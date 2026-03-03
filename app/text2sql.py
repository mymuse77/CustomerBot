"""Text2SQL 管道：自然语言 -> SQL -> 执行 -> 自然语言回答"""

import json
import logging
from typing import Any

from app.llm_client import llm_client
from app.database import execute_query
from app.prompts import (
    SYSTEM_PROMPT,
    ANSWER_SYSTEM_PROMPT,
    ANSWER_USER_TEMPLATE,
    ERROR_ANSWER_TEMPLATE,
)

logger = logging.getLogger(__name__)


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
            "error": str | None
        }
    """
    generated_sql = ""

    try:
        # 第 1 步：生成 SQL
        logger.info(f"用户问题: {question}")
        generated_sql = await llm_client.generate_sql(question, SYSTEM_PROMPT)
        logger.info(f"生成 SQL: {generated_sql}")

        # 第 2 步：执行 SQL
        query_result = execute_query(generated_sql)
        logger.info(
            f"查询结果: success={query_result['success']}, rows={query_result['row_count']}"
        )

        # 第 3 步：生成自然语言回答
        if query_result["success"]:
            result_text = ANSWER_USER_TEMPLATE.format(
                question=question,
                result=_format_query_result(query_result),
            )
            answer = await llm_client.generate_answer(
                question=question,
                system_prompt=ANSWER_SYSTEM_PROMPT,
                result_text=result_text,
            )
            return {
                "answer": answer,
                "sql": generated_sql,
                "data": query_result["rows"],
                "success": True,
                "error": None,
            }
        else:
            # SQL 执行失败，让 LLM 生成友好的错误提示
            error_text = ERROR_ANSWER_TEMPLATE.format(
                question=question,
                error=query_result["error"],
            )
            answer = await llm_client.generate_answer(
                question=question,
                system_prompt=ANSWER_SYSTEM_PROMPT,
                result_text=error_text,
            )
            return {
                "answer": answer,
                "sql": generated_sql,
                "data": None,
                "success": False,
                "error": query_result["error"],
            }

    except Exception as e:
        logger.exception("Text2SQL 管道异常")
        return {
            "answer": f"抱歉，处理您的问题时遇到了技术问题：{str(e)}。请稍后再试或换一种方式提问。",
            "sql": generated_sql,
            "data": None,
            "success": False,
            "error": str(e),
        }
