/**
 * Whisper Web Worker - 纯前端语音识别后台线程
 *
 * 职责：
 * 1. 加载并缓存 Whisper-small 量化模型（ONNX）
 * 2. 接收主线程传来的 16kHz Float32 PCM 音频数据
 * 3. 执行推理并将识别文字（简体中文）返回主线程
 *
 * 通信协议（postMessage）：
 *   主线程 -> Worker:
 *     { type: 'load' }                           预加载模型
 *     { type: 'transcribe', audio: Float32Array } 执行识别
 *   Worker -> 主线程:
 *     { type: 'status', status: string, progress?: number }
 *     { type: 'ready' }                           模型就绪
 *     { type: 'result', text: string }            识别结果
 *     { type: 'error', message: string }          错误
 */

// 引入 Transformers.js（CDN ESM 版本）
import { pipeline, env } from 'https://cdn.jsdelivr.net/npm/@xenova/transformers@2.17.2';

// -------- 配置 --------
// 禁用本地模型搜索，强制走 HuggingFace Hub CDN
env.allowLocalModels = false;
// 线程数设为 1，兼容性最好，避免低端设备爆内存
// （Chromium 的 SharedArrayBuffer 跨域隔离要求严格，1 线程最稳）
env.backends.onnx.wasm.numThreads = 1;

// 使用的模型 ID
// whisper-small 比 tiny 中文识别准确度显著更高，量化后约 ~150MB，首次下载后缓存
const MODEL_ID = 'Xenova/whisper-small';

// 单例 transcriber pipeline
let transcriber = null;
let isLoading = false;

/**
 * 加载（或从缓存恢复）Whisper pipeline
 */
async function loadModel() {
  if (transcriber) {
    self.postMessage({ type: 'ready', modelId: MODEL_ID });
    return;
  }
  if (isLoading) return; // 防止并发重复加载
  isLoading = true;

  self.postMessage({ type: 'status', status: 'downloading', progress: 0 });

  try {
    transcriber = await pipeline(
      'automatic-speech-recognition',
      MODEL_ID,
      {
        quantized: true,   // 使用量化版本，体积 ~150MB（首次下载后自动缓存到浏览器 Cache Storage）
        // 进度回调
        progress_callback: (progress) => {
          if (progress.status === 'progress' && progress.progress !== undefined) {
            self.postMessage({
              type: 'status',
              status: 'downloading',
              progress: Math.round(progress.progress),
            });
          } else if (progress.status === 'done') {
            self.postMessage({ type: 'status', status: 'loading', progress: 100 });
          }
        },
      }
    );

    self.postMessage({ type: 'ready', modelId: MODEL_ID });
  } catch (err) {
    self.postMessage({ type: 'error', message: `模型加载失败: ${err.message}` });
  } finally {
    isLoading = false;
  }
}

/**
 * 执行语音转文字推理
 * @param {Float32Array} audioData - 16kHz 单声道 PCM 数据
 */
async function transcribe(audioData) {
  if (!transcriber) {
    self.postMessage({ type: 'error', message: '模型尚未加载完成' });
    return;
  }

  self.postMessage({ type: 'status', status: 'transcribing' });

  try {
    const result = await transcriber(audioData, {
      language: 'zh',            // 'zh' = 简体中文（'chinese' 会输出繁体）
      task: 'transcribe',        // 识别（非翻译）
      chunk_length_s: 30,        // 每段最多 30s
      stride_length_s: 5,        // 重叠 5s，提高连续语音精度
    });

    const text = result.text ? result.text.trim() : '';
    self.postMessage({ type: 'result', text });
  } catch (err) {
    self.postMessage({ type: 'error', message: `识别失败: ${err.message}` });
  }
}

// -------- 消息分发 --------
self.addEventListener('message', async (e) => {
  const { type, audio } = e.data;

  switch (type) {
    case 'load':
      await loadModel();
      break;
    case 'transcribe':
      await transcribe(audio);
      break;
    default:
      self.postMessage({ type: 'error', message: `未知消息类型: ${type}` });
  }
});
