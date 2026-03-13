"""请求/响应数据模型"""

from pydantic import BaseModel, Field
from typing import Optional, Any, Literal


class ChatRequest(BaseModel):
    """用户聊天请求"""

    question: str = Field(..., min_length=1, max_length=500, description="用户问题")


class CameraInfo(BaseModel):
    """摄像机信息（用于视频/图片请求）"""

    id: int = Field(..., description="摄像机ID")
    name: str = Field(..., description="摄像机名称")
    online_status: int = Field(..., description="在线状态")
    check_time: str = Field(..., description="最后检查时间")


class MediaContent(BaseModel):
    """媒体内容（视频或图片）"""

    type: Literal["video", "image"] = Field(..., description="媒体类型")
    camera_id: int = Field(..., description="关联的摄像机ID")
    camera_name: str = Field(..., description="摄像机名称")
    url: str = Field(..., description="媒体URL")
    thumbnail_time: Optional[float] = Field(None, description="图片/截图的随机时间点")


class ChatResponse(BaseModel):
    """聊天响应"""

    answer: str = Field(..., description="自然语言回答")
    sql: Optional[str] = Field(None, description="生成的 SQL（调试用）")
    data: Optional[list[dict[str, Any]]] = Field(None, description="查询结果原始数据")
    success: bool = Field(True, description="是否成功")
    error: Optional[str] = Field(None, description="错误信息")
    # 新增：媒体内容（视频/图片）
    media: Optional[MediaContent] = Field(None, description="媒体内容（视频/图片）")


class HealthResponse(BaseModel):
    """健康检查响应"""

    status: str
    db_connected: bool
    sensevoice_connected: Optional[bool] = Field(
        None, description="SenseVoice 服务连接状态"
    )


class ScreenshotRequest(BaseModel):
    """截图请求"""

    camera_id: int = Field(..., description="摄像机ID")
    camera_name: str = Field(..., description="摄像机名称")
    timestamp: Optional[float] = Field(
        None, description="视频中的时间点（秒），随机如果为空"
    )


class ScreenshotResponse(BaseModel):
    """截图响应"""

    success: bool
    image_data: Optional[str] = Field(None, description="Base64编码的图片数据")
    camera_id: int
    camera_name: str
    timestamp: float
    error: Optional[str] = None
