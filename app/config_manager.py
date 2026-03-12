"""配置热重载管理器

支持 YAML 配置文件的热重载，文件变更后自动重新加载，无需重启服务。
"""

import time
import threading
import logging
from pathlib import Path
from typing import Any, Dict, Optional, Callable, Union
from dataclasses import dataclass

# 可选依赖导入
try:
    import yaml

    HAS_YAML = True
except ImportError:
    HAS_YAML = False
    yaml = None  # type: ignore
    logging.warning("PyYAML not installed. Please install: pip install pyyaml")

try:
    from watchfiles import watch, Change

    HAS_WATCHFILES = True
except ImportError:
    HAS_WATCHFILES = False
    watch = None  # type: ignore
    Change = None  # type: ignore
    logging.warning("watchfiles not installed. Please install: pip install watchfiles")


logger = logging.getLogger(__name__)


@dataclass
class ConfigChangeEvent:
    """配置变更事件"""

    config_name: str
    change_type: str  # 'modified', 'created', 'deleted'
    timestamp: float


class ConfigManager:
    """配置管理器 - 支持热重载"""

    def __init__(self, config_dir: Optional[Union[str, Path]] = None):
        """
        初始化配置管理器

        Args:
            config_dir: 配置文件目录，默认为项目根目录下的 config 目录
        """
        if config_dir is None:
            # 获取项目根目录
            current_file = Path(__file__).resolve()
            project_root = current_file.parent.parent
            config_dir = project_root / "config"

        self.config_dir: Path = Path(config_dir) if config_dir else Path(".")
        self._configs: Dict[str, Dict[str, Any]] = {}
        self._last_modified: Dict[str, float] = {}
        self._lock = threading.RLock()
        self._watch_thread: Optional[threading.Thread] = None
        self._stop_event = threading.Event()
        self._callbacks: Dict[str, list] = {}

        logger.info(f"ConfigManager initialized with config_dir: {self.config_dir}")

    def load_yaml(self, filename: str) -> Dict[str, Any]:
        """
        加载 YAML 配置文件

        Args:
            filename: 配置文件名（不含路径）

        Returns:
            配置字典
        """
        if not HAS_YAML:
            raise ImportError("PyYAML is required. Install: pip install pyyaml")

        config_path = self.config_dir / filename

        try:
            with open(config_path, "r", encoding="utf-8") as f:
                config = yaml.safe_load(f)  # type: ignore

            with self._lock:
                self._configs[filename] = config
                self._last_modified[filename] = config_path.stat().st_mtime

            logger.info(f"Loaded config: {filename}")
            return config

        except FileNotFoundError:
            logger.error(f"Config file not found: {config_path}")
            raise
        except Exception as e:
            logger.error(f"YAML parse error in {filename}: {e}")
            raise

    def get_config(self, filename: str, reload: bool = False) -> Dict[str, Any]:
        """
        获取配置

        Args:
            filename: 配置文件名
            reload: 是否强制重新加载

        Returns:
            配置字典
        """
        with self._lock:
            if filename not in self._configs or reload:
                return self.load_yaml(filename)
            return self._configs[filename]

    def get_prompt(self, config_name: str, prompt_key: str, **kwargs) -> str:
        """
        获取提示词模板并渲染变量

        Args:
            config_name: 配置文件名（如 'prompts.yaml'）
            prompt_key: 提示词键名（如 'system_prompt'）
            **kwargs: 模板变量

        Returns:
            渲染后的提示词字符串
        """
        config = self.get_config(config_name)

        if prompt_key not in config:
            raise KeyError(f"Prompt key '{prompt_key}' not found in {config_name}")

        prompt_template = config[prompt_key]

        # 如果是字符串，直接格式化
        if isinstance(prompt_template, str):
            try:
                return prompt_template.format(**kwargs)
            except KeyError as e:
                logger.warning(f"Missing template variable {e} in {prompt_key}")
                return prompt_template

        # 如果是其他类型，返回字符串表示
        return str(prompt_template)

    def check_reload(self, filename: str) -> bool:
        """
        检查文件是否需要重新加载

        Args:
            filename: 配置文件名

        Returns:
            是否重新加载了文件
        """
        config_path = self.config_dir / filename

        if not config_path.exists():
            return False

        current_mtime = config_path.stat().st_mtime

        with self._lock:
            last_mtime = self._last_modified.get(filename, 0)

            if current_mtime > last_mtime:
                logger.info(f"Config file changed: {filename}, reloading...")
                self.load_yaml(filename)
                self._notify_callbacks(filename, "modified")
                return True

        return False

    def register_callback(
        self, filename: str, callback: Callable[[ConfigChangeEvent], None]
    ):
        """
        注册配置变更回调函数

        Args:
            filename: 监控的配置文件名
            callback: 回调函数，接收 ConfigChangeEvent 参数
        """
        with self._lock:
            if filename not in self._callbacks:
                self._callbacks[filename] = []
            self._callbacks[filename].append(callback)

        logger.info(f"Registered callback for {filename}")

    def _notify_callbacks(self, filename: str, change_type: str):
        """通知所有回调函数"""
        event = ConfigChangeEvent(
            config_name=filename, change_type=change_type, timestamp=time.time()
        )

        with self._lock:
            callbacks = self._callbacks.get(filename, [])

        for callback in callbacks:
            try:
                callback(event)
            except Exception as e:
                logger.error(f"Callback error for {filename}: {e}")

    def start_watching(self, filenames: list, interval: float = 1.0):
        """
        启动文件监控线程（轮询模式）

        Args:
            filenames: 要监控的文件名列表
            interval: 检查间隔（秒）
        """
        if self._watch_thread and self._watch_thread.is_alive():
            logger.warning("Watch thread already running")
            return

        self._stop_event.clear()

        def watch_loop():
            logger.info(f"Started watching configs: {filenames}")
            while not self._stop_event.is_set():
                for filename in filenames:
                    try:
                        self.check_reload(filename)
                    except Exception as e:
                        logger.error(f"Error checking {filename}: {e}")

                # 等待 interval 秒或直到停止事件
                self._stop_event.wait(interval)

        self._watch_thread = threading.Thread(target=watch_loop, daemon=True)
        self._watch_thread.start()
        logger.info(f"Config watch thread started with interval={interval}s")

    def start_watching_native(self, filenames: list):
        """
        启动原生文件监控（使用 watchfiles，更高效）

        Args:
            filenames: 要监控的文件名列表
        """
        if not HAS_WATCHFILES:
            logger.warning("watchfiles not available, falling back to polling mode")
            self.start_watching(filenames)
            return

        if self._watch_thread and self._watch_thread.is_alive():
            logger.warning("Watch thread already running")
            return

        self._stop_event.clear()

        # 准备监控路径
        watch_paths = [str(self.config_dir / f) for f in filenames]

        def watch_loop():
            logger.info(f"Started native watching configs: {filenames}")
            try:
                for changes in watch(*watch_paths, stop_event=self._stop_event):  # type: ignore
                    for change_type, path in changes:
                        filename = Path(path).name
                        if filename in filenames:
                            if change_type == Change.modified:  # type: ignore
                                logger.info(f"Config modified: {filename}")
                                try:
                                    self.load_yaml(filename)
                                    self._notify_callbacks(filename, "modified")
                                except Exception as e:
                                    logger.error(f"Error reloading {filename}: {e}")
                            elif change_type == Change.added:  # type: ignore
                                logger.info(f"Config added: {filename}")
                                self._notify_callbacks(filename, "created")
                            elif change_type == Change.deleted:  # type: ignore
                                logger.warning(f"Config deleted: {filename}")
                                self._notify_callbacks(filename, "deleted")
            except Exception as e:
                logger.error(f"Watch loop error: {e}")

        self._watch_thread = threading.Thread(target=watch_loop, daemon=True)
        self._watch_thread.start()
        logger.info("Native config watch thread started")

    def stop_watching(self):
        """停止文件监控"""
        if self._watch_thread and self._watch_thread.is_alive():
            self._stop_event.set()
            self._watch_thread.join(timeout=2.0)
            logger.info("Config watch thread stopped")

    def __del__(self):
        """析构时停止监控"""
        self.stop_watching()


# 全局配置管理器实例
_config_manager: Optional[ConfigManager] = None


def get_config_manager() -> ConfigManager:
    """获取全局配置管理器实例（单例模式）"""
    global _config_manager
    if _config_manager is None:
        _config_manager = ConfigManager()
    return _config_manager


def init_config_manager(config_dir: Optional[str] = None) -> ConfigManager:
    """初始化配置管理器"""
    global _config_manager
    _config_manager = ConfigManager(config_dir)
    return _config_manager
