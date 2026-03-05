"""FastAPI 应用入口"""

import base64
import logging
import os
import subprocess
import tempfile
import urllib.parse
from pathlib import Path

from fastapi import FastAPI, Query
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, HTMLResponse, Response

from app.models import ChatRequest, ChatResponse, HealthResponse
from app.text2sql import process_question
from app.database import test_connection

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)

app = FastAPI(
    title="视频监控数字人",
    description="基于 Text2SQL + LLM 的视频监控平台智能问答系统",
    version="1.1.0",
)

# 挂载静态文件
static_dir = Path(__file__).parent.parent / "static"
app.mount("/static", StaticFiles(directory=str(static_dir)), name="static")


@app.get("/", response_class=FileResponse)
async def index():
    """返回前端页面"""
    return FileResponse(str(static_dir / "index.html"))


@app.get("/health", response_model=HealthResponse)
async def health():
    """健康检查"""
    db_ok = test_connection()
    return HealthResponse(
        status="ok" if db_ok else "degraded",
        db_connected=db_ok,
    )


@app.post("/api/chat", response_model=ChatResponse)
async def chat(req: ChatRequest):
    """
    聊天接口：接收用户自然语言问题，返回数据分析结果。

    流程: 问题 -> Text2SQL -> 执行查询 -> LLM 生成回答
    支持视频/图片请求，返回媒体内容
    """
    result = await process_question(req.question)
    return ChatResponse(**result)


