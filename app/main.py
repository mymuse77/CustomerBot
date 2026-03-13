"""FastAPI 应用入口"""

import asyncio
import base64
import json
import logging
import os
import subprocess
import tempfile
import time
import urllib.parse
from pathlib import Path

import httpx
from fastapi import FastAPI, File, Query, Request, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse, Response
from fastapi.templating import Jinja2Templates

from app.models import ChatRequest, ChatResponse, HealthResponse
from app.text2sql import process_question
from app.database import test_connection
from app.config import get_app_config, SENSEVOICE_SERVICE_URL

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)

app = FastAPI(
    title=get_app_config("app.title", "视频监控数字人"),
    description=get_app_config(
        "app.description", "基于 Text2SQL + LLM 的视频监控平台智能问答系统"
    ),
    version=get_app_config("app.version", "1.1.0"),
)

# 配置 CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # 允许所有来源，生产环境应该限制具体域名
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 挂载静态文件
static_dir = Path(__file__).parent.parent / "static"
app.mount("/static", StaticFiles(directory=str(static_dir)), name="static")

# 挂载模板文件
templates_dir = Path(__file__).parent / "templates"
templates = Jinja2Templates(directory=str(templates_dir))


@app.get("/", response_class=FileResponse)
async def index():
    """返回前端页面"""
    return FileResponse(str(static_dir / "index.html"))


