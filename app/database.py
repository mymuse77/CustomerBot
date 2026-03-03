"""数据库连接与查询执行"""

import pymysql
from pymysql.cursors import DictCursor
from contextlib import contextmanager
from typing import Any

from app.config import DB_HOST, DB_PORT, DB_USER, DB_PASSWORD, DB_NAME


def _get_connection() -> pymysql.Connection:
    """创建数据库连接"""
    return pymysql.connect(
        host=DB_HOST,
        port=DB_PORT,
        user=DB_USER,
        password=DB_PASSWORD,
        database=DB_NAME,
        charset="utf8mb4",
        cursorclass=DictCursor,
        connect_timeout=10,
        read_timeout=30,
    )


@contextmanager
def get_connection():
    """数据库连接上下文管理器"""
    conn = _get_connection()
    try:
        yield conn
    finally:
        conn.close()


def execute_query(sql: str) -> dict[str, Any]:
    """
    执行 SQL 查询并返回结果。

    返回:
        {
            "success": True/False,
            "columns": [...],  # 列名列表
            "rows": [...],     # 结果行（字典列表）
            "row_count": int,  # 结果行数
            "error": str       # 仅失败时
        }
    """
    # 安全检查：只允许 SELECT / WITH (CTE) 查询
    stripped = sql.strip().upper()
    if not (stripped.startswith("SELECT") or stripped.startswith("WITH")):
        return {
            "success": False,
            "error": "安全限制：仅允许执行 SELECT 查询语句",
            "columns": [],
            "rows": [],
            "row_count": 0,
        }

    # 禁止危险关键字
    dangerous = [
        "DROP",
        "DELETE",
        "UPDATE",
        "INSERT",
        "ALTER",
        "TRUNCATE",
        "CREATE",
        "GRANT",
        "REVOKE",
    ]
    for kw in dangerous:
        # 检查是否作为独立关键字出现（不在引号内的简单检查）
        if f" {kw} " in f" {stripped} ":
            return {
                "success": False,
                "error": f"安全限制：查询中不允许包含 {kw} 操作",
                "columns": [],
                "rows": [],
                "row_count": 0,
            }

    try:
        with get_connection() as conn:
            with conn.cursor() as cursor:
                cursor.execute(sql)
                rows = cursor.fetchall()
                columns = (
                    [desc[0] for desc in cursor.description]
                    if cursor.description
                    else []
                )
                return {
                    "success": True,
                    "columns": columns,
                    "rows": rows,
                    "row_count": len(rows),
                }
    except Exception as e:
        return {
            "success": False,
            "error": f"SQL 执行错误: {str(e)}",
            "columns": [],
            "rows": [],
            "row_count": 0,
        }


def test_connection() -> bool:
    """测试数据库连接是否正常"""
    try:
        with get_connection() as conn:
            with conn.cursor() as cursor:
                cursor.execute("SELECT 1")
                return True
    except Exception:
        return False
