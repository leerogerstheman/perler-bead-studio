@echo off
chcp 65001 >nul
setlocal
cd /d "%~dp0"

echo ============================================================
echo   把拼豆图案生成器打包成单个 exe
echo ============================================================
echo.

set PY=
where python >nul 2>nul && set PY=python
if "%PY%"=="" (where py >nul 2>nul && set PY=py -3)
if "%PY%"=="" (
    if exist "%~dp0python\python.exe" set PY="%~dp0python\python.exe"
)
if "%PY%"=="" (
    if exist "%USERPROFILE%\.dsh\dsh-runtimes\dsh-primary-runtime\dependencies\python\python.exe" (
        set PY="%USERPROFILE%\.dsh\dsh-runtimes\dsh-primary-runtime\dependencies\python\python.exe"
    )
)
if "%PY%"=="" (
    echo [错误] 没有找到 Python，请先安装 Python 3.10+ 并勾选 Add to PATH。
    pause
    exit /b 1
)

%PY% -c "import PyInstaller" 2>nul
if errorlevel 1 (
    echo 正在安装 PyInstaller ...
    %PY% -m pip install --upgrade pyinstaller
    if errorlevel 1 (
        echo [错误] PyInstaller 安装失败，请检查网络。
        pause
        exit /b 1
    )
)

%PY% -c "import PIL, tkinter" 2>nul
if errorlevel 1 (
    echo 正在安装 Pillow ...
    %PY% -m pip install --upgrade pillow
)

echo.
echo 开始打包（第一次会比较慢，请耐心等待）...
%PY% -m PyInstaller --noconfirm --clean --windowed --onefile ^
  --name "拼豆图案生成器" ^
  --icon "%~dp0app.ico" ^
  --add-data "%~dp0app.ico;." ^
  --add-data "%~dp0app_icon.png;." ^
  --add-data "%~dp0palettes;palettes" ^
  --collect-all PIL ^
  studio.py

if errorlevel 1 (
    echo.
    echo [错误] 打包失败，请把上面的报错信息发给开发者。
    pause
    exit /b 1
)

echo.
echo ============================================================
echo   打包完成：dist\拼豆图案生成器.exe
echo   可以直接把这个 exe 拷到别的电脑用（无需安装 Python）
echo ============================================================
pause
