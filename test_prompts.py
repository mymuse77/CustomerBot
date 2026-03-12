#!/usr/bin/env python3
"""测试提示词配置和热重载功能"""

import sys
import time

sys.path.insert(0, "D:\\AI\\Git\\CustomerBot")

from app.config_manager import ConfigManager
from app.prompts import (
    get_system_prompt,
    get_answer_system_prompt,
    format_answer_prompt,
    format_error_prompt,
    reload_prompts,
    register_prompt_change_callback,
)


def test_config_loading():
    """测试配置加载"""
    print("=" * 50)
    print("测试配置加载")
    print("=" * 50)

    manager = ConfigManager()
    config = manager.load_yaml("prompts.yaml")

    print(f"✓ 配置加载成功")
    print(f"  - 包含键: {list(config.keys())}")
    print()


def test_prompt_functions():
    """测试提示词函数"""
    print("=" * 50)
    print("测试提示词函数")
    print("=" * 50)

    # 测试系统提示词
    system_prompt = get_system_prompt()
    print(f"✓ get_system_prompt() 返回长度: {len(system_prompt)} 字符")

    # 测试回答系统提示词
    answer_prompt = get_answer_system_prompt()
    print(f"✓ get_answer_system_prompt() 返回长度: {len(answer_prompt)} 字符")

    # 测试格式化函数
    result = format_answer_prompt(question="测试问题", result="测试数据")
    print(f"✓ format_answer_prompt() 返回长度: {len(result)} 字符")

    result = format_error_prompt(question="测试问题", error="测试错误")
    print(f"✓ format_error_prompt() 返回长度: {len(result)} 字符")
    print()


def test_hot_reload():
    """测试热重载功能"""
    print("=" * 50)
    print("测试热重载功能")
    print("=" * 50)

    from app.config_manager import get_config_manager

    manager = get_config_manager()

    # 注册回调
    callback_triggered = False

    def on_change(event):
        nonlocal callback_triggered
        callback_triggered = True
        print(f"✓ 配置变更回调触发: {event}")

    register_prompt_change_callback(on_change)
    print("✓ 已注册配置变更回调")

    # 启动监控（轮询模式，便于测试）
    manager.start_watching(["prompts.yaml"], interval=1.0)
    print("✓ 已启动配置监控 (轮询模式)")

    print()
    print("提示: 修改 config/prompts.yaml 文件，观察回调是否触发")
    print("等待 10 秒，期间可以修改配置文件...")
    print()

    for i in range(10, 0, -1):
        print(f"  倒计时: {i} 秒", end="\r")
        time.sleep(1)

    print()

    if callback_triggered:
        print("✓ 热重载测试成功！配置变更已检测")
    else:
        print("○ 未检测到配置变更（未修改文件或监控延迟）")

    manager.stop_watching()
    print("✓ 已停止配置监控")
    print()


def test_manual_reload():
    """测试手动重新加载"""
    print("=" * 50)
    print("测试手动重新加载")
    print("=" * 50)

    reload_prompts()
    print("✓ 手动重新加载成功")
    print()


if __name__ == "__main__":
    try:
        test_config_loading()
        test_prompt_functions()
        test_manual_reload()
        test_hot_reload()

        print("=" * 50)
        print("所有测试完成！")
        print("=" * 50)
        print()
        print("使用说明:")
        print("1. 提示词配置文件: config/prompts.yaml")
        print("2. 修改配置文件后会自动热重载（无需重启服务）")
        print("3. 也可以通过 reload_prompts() 手动刷新")
        print()

    except Exception as e:
        print(f"✗ 测试失败: {e}")
        import traceback

        traceback.print_exc()
        sys.exit(1)
