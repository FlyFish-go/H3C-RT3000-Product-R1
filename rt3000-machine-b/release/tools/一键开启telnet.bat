@echo off
chcp 65001 >nul
setlocal

REM ============================================================
REM  RT3000 一键开启 telnet
REM  双击运行；也可以把 .cfg 文件拖到本文件上
REM ============================================================

set "PS1=%~dp0RT3000-开启telnet.ps1"

if not exist "%PS1%" (
    echo.
    echo   [错误] 找不到脚本文件：
    echo          %PS1%
    echo.
    echo   请确认 RT3000-开启telnet.ps1 和本文件在同一个文件夹里。
    echo.
    pause
    exit /b 1
)

REM 传参：如果用户把 cfg 拖到 bat 上，%1 就是那个文件
powershell -NoProfile -ExecutionPolicy Bypass -File "%PS1%" %*

if errorlevel 1 (
    echo.
    echo   脚本异常退出。
    pause
)
