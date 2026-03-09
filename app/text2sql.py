"""Text2SQL 管道：自然语言 -> SQL -> 执行 -> 自然语言回答"""

import json
import logging
import random
import re
import urllib.parse
from typing import Any, Optional

from app.llm_client import llm_client
from app.database import execute_query
from app.prompts import (
    get_system_prompt,
    get_answer_system_prompt,
    format_answer_prompt,
    format_error_prompt,
)
from app.config import get_primary_video_url, get_all_video_urls
from app.models import MediaContent

logger = logging.getLogger(__name__)


def _detect_media_request(sql: str) -> Optional[str]:
    """
    检测SQL是否为视频/图片请求

    Returns:
        "video" - 视频请求
        "image" - 图片请求
        None - 普通数据查询
    """
    sql_upper = sql.upper()
    if "-- VIDEO_REQUEST" in sql_upper:
        return "video"
    elif "-- IMAGE_REQUEST" in sql_upper:
        return "image"
    return None


def _extract_camera_info(rows: list[dict[str, Any]]) -> Optional[dict]:
    """从查询结果中提取摄像机信息"""
    if not rows or len(rows) == 0:
        return None

    row = rows[0]
    # 尝试多种可能的ID字段名
    camera_id = row.get("id") or row.get("camera_id") or row.get("cameras.id")
    camera_name = row.get("name") or row.get("cameras.name")
    online_status = row.get("online_status") or row.get("cameras.online_status")
    check_time = row.get("check_time") or row.get("cameras.check_time")

    if camera_id and camera_name:
        return {
            "id": int(camera_id),
            "name": str(camera_name),
            "online_status": int(online_status) if online_status else 0,
            "check_time": str(check_time) if check_time else "",
        }
    return None


def _generate_video_response(
    camera_info: dict, answer: str
) -> tuple[str, Optional[MediaContent]]:
    """生成视频响应"""
    video_url = get_primary_video_url()

    media = MediaContent(
        type="video",
        camera_id=camera_info["id"],
        camera_name=camera_info["name"],
        url=video_url,
        thumbnail_time=None,
    )

    # 更新回答文本
    video_answer = (
        f"**📹 视频播放：{camera_info['name']} (ID: {camera_info['id']})**\n\n" + answer
    )

    return video_answer, media


def _generate_image_response(
    camera_info: dict, answer: str
) -> tuple[str, Optional[MediaContent]]:
    """生成图片响应"""
    # 生成随机截图时间点（5-30秒之间的随机值，模拟从视频中随机截取）
    random_time = round(random.uniform(5.0, 30.0), 2)

    # 图片URL使用base64格式的截图API，直接返回图片数据
    video_url = get_primary_video_url()
    encoded_video_url = urllib.parse.quote(video_url, safe="")
    image_url = f"/api/screenshot?video_url={encoded_video_url}&timestamp={random_time}&camera_id={camera_info['id']}&camera_name={urllib.parse.quote(camera_info['name'])}&format=base64"

    media = MediaContent(
        type="image",
        camera_id=camera_info["id"],
        camera_name=camera_info["name"],
        url=image_url,
        thumbnail_time=random_time,
    )

    # 更新回答文本
    image_answer = (
        f"**🖼️ 截图预览：{camera_info['name']} (ID: {camera_info['id']})**\n\n" + answer
    )

    return image_answer, media


def _format_query_result(result: dict[str, Any]) -> str:
    """将查询结果格式化为文本，供 LLM 生成回答"""
    if not result["success"]:
        return f"查询失败: {result['error']}"

    if result["row_count"] == 0:
        return "查询成功，但没有返回任何数据。"

    # 格式化为表格文本
    rows = result["rows"]
    columns = result["columns"]

    lines = [f"共返回 {result['row_count']} 条记录：", ""]

    # 表头
    lines.append(" | ".join(str(c) for c in columns))
    lines.append("-" * 60)

    # 数据行（最多展示 50 行避免 token 爆炸）
    display_rows = rows[:50]
    for row in display_rows:
        lines.append(" | ".join(str(row.get(c, "")) for c in columns))

    if len(rows) > 50:
        lines.append(f"... 还有 {len(rows) - 50} 条记录未显示")

    return "\n".join(lines)


async def process_question(question: str) -> dict[str, Any]:
    """
    完整的 Text2SQL 管道。

    流程:
        1. 用户问题 -> LLM 生成 SQL
        2. SQL -> 数据库执行
        3. 执行结果 -> LLM 生成自然语言回答

    返回:
        {
            "answer": str,       # 自然语言回答
            "sql": str,          # 生成的 SQL
            "data": list | None, # 原始查询数据
            "success": bool,
            "error": str | None,
            "media": MediaContent | None  # 视频/图片内容
        }
    """
    generated_sql = ""
    media_content = None

    try:
        # 第 1 步：生成 SQL
        logger.info(f"用户问题: {question}")
        generated_sql = await llm_client.generate_sql(question, get_system_prompt())
        logger.info(f"生成 SQL: {generated_sql}")

        # 检测是否为视频/图片请求
        media_request_type = _detect_media_request(generated_sql)
        if media_request_type:
            # 移除请求标记，获取纯净的SQL
            generated_sql = re.sub(
                r"\s*--\s*(VIDEO_REQUEST|IMAGE_REQUEST)\s*$",
                "",
                generated_sql,
                flags=re.IGNORECASE,
            )
            logger.info(
                f"媒体请求检测到: {media_request_type}, 清理后SQL: {generated_sql}"
            )

        # 第 2 步：执行 SQL
        query_result = execute_query(generated_sql)
        logger.info(
            f"查询结果: success={query_result['success']}, rows={query_result['row_count']}"
        )

        # 第 3 步：生成自然语言回答
        if query_result["success"]:
            result_text = format_answer_prompt(
                question=question,
                result=_format_query_result(query_result),
            )
            answer = await llm_client.generate_answer(
                question=question,
                system_prompt=get_answer_system_prompt(),
                result_text=result_text,
            )

            # 如果是视频/图片请求，提取摄像机信息并生成媒体内容
            if media_request_type and query_result["rows"]:
                camera_info = _extract_camera_info(query_result["rows"])
                if camera_info:
                    if media_request_type == "video":
                        answer, media_content = _generate_video_response(
                            camera_info, answer
                        )
                    elif media_request_type == "image":
                        answer, media_content = _generate_image_response(
                            camera_info, answer
                        )
                    logger.info(
                        f"媒体内容已生成: {media_request_type}, camera: {camera_info['name']}"
                    )

            return {
                "answer": answer,
                "sql": generated_sql,
                "data": query_result["rows"],
                "success": True,
                "error": None,
                "media": media_content,
            }
        else:
            # SQL 执行失败，让 LLM 生成友好的错误提示
            error_text = format_error_prompt(
                question=question,
                error=query_result["error"],
            )
            answer = await llm_client.generate_answer(
                question=question,
                system_prompt=get_answer_system_prompt(),
                result_text=error_text,
            )
            return {
                "answer": answer,
                "sql": generated_sql,
                "data": None,
                "success": False,
                "error": query_result["error"],
                "media": None,
            }

    except Exception as e:
        logger.exception("Text2SQL 管道异常")
        return {
            "answer": f"抱歉，处理您的问题时遇到了技术问题：{str(e)}。请稍后再试或换一种方式提问。",
            "sql": generated_sql,
            "data": None,
            "success": False,
            "error": str(e),
            "media": None,
        }
