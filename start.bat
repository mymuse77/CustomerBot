@echo off
chcp 65001 >nul
title 视频监控数字人 - 启动脚本

echo ========================================
echo   视频监控数字人 - Windows 快速启动
echo ========================================
echo.

:: 检查 Python 是否安装
python --version >nul 2>&1
if errorlevel 1 (
    echo [错误] 未检测到 Python，请先安装 Python 3.10+
    echo 下载地址: https://www.python.org/downloads/
    pause
    exit /b 1
)

echo [1/3] 检查 Python 版本...
python --version

echo.
echo [2/3] 安装依赖...
pip install -r requirements.txt

if errorlevel 1 (
    echo [错误] 依赖安装失败，请检查网络连接
    pause
    exit /b 1
)

echo.
echo [3/3] 启动服务...
echo ========================================
echo.
echo 服务启动成功后，浏览器访问: http://localhost:8000
echo 按 Ctrl+C 停止服务
echo.
echo ========================================
echo.

:: 启动服务
python run.py