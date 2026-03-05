#!/bin/bash

# ========================================
#   视频监控数字人 - Linux/macOS 快速启动
# ========================================

set -e

echo "========================================"
echo "  视频监控数字人 - Linux 快速启动"
echo "========================================"
echo ""

# 检查 Python
if ! command -v python3 &> /dev/null; then
    echo "[错误] 未检测到 Python，请先安装 Python 3.10+"
    echo "Ubuntu/Debian: sudo apt install python3 python3-pip"
    echo "CentOS/RHEL:   sudo yum install python3 python3-pip"
    exit 1
fi

# 使用 python3 或 python
PYTHON_CMD="python"
command -v python &> /dev/null || PYTHON_CMD="python3"

echo "[1/3] 检查 Python 版本..."
$PYTHON_CMD --version

echo ""
echo "[2/3] 安装依赖..."
$PYTHON_CMD -m pip install -r requirements.txt

echo ""
echo "[3/3] 启动服务..."
echo "========================================"
echo ""
echo "服务启动成功后，浏览器访问: http://localhost:8000"
echo "按 Ctrl+C 停止服务"
echo ""
echo "========================================"
echo ""

# 启动服务
$PYTHON_CMD run.py