@echo off
REM 打包 MarkItDownGUI（文件夹模式，启动快，带自定义图标）
setlocal
chcp 65001 >nul

cd /d "%~dp0"

REM 使用项目虚拟环境（Python 3.12）
if not exist ".venv\Scripts\python.exe" (
    echo [错误] 未找到 .venv，请先创建并安装依赖：uv venv --python 3.12 .venv && uv pip install -e "packages/markitdown[all]"
    pause
    exit /b 1
)

call ".venv\Scripts\activate.bat"

echo [1/4] 生成程序图标 ...
python make_icon.py
if errorlevel 1 (
    echo [错误] 生成图标失败
    pause
    exit /b 1
)

echo [2/4] 安装打包工具 pyinstaller 和 tkinterdnd2 ...
python -m pip install --quiet pyinstaller tkinterdnd2
if errorlevel 1 (
    echo [错误] 安装打包工具失败
    pause
    exit /b 1
)

echo [3/4] 开始打包（文件夹模式，首次打包需数分钟）...
pyinstaller --noconfirm --clean --onedir --windowed ^
    --name MarkItDownGUI ^
    --icon icon.ico ^
    --collect-data tkinterdnd2 ^
    --collect-data magika ^
    markitdown_gui.py
if errorlevel 1 (
    echo [错误] 打包失败
    pause
    exit /b 1
)

echo.
echo [4/4] 打包完成！
echo 程序位于：dist\MarkItDownGUI\MarkItDownGUI.exe
echo 说明：dist\MarkItDownGUI\ 为整个程序目录，分发时请整体拷贝该文件夹。
pause
