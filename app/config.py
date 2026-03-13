"""应用配置"""

import os

# MySQL 数据库配置
DB_HOST = "127.0.0.1"
DB_PORT = 3306
DB_USER = "root"
DB_PASSWORD = "qwer~1234"
DB_NAME = "spkf"

# DeepSeek API 配置
DEEPSEEK_API_KEY = os.environ.get("DEEPSEEK_API_KEY", "")
DEEPSEEK_BASE_URL = os.environ.get("DEEPSEEK_BASE_URL", "https://api.deepseek.com")
DEEPSEEK_MODEL = os.environ.get("DEEPSEEK_MODEL", "deepseek-chat")

# SenseVoice 本地服务配置
SENSEVOICE_SERVICE_URL = os.environ.get(
    "SENSEVOICE_SERVICE_URL", "http://localhost:8000"
)

# 视频FLV源配置（主源 + 备选源）
# 注意：截图功能需要视频服务器支持 CORS 头部 (Access-Control-Allow-Origin)
FLV_VIDEO_URLS = [
    "https://sf1-cdn-tos.huoshanstatic.com/obj/media-fe/xgplayer_doc_video/mp4/xgplayer-demo-360p.mp4",
    "https://mister-ben.github.io/videojs-flvjs/bbb.flv",  # Big Buck Bunny
    "https://test-streams.mux.dev/x36xhzz/x36xhzz.m3u8",  # HLS
]


# 获取主视频源
def get_primary_video_url() -> str:
    return FLV_VIDEO_URLS[0]


# 获取所有视频源
def get_all_video_urls() -> list:
    return FLV_VIDEO_URLS


# ---------------------------------------------------------
# 基于配置管理器的热重载配置访问
# ---------------------------------------------------------

import logging
from typing import Any
from app.config_manager import get_config_manager

logger = logging.getLogger(__name__)

# 配置管理器实例
_manager = get_config_manager()


def get_app_config(key_path: str, default: Any = None) -> Any:
    """获取 app_config.yaml 中的配置项，支持点号分隔路径 (如 'app.title')"""
    try:
        config = _manager.get_config("app_config.yaml")
        keys = key_path.split(".")
        val = config
        for k in keys:
            if isinstance(val, dict) and k in val:
                val = val[k]
            else:
                return default
        return val
    except Exception as e:
        logger.warning(f"Failed to read '{key_path}' from app_config.yaml: {e}")
        return default


def get_message_template(key: str, **kwargs) -> str:
    """获取 messages.yaml 中的 ui 文案并格式化"""
    try:
        config = _manager.get_config("messages.yaml")
        template = config.get("ui", {}).get(key, "")
        if template and kwargs:
            return template.format(**kwargs)
        return template
    except Exception as e:
        logger.warning(f"Failed to load UI message '{key}': {e}")
        return ""


# 数据库表结构描述（供 Text2SQL 使用）
DB_SCHEMA = """
数据库: spkf (MySQL)

表结构如下:

1. regions - 区域信息表
   - id INT PRIMARY KEY AUTO_INCREMENT  -- 区域唯一标识
   - name VARCHAR(100) NOT NULL  -- 区域名称
   - parent_id INT DEFAULT 0  -- 父区域ID，0表示顶级区域
   - level TINYINT NOT NULL  -- 区域层级（1:省/直辖市，2:市，3:区/县，4:街道/乡镇）

2. cameras - 摄像机信息表
   - id INT PRIMARY KEY AUTO_INCREMENT  -- 摄像机唯一标识
   - name VARCHAR(100) NOT NULL  -- 摄像机名称
   - region_id INT NOT NULL  -- 所属区域ID，关联regions表id
   - online_status TINYINT NOT NULL  -- 在线状态（0:离线，1:在线）
   - check_time DATETIME NOT NULL  -- 最后状态检查时间

3. cameras_img_checks - 摄像机图片质量检测记录表
   - id INT PRIMARY KEY AUTO_INCREMENT  -- 检测记录唯一标识
   - camera_id INT NOT NULL  -- 关联摄像机ID，关联cameras表id
   - img_status TINYINT NOT NULL  -- 图片状态（0:异常，1:正常，2:模糊，3:过曝，4:欠曝）
   - check_time DATETIME NOT NULL  -- 图片检测时间

表间关系:
- cameras.region_id -> regions.id （摄像机所属区域）
- cameras_img_checks.camera_id -> cameras.id （检测记录关联摄像机）

区域表是树形结构，通过 parent_id 形成父子关系，parent_id=0 为顶级区域。
"""
