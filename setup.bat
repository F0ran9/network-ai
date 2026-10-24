@echo off
chcp 65001 >nul
title Network Config Generator — 一键启动

echo ========================================
echo   Network Config Generator v1.0
echo ========================================
echo.

cd /d "%~dp0"

:: ========== 1. Python 虚拟环境 ==========
if not exist "backend\venv\Scripts\python.exe" (
    echo [1/5] 创建 Python 虚拟环境...
    python -m venv backend\venv
    if errorlevel 1 (
        echo [ERROR] 创建虚拟环境失败，请检查 Python 是否已安装
        pause
        exit /b 1
    )
) else (
    echo [1/5] Python 虚拟环境已存在，跳过
)

:: ========== 2. 安装后端依赖 ==========
echo [2/5] 检查后端依赖...
call backend\venv\Scripts\activate.bat
pip install -r backend\requirements.txt -q
if errorlevel 1 (
    echo [ERROR] 后端依赖安装失败
    pause
    exit /b 1
)

:: ========== 3. 检查 .env ==========
echo [3/5] 检查配置文件...
if not exist "backend\.env" (
    if exist ".env.example" (
        echo [WARNING] backend\.env 不存在，正在从 .env.example 复制...
        copy .env.example backend\.env >nul
        echo [WARNING] 请编辑 backend\.env 填入你的 API Key 后重新启动
        start notepad backend\.env
        pause
        exit /b 1
    ) else (
        echo [ERROR] 未找到 .env 配置模板
        pause
        exit /b 1
    )
)

:: ========== 4. 前端依赖与构建 ==========
echo [4/5] 检查前端...
if not exist "frontend\node_modules" (
    echo   安装前端依赖...
    cd frontend
    call npm install
    cd ..
)
if not exist "frontend\dist\index.html" (
    echo   构建前端...
    cd frontend
    call npx vite build
    cd ..
)

:: ========== 5. 启动服务 ==========
echo [5/5] 启动服务...
echo.
echo   地址: http://localhost:5732
echo   按 Ctrl+C 停止
echo.

start "" http://localhost:5732
cd backend
python main.py

pause