@app.get("/health", response_model=HealthResponse)
async def health():
    """健康检查"""
    db_ok = test_connection()

    # 检查 SenseVoice 服务状态
    sensevoice_ok = False
    try:
        async with httpx.AsyncClient() as client:
            response = await client.get(f"{SENSEVOICE_SERVICE_URL}/docs", timeout=5.0)
            sensevoice_ok = response.status_code == 200
    except:
        sensevoice_ok = False

    return HealthResponse(
        status="ok" if db_ok else "degraded",
        db_connected=db_ok,
        sensevoice_connected=sensevoice_ok,
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
    request: Request,
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

    timeout_sec = get_app_config("business.screenshot_timeout", 60)

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

            result = subprocess.run(
                cmd, capture_output=True, text=True, timeout=timeout_sec
            )

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
                return templates.TemplateResponse(
                    "screenshot_base64.html", {"request": request, "b64_img": b64_img}
                )
            else:
                error_msg = result.stderr[:500] if result.stderr else "截图失败"
                logging.error(f"[Screenshot] 失败: {error_msg}")
                return templates.TemplateResponse(
                    "screenshot_error.html",
                    {
                        "request": request,
                        "error_title": "截图失败",
                        "error_msg": error_msg,
                    },
                )

        except Exception as e:
            logging.error(f"[Screenshot] 异常: {str(e)}")
            return templates.TemplateResponse(
                "screenshot_error.html",
                {"request": request, "error_title": "截图异常", "error_msg": str(e)},
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
        result = subprocess.run(
            cmd, capture_output=True, text=True, timeout=timeout_sec
        )

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

            # 返回 base64 图片 (重用 base64 模板)
            return templates.TemplateResponse(
                "screenshot_base64.html", {"request": request, "b64_img": b64_img}
            )
        else:
            # ffmpeg 失败，记录详细错误
            error_msg = result.stderr[:800] if result.stderr else "未知错误"
            logging.error(f"[Screenshot] ffmpeg 失败: {error_msg}")
            return templates.TemplateResponse(
                "screenshot_error.html",
                {"request": request, "error_title": "截图失败", "error_msg": error_msg},
            )

    except subprocess.TimeoutExpired:
        logging.error("[Screenshot] 截图超时")
        return templates.TemplateResponse(
            "screenshot_error.html",
            {
                "request": request,
                "error_title": "截图超时",
                "error_msg": "视频可能无法访问或太大",
            },
            status_code=500,
        )
    except Exception as e:
        logging.exception("[Screenshot] 截图异常")
        return templates.TemplateResponse(
            "screenshot_error.html",
            {"request": request, "error_title": "截图异常", "error_msg": str(e)},
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

    return templates.TemplateResponse(
        "screenshot_player.html",
        {
            "request": request,
            "camera_name": decoded_camera_name,
            "camera_id": camera_id,
            "timestamp": timestamp,
            "video_url": decoded_video_url,
            "video_type": video_type,
        },
    )


@app.post("/api/sensevoice/transcribe")
async def sensevoice_transcribe(
    audio: UploadFile = File(
        ...,
        description="音频文件 (支持 wav, mp3, m4a, ogg, webm 等格式)",
        media_type="audio/*",
    ),
):
    """
    SenseVoice 语音识别接口
    接收音频文件，转换为 wav 格式后转发到本地 SenseVoice 服务进行转写
    """
    try:
        # 读取上传的音频文件
        if not audio:
            return JSONResponse(
                status_code=400, content={"success": False, "error": "未提供音频文件"}
            )

        audio_content = await audio.read()
        if not audio_content or len(audio_content) == 0:
            return JSONResponse(
                status_code=400, content={"success": False, "error": "音频文件为空"}
            )

        logging.info(
            f"[SenseVoice] 接收到音频文件: {audio.filename}, 大小: {len(audio_content)} bytes, 类型: {audio.content_type}"
        )

        # 检查是否需要转换为 wav 格式
        content_type = audio.content_type or ""
        filename = audio.filename or "audio.wav"

        # 如果是 webm 格式，转换为 wav
        if "webm" in content_type.lower() or filename.endswith(".webm"):
            logging.info("[SenseVoice] 检测到 webm 格式，转换为 wav...")
            try:
                import subprocess
                import tempfile

                # 保存原始 webm 到临时文件
                with tempfile.NamedTemporaryFile(
                    suffix=".webm", delete=False
                ) as tmp_in:
                    tmp_in.write(audio_content)
                    tmp_in_path = tmp_in.name

                # 转换为 wav
                with tempfile.NamedTemporaryFile(
                    suffix=".wav", delete=False
                ) as tmp_out:
                    tmp_out_path = tmp_out.name

                # 使用 ffmpeg 转换
                cmd = [
                    "ffmpeg",
                    "-y",  # 覆盖输出文件
                    "-i",
                    tmp_in_path,  # 输入
                    "-ar",
                    "16000",  # 采样率 16kHz
                    "-ac",
                    "1",  # 单声道
                    "-c:a",
                    "pcm_s16le",  # 16-bit PCM
                    tmp_out_path,
                ]

                result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)

                if result.returncode == 0:
                    # 读取转换后的 wav
                    with open(tmp_out_path, "rb") as f:
                        audio_content = f.read()
                    filename = "recording.wav"
                    content_type = "audio/wav"
                    logging.info(
                        f"[SenseVoice] 转换成功，新大小: {len(audio_content)} bytes"
                    )
                else:
                    logging.error(f"[SenseVoice] ffmpeg 转换失败: {result.stderr}")
                    # 继续使用原始格式

                # 清理临时文件
                try:
                    import os

                    os.unlink(tmp_in_path)
                    os.unlink(tmp_out_path)
                except:
                    pass

            except Exception as e:
                logging.error(f"[SenseVoice] 格式转换失败: {str(e)}")
                # 继续使用原始格式

        # 调用本地 SenseVoice 服务
        async with httpx.AsyncClient() as client:
            from io import BytesIO

            files = {
                "file": (
                    filename or "audio.wav",
                    BytesIO(audio_content),
                    content_type or "audio/wav",
                )
            }
            data = {"language": "zh"}

            logging.info(
                f"[SenseVoice] 转发到服务: {SENSEVOICE_SERVICE_URL}/transcribe"
            )

            try:
                response = await client.post(
                    f"{SENSEVOICE_SERVICE_URL}/transcribe",
                    files=files,
                    data=data,
                    timeout=60.0,
                )
                logging.info(f"[SenseVoice] 服务响应状态: {response.status_code}")
                response.raise_for_status()
            except httpx.ConnectError as e:
                logging.error(f"[SenseVoice] 无法连接到服务: {str(e)}")
                return JSONResponse(
                    status_code=503,
                    content={
                        "success": False,
                        "error": f"无法连接到 SenseVoice 服务，请确保服务已启动: {str(e)}",
                    },
                )
            except httpx.HTTPStatusError as e:
                logging.error(
                    f"[SenseVoice] 服务返回错误: {e.response.status_code} - {e.response.text}"
                )
                return JSONResponse(
                    status_code=500,
                    content={
                        "success": False,
                        "error": f"SenseVoice 服务错误 ({e.response.status_code}): {e.response.text}",
                    },
                )

            result = response.json()
            logging.info(f"[SenseVoice] 服务响应: {result}")

            if result.get("success"):
                # 清理特殊标记
                text = result.get("text", "")
                text = _clean_sensevoice_text(text)

                return JSONResponse(
                    content={
                        "success": True,
                        "text": text,
                        "language": result.get("language", "zh"),
                        "duration": result.get("duration", 0),
                    }
                )
            else:
                # SenseVoice 返回了 200 但识别失败
                error_msg = result.get("error") or result.get("message") or "识别失败"
                logging.error(f"[SenseVoice] 识别失败: {error_msg}")
                return JSONResponse(
                    status_code=500,
                    content={
                        "success": False,
                        "error": f"SenseVoice 识别失败: {error_msg}",
                    },
                )

    except httpx.HTTPError as e:
        logging.error(f"[SenseVoice] HTTP 错误: {str(e)}")
        return JSONResponse(
            status_code=500,
            content={"success": False, "error": f"SenseVoice 服务调用失败: {str(e)}"},
        )
    except Exception as e:
        logging.exception(f"[SenseVoice] 转写异常: {str(e)}")
        import traceback

        error_detail = traceback.format_exc()
        logging.error(f"[SenseVoice] 详细错误: {error_detail}")
        return JSONResponse(
            status_code=500, content={"success": False, "error": f"识别失败: {str(e)}"}
        )


def _clean_sensevoice_text(text: str) -> str:
    """清理 SenseVoice 返回的文本中的特殊标记"""
    if not text:
        return ""

    # 移除 emotion 标记 <|NEUTRAL|>, <|HAPPY|>, <|ANGRY|>, <|SAD|>
    import re

    text = re.sub(r"\<\|(NEUTRAL|HAPPY|ANGRY|SAD)\|\>", "", text)

    # 移除 language 标记 <|zh|>, <|en|>, <|ja|>, <|ko|> 等
    text = re.sub(r"\<\|(zh|en|ja|ko|yue|auto)\|\>", "", text)

    # 移除 event 标记 <|Speech|>, <|/Speech|>, <|BGM|>, <|/BGM|> 等
    text = re.sub(
        r"\<\|(Speech|/Speech|BGM|/BGM|Applause|Laughter|/Laughter)\|\>", "", text
    )

    # 移除多余空白
    text = text.strip()
    text = re.sub(r"\s+", " ", text)

    return text
