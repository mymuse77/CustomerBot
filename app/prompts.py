"""Text2SQL 提示词模板 - 支持热重载

提示词配置从外部 YAML 文件加载，支持热重载。
修改 config/prompts.yaml 后无需重启服务立即生效。
"""

import logging
from typing import Optional

from app.config import DB_SCHEMA
from app.config_manager import get_config_manager, ConfigManager

logger = logging.getLogger(__name__)

# 配置文件名
PROMPTS_CONFIG_FILE = "prompts.yaml"

# 获取配置管理器实例
_config_manager: Optional[ConfigManager] = None


def _get_config_manager() -> ConfigManager:
    """获取或初始化配置管理器"""
    global _config_manager
    if _config_manager is None:
        _config_manager = get_config_manager()
        # 启动热重载监控
        try:
            _config_manager.start_watching_native([PROMPTS_CONFIG_FILE])
            logger.info(f"Started hot-reload watching for {PROMPTS_CONFIG_FILE}")
        except Exception as e:
            logger.warning(
                f"Failed to start native watching, falling back to polling: {e}"
            )
            _config_manager.start_watching([PROMPTS_CONFIG_FILE], interval=2.0)
    return _config_manager


def get_system_prompt() -> str:
    """
    获取系统提示词（支持热重载）

    Returns:
        系统提示词字符串，包含数据库 schema 和业务知识
    """
    try:
        manager = _get_config_manager()
        return manager.get_prompt(
            PROMPTS_CONFIG_FILE, "system_prompt", db_schema=DB_SCHEMA
        )
    except Exception as e:
        logger.error(f"Failed to load system_prompt from config: {e}")
        # 返回默认提示词作为后备
        return _get_default_system_prompt()


def get_answer_system_prompt() -> str:
    """
    获取回答系统提示词（支持热重载）

    Returns:
        回答系统提示词字符串
    """
    try:
        manager = _get_config_manager()
        return manager.get_prompt(PROMPTS_CONFIG_FILE, "answer_system_prompt")
    except Exception as e:
        logger.error(f"Failed to load answer_system_prompt from config: {e}")
        return _get_default_answer_system_prompt()


def get_answer_user_template() -> str:
    """
    获取回答用户模板（支持热重载）

    Returns:
        回答用户模板字符串
    """
    try:
        manager = _get_config_manager()
        return manager.get_prompt(PROMPTS_CONFIG_FILE, "answer_user_template")
    except Exception as e:
        logger.error(f"Failed to load answer_user_template from config: {e}")
        return _get_default_answer_user_template()


def get_error_answer_template() -> str:
    """
    获取错误回答模板（支持热重载）

    Returns:
        错误回答模板字符串
    """
    try:
        manager = _get_config_manager()
        return manager.get_prompt(PROMPTS_CONFIG_FILE, "error_answer_template")
    except Exception as e:
        logger.error(f"Failed to load error_answer_template from config: {e}")
        return _get_default_error_answer_template()


def format_answer_prompt(question: str, result: str) -> str:
    """
    格式化回答提示词

    Args:
        question: 用户问题
        result: 查询结果

    Returns:
        格式化后的提示词
    """
    template = get_answer_user_template()
    try:
        return template.format(question=question, result=result)
    except Exception as e:
        logger.error(f"Failed to format answer prompt: {e}")
        return f"用户问题: {question}\n\n查询结果:\n{result}\n\n请用友好的中文自然语言回答用户的问题。"


def format_error_prompt(question: str, error: str) -> str:
    """
    格式化错误提示词

    Args:
        question: 用户问题
        error: 错误信息

    Returns:
        格式化后的提示词
    """
    template = get_error_answer_template()
    try:
        return template.format(question=question, error=error)
    except Exception as e:
        logger.error(f"Failed to format error prompt: {e}")
        return f"用户问题: {question}\n\n查询执行出现了错误: {error}\n\n请用友好的语言告知用户查询出现了问题，并建议用户换一种方式提问。"


def reload_prompts():
    """
    手动重新加载提示词配置

    用于手动刷新配置，无需等待自动热重载
    """
    try:
        manager = _get_config_manager()
        manager.load_yaml(PROMPTS_CONFIG_FILE)
        logger.info("Prompts manually reloaded")
    except Exception as e:
        logger.error(f"Failed to reload prompts: {e}")


def register_prompt_change_callback(callback):
    """
    注册提示词变更回调函数

    Args:
        callback: 回调函数，接收 ConfigChangeEvent 参数
    """
    try:
        manager = _get_config_manager()
        manager.register_callback(PROMPTS_CONFIG_FILE, callback)
        logger.info("Registered prompt change callback")
    except Exception as e:
        logger.error(f"Failed to register callback: {e}")


# ============================================================================
# 默认提示词（配置加载失败时的后备）
# ============================================================================


def _get_default_system_prompt() -> str:
    """默认系统提示词"""
    return f"""你是一个视频监控平台的智能数据分析助手。你的任务是将用户的自然语言问题转换为 MySQL SQL 查询语句。

{DB_SCHEMA}

## 基本规则

1. 只生成 SELECT 语句，不要生成任何修改数据的语句
2. 使用标准 MySQL 语法
3. 结果列名使用中文别名
4. 数值计算保留 2 位小数

## 视频/图片请求标记

- 视频请求：SQL末尾添加 `-- VIDEO_REQUEST`
- 图片请求：SQL末尾添加 `-- IMAGE_REQUEST`

只输出纯 SQL 语句，不要包含任何解释或 markdown 标记。
"""


def _get_default_answer_system_prompt() -> str:
    """默认回答系统提示词"""
    return """你是一个视频监控平台的智能数据分析助手。请根据用户的问题和数据库查询结果，用自然、友好的中文回答用户。

1. 用通俗易懂的语言总结查询结果
2. 如果有表格数据，用清晰的格式展示
3. 回答要简洁有条理，可以适当使用 emoji
4. 回答使用 Markdown 格式
"""


def _get_default_answer_user_template() -> str:
    """默认回答用户模板"""
    return """用户问题: {question}

执行的查询返回了以下结果:
{result}

请用友好的中文自然语言回答用户的问题。"""


def _get_default_error_answer_template() -> str:
    """默认错误回答模板"""
    return """用户问题: {question}

查询执行出现了错误: {error}

请用友好的语言告知用户查询出现了问题，并建议用户换一种方式提问。"""


# ============================================================================
# 向后兼容：提供模块级别的变量（延迟加载）
# ============================================================================


class _LazyPrompt:
    """延迟加载的提示词包装器"""

    def __init__(self, getter_func):
        self._getter = getter_func
        self._cache = None

    def __str__(self):
        if self._cache is None:
            self._cache = self._getter()
        return self._cache

    def __repr__(self):
        return str(self)

    def refresh(self):
        """刷新缓存"""
        self._cache = self._getter()
        return self._cache


# 向后兼容的变量导出（实际使用时建议调用函数）
SYSTEM_PROMPT = _LazyPrompt(get_system_prompt)
ANSWER_SYSTEM_PROMPT = _LazyPrompt(get_answer_system_prompt)
ANSWER_USER_TEMPLATE = _LazyPrompt(get_answer_user_template)
ERROR_ANSWER_TEMPLATE = _LazyPrompt(get_error_answer_template)
