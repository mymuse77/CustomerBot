"""请求/响应数据模型"""

from pydantic import BaseModel, Field
from typing import Optional, Any


class ChatRequest(BaseModel):
    """用户聊天请求"""

    question: str = Field(..., min_length=1, max_length=500, description="用户问题")


class ChatResponse(BaseModel):
    """聊天响应"""

    answer: str = Field(..., description="自然语言回答")
    sql: Optional[str] = Field(None, description="生成的 SQL（调试用）")
    data: Optional[list[dict[str, Any]]] = Field(None, description="查询结果原始数据")
    success: bool = Field(True, description="是否成功")
    error: Optional[str] = Field(None, description="错误信息")


class HealthResponse(BaseModel):
    """健康检查响应"""

    status: str
    db_connected: bool