@app.get("/api/screenshot")
async def get_screenshot(
    video_url: str = Query(..., description="视频URL"),
    timestamp: float = Query(..., description="截图时间点（秒）"),
    camera_id: int = Query(..., description="摄像机ID"),
    camera_name: str = Query(..., description="摄像机名称"),
    format: str = Query("html", description="返回格式: html 或 base64"),
):
    """
    截图API：返回指定视频在指定时间点的截图

    format=base64: 直接返回 base64 图片数据（供 <img src="data:image/jpeg;base64,..."> 使用）
    format=html: 返回视频播放器HTML页面，由前端JS执行实际截图（默认，兼容性更好）
    """

    # 如果请求 base64 格式，使用服务器端截图直接返回 base64
    if format == "base64":
        decoded_video_url = urllib.parse.unquote(video_url)
        logging.info(
            f"[Screenshot] Base64模式 - 视频URL: {decoded_video_url}, 时间点: {timestamp}秒"
        )

        # 检查是否为本地文件
        if os.path.isfile(decoded_video_url):
            video_path = decoded_video_url
        else:
            video_path = decoded_video_url

        # 使用 ffmpeg 截图
        try:
            with tempfile.NamedTemporaryFile(suffix=".jpg", delete=False) as tmp:
                tmp_path = tmp.name

            # ffmpeg 命令
            base_args = ["ffmpeg", "-y"]
            is_stream = not os.path.isfile(decoded_video_url) and (
                decoded_video_url.startswith("http://")
                or decoded_video_url.startswith("https://")
            )

            if is_stream and (
                decoded_video_url.endswith(".m3u8") or decoded_video_url.endswith(".ts")
            ):
                cmd = base_args + [
                    "-i",
                    decoded_video_url,
                    "-ss",
                    str(timestamp),
                    "-vframes",
                    "1",
                    "-q:v",
                    "2",
                    tmp_path,
                ]
            else:
                cmd = base_args + [
                    "-ss",
                    str(timestamp),
                    "-i",
                    decoded_video_url,
                    "-vframes",
                    "1",
                    "-q:v",
                    "2",
                    tmp_path,
                ]

            result = subprocess.run(cmd, capture_output=True, text=True, timeout=60)

            if result.returncode == 0 and os.path.exists(tmp_path):
                with open(tmp_path, "rb") as f:
                    img_data = f.read()
                b64_img = base64.b64encode(img_data).decode("utf-8")

                try:
                    os.unlink(tmp_path)
                except:
                    pass

                logging.info(f"[Screenshot] 截图成功，图片大小: {len(img_data)} bytes")

                # 返回包含 base64 图片的 HTML
                img_html = f"""<!DOCTYPE html>
<html>
<head>
    <meta charset="UTF-8">
    <title>截图</title>
    <style>
        body {{ margin: 0; padding: 0; background: #000; display: flex; justify-content: center; align-items: center; min-height: 100vh; }}
        img {{ max-width: 100%; max-height: 100vh; object-fit: contain; cursor: pointer; }}
    </style>
</head>
<body>
    <img src="data:image/jpeg;base64,{b64_img}" alt="截图" onclick="window.parent.postMessage({{type:'image-click'}}, '*')" ondblclick="window.parent.postMessage({{type:'image-dblclick'}}, '*')">
    <script>
        // ESC键通知父窗口关闭
        document.addEventListener('keydown', function(e) {{
            if (e.key === 'Escape') {{
                window.parent.postMessage({{type:'esc-close'}}, '*');
            }}
        }});
        // 点击空白处关闭
        document.addEventListener('click', function(e) {{
            if (e.target.tagName !== 'IMG') {{
                window.parent.postMessage({{type:'esc-close'}}, '*');
            }}
        }});
    </script>
</body>
</html>"""
                return HTMLResponse(content=img_html)
            else:
                error_msg = result.stderr[:500] if result.stderr else "截图失败"
                logging.error(f"[Screenshot] 失败: {error_msg}")
                return HTMLResponse(
                    content=f"<div style='color:#f44336;padding:20px;'>截图失败: {error_msg}</div>"
                )

        except Exception as e:
            logging.error(f"[Screenshot] 异常: {str(e)}")
            return HTMLResponse(
                content=f"<div style='color:#f44336;padding:20px;'>截图异常: {str(e)}</div>"
            )

    # ========================================
    # 服务器端截图（使用 ffmpeg）- 默认模式
    # ========================================
    # 服务器端截图（使用 ffmpeg）
    # ========================================
    # URL解码
    decoded_video_url = urllib.parse.unquote(video_url)
    logging.info(f"[Screenshot] 视频URL: {decoded_video_url}, 时间点: {timestamp}秒")

    # 检查是否为本地文件
    if os.path.isfile(decoded_video_url):
        # 本地文件直接用文件路径
        video_path = decoded_video_url
        input_args = [video_path]
    else:
        # 远程URL - ffmpeg 直接处理
        video_path = decoded_video_url
        input_args = [video_path]

    # 使用 ffmpeg 截图
    try:
        # 创建临时文件保存截图
        with tempfile.NamedTemporaryFile(suffix=".jpg", delete=False) as tmp:
            tmp_path = tmp.name

        # ffmpeg 命令改进：对流媒体使用更可靠的参数顺序
        # 基础参数
        base_args = ["ffmpeg", "-y"]

        # 检测是否为流媒体(URL且包含特殊扩展名)
        is_stream = not os.path.isfile(decoded_video_url) and (
            decoded_video_url.startswith("http://")
            or decoded_video_url.startswith("https://")
        )

        if is_stream and (
            decoded_video_url.endswith(".m3u8") or decoded_video_url.endswith(".ts")
        ):
            # 对HLS流：-ss放在-i之后更可靠
            cmd = base_args + [
                "-i",
                decoded_video_url,
                "-ss",
                str(timestamp),
                "-vframes",
                "1",
                "-q:v",
                "2",
                tmp_path,
            ]
        else:
            # 对本地文件或普通URL：-ss放在-i之前更快
            cmd = base_args + [
                "-ss",
                str(timestamp),
                "-i",
                decoded_video_url,
                "-vframes",
                "1",
                "-q:v",
                "2",
                tmp_path,
            ]

        logging.info(f"[Screenshot] 执行命令: {' '.join(cmd[:8])}...")

        # 执行 ffmpeg
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=60)

        if result.returncode == 0 and os.path.exists(tmp_path):
            # 读取截图并返回 base64
            with open(tmp_path, "rb") as f:
                img_data = f.read()
            b64_img = base64.b64encode(img_data).decode("utf-8")

            # 清理临时文件
            try:
                os.unlink(tmp_path)
            except:
                pass

            logging.info(f"[Screenshot] 截图成功，图片大小: {len(img_data)} bytes")

            # 返回 base64 图片
            img_html = f"""<!DOCTYPE html>
<html>
<head>
    <meta charset="UTF-8">
    <title>截图</title>
    <style>
        body {{ margin: 0; background: #000; display: flex; justify-content: center; align-items: center; min-height: 100vh; }}
        img {{ max-width: 100%; max-height: 90vh; }}
    </style>
</head>
<body>
    <img src="data:image/jpeg;base64,{b64_img}" alt="截图">
</body>
</html>"""
            return HTMLResponse(content=img_html)
        else:
            # ffmpeg 失败，记录详细错误
            error_msg = result.stderr[:800] if result.stderr else "未知错误"
            logging.error(f"[Screenshot] ffmpeg 失败: {error_msg}")
            return HTMLResponse(
                content=f"""
<html><body style="color:#f44336;font-family:Arial;padding:20px;text-align:center;">
❌ 截图失败<br><br>
<small style="color:#666;">{error_msg[:300]}...</small>
</body></html>"""
            )

    except subprocess.TimeoutExpired:
        logging.error("[Screenshot] 截图超时")
        return HTMLResponse(
            content="""
<html><body style="color:#f44336;font-family:Arial;padding:20px;text-align:center;">
❌ 截图超时，视频可能无法访问或太大
</body></html>""",
            status_code=500,
        )
    except Exception as e:
        logging.exception("[Screenshot] 截图异常")
        return HTMLResponse(
            content=f"""
<html><body style="color:#f44336;font-family:Arial;padding:20px;text-align:center;">
❌ 截图异常: {str(e)}
</body></html>""",
            status_code=500,
        )
    decoded_camera_name = urllib.parse.unquote(camera_name)

    # 动态检测视频MIME类型
    if decoded_video_url.endswith(".flv"):
        video_type = "video/x-flv"
    elif decoded_video_url.endswith(".m3u8"):
        video_type = "application/x-mpegURL"
    elif decoded_video_url.endswith(".webm"):
        video_type = "video/webm"
    else:
        video_type = "video/mp4"  # 默认MP4

    # JavaScript脚本（作为普通字符串，不使用f-string转义）
    js_script = """
        const video = document.getElementById('video');
        const canvas = document.getElementById('canvas');
        const ctx = canvas.getContext('2d');
        const screenshot = document.getElementById('screenshot');
        const videoUrl = 'VIDEO_URL_PLACEHOLDER';
        const timestamp = TIMESTAMP_PLACEHOLDER;
        
        const isFlv = videoUrl.endsWith('.flv');
        const isM3u8 = videoUrl.endsWith('.m3u8');
        
        if (isFlv && flvjs.isSupported()) {
            const flvPlayer = flvjs.createPlayer({
                type: 'flv',
                url: videoUrl
            }, {
                enableWorker: true,
                enableStashBuffer: false,
                stashInitialSize: 128
            });
            flvPlayer.attachMediaElement(video);
            flvPlayer.load();
            flvPlayer.play();
            
            video.addEventListener('loadeddata', function() {
                video.currentTime = timestamp;
            });
            
            video.addEventListener('seeked', function() {
                captureFrame();
            });
            
            setTimeout(() => {
                if (video.readyState >= 2 && video.currentTime < 0.1) {
                    captureFrame();
                }
            }, 3000);
        } else if (isM3u8 && Hls.isSupported()) {
            const hls = new Hls();
            hls.loadSource(videoUrl);
            hls.attachMedia(video);
            hls.on(Hls.Events.MANIFEST_PARSED, function() {
                video.currentTime = timestamp;
                video.play();
            });
            
            video.addEventListener('seeked', function() {
                captureFrame();
            });
            
            setTimeout(() => {
                if (video.readyState >= 2 && video.currentTime < 0.1) {
                    captureFrame();
                }
            }, 3000);
        } else {
            video.addEventListener('loadeddata', function() {
                video.currentTime = timestamp;
            });
            
            video.addEventListener('seeked', function() {
                captureFrame();
            });
            
            setTimeout(() => {
                captureFrame();
            }, 3000);
        }
        
        function captureFrame() {
            try {
                canvas.width = video.videoWidth || 640;
                canvas.height = video.videoHeight || 360;
                ctx.drawImage(video, 0, 0, canvas.width, canvas.height);
                const dataUrl = canvas.toDataURL('image/jpeg', 0.85);
                screenshot.src = dataUrl;
                console.log('Screenshot captured at', video.currentTime, 'seconds');
                document.querySelector('.info p').textContent = 
                    '截图成功！时间点: ' + video.currentTime.toFixed(2) + '秒';
            } catch (e) {
                document.querySelector('.info p').textContent = 
                    '截图失败: ' + e.message + '（可能是跨域限制）';
                console.error(e);
            }
        }
    """

    # 替换占位符
    js_script = js_script.replace("VIDEO_URL_PLACEHOLDER", decoded_video_url)
    js_script = js_script.replace("TIMESTAMP_PLACEHOLDER", str(timestamp))

    # 构建HTML内容（使用普通字符串拼接）
    html_content = (
        """<!DOCTYPE html>
<html>
<head>
    <meta charset="UTF-8">
    <title>截图 - """
        + decoded_camera_name
        + """</title>
    <style>
        body { 
            margin: 0; 
            padding: 20px; 
            background: #1a1a1a; 
            display: flex; 
            flex-direction: column; 
            align-items: center;
            min-height: 100vh;
        }
        #video-container {
            position: relative;
            max-width: 100%;
            background: #000;
            border-radius: 8px;
            overflow: hidden;
        }
        video {
            display: block;
            max-width: 100%;
            max-height: 60vh;
        }
        #canvas {
            display: none;
        }
        #output {
            margin-top: 20px;
            text-align: center;
        }
        #output img {
            max-width: 100%;
            border-radius: 8px;
            box-shadow: 0 4px 20px rgba(0,0,0,0.5);
        }
        .info {
            color: #fff;
            margin-bottom: 10px;
            font-family: Arial, sans-serif;
        }
    </style>
</head>
<body>
    <div class="info">
        <h2>📷 """
        + decoded_camera_name
        + """ (ID: """
        + str(camera_id)
        + """)</h2>
        <p>正在加载视频并截取 """
        + str(timestamp)
        + """ 秒处的画面...</p>
    </div>
    <div id="video-container">
        <video id="video" controls crossorigin="anonymous">
            <source src=\""""
        + decoded_video_url
        + '" type="'
        + video_type
        + '">\n        </video>\n    </div>\n    <canvas id="canvas"></canvas>\n    <div id="output">\n        <img id="screenshot" alt="截图">\n    </div>\n    \n    <script src="https://cdn.jsdelivr.net/npm/flv.js@1.6.2/dist/flv.min.js"></script>\n    <script src="https://cdn.jsdelivr.net/npm/hls.js@latest/dist/hls.min.js"></script>\n    <script>\n'
        ""
        + js_script
        + """
    </script>
</body>
</html>
"""
    )
    return HTMLResponse(content=html_content)
