@echo off
chcp 65001 >nul
setlocal enabledelayedexpansion

cd /d "%~dp0"

echo ============================================================
echo   RT3000 刷机 - 临时文件服务器
echo ============================================================
echo.

REM ============================================================
REM  1. 收集所有局域网 IPv4，让用户明确选择
REM ============================================================
echo [1/4] 检测本机网络地址 ...
echo.
set "N=0"
for /f "tokens=2 delims=:" %%a in ('ipconfig ^| findstr /c:"IPv4"') do (
    set "T=%%a"
    set "T=!T: =!"
    echo !T! | findstr /b "192.168." >nul && (
        set /a N+=1
        set "IP!N!=!T!"
        echo       [!N!] !T!
    )
)
if !N!==0 (
    for /f "tokens=2 delims=:" %%a in ('ipconfig ^| findstr /c:"IPv4"') do (
        set "T=%%a"
        set "T=!T: =!"
        echo !T! | findstr /b "10\." >nul && (
            set /a N+=1
            set "IP!N!=!T!"
            echo       [!N!] !T!
        )
    )
)
if !N!==0 (
    echo       [错误] 没找到局域网 IP。请确认电脑已连上路由器。
    echo.
    pause
    exit /b 1
)

echo.
if !N! GTR 1 (
    echo   ⚠ 检测到多个网络地址。请选择「和设备在同一网络」的那个。
    echo      （通常是连接 RT3000 所在路由器的网卡）
    echo.
    set /p SEL="  请输入编号 [1-!N!]: "
) else (
    set "SEL=1"
)

call set "MYIP=%%IP!SEL!%%"
if not defined MYIP (
    echo.
    echo   [错误] 选择无效。
    echo.
    pause
    exit /b 1
)
echo.
echo       已选择: !MYIP!
echo.

REM ============================================================
REM  2. 列出所有 .ubi，让用户明确选择
REM ============================================================
echo [2/4] 查找镜像文件 ...
echo.
set "M=0"
for %%f in ("*.ubi") do (
    set /a M+=1
    set "UBI!M!=%%f"
    for %%s in ("%%f") do echo       [!M!] %%f  %%~zs 字节
)
if !M!==0 (
    echo       [错误] 当前目录下没有找到 .ubi 镜像文件。
    echo              请把 QSDK 的 factory 镜像放到本目录。
    echo.
    pause
    exit /b 1
)

echo.
if !M! GTR 1 (
    echo   ⚠ 检测到多个镜像文件。请选择要写入设备的那个。
    echo      （确认方法是核对它的 SHA-256，见教程第二部分第 1 节）
    echo.
    set /p USEL="  请输入编号 [1-!M!]: "
) else (
    set "USEL=1"
)

call set "UBIFILE=%%UBI!USEL!%%"
if not defined UBIFILE (
    echo.
    echo   [错误] 选择无效。
    echo.
    pause
    exit /b 1
)
echo.
echo       已选择: !UBIFILE!
echo.

REM ============================================================
REM  3. 检查必需文件
REM ============================================================
echo [3/4] 检查文件 ...
set MISSING=0

if exist "rt3bcwrite" (
    for %%s in (rt3bcwrite) do echo       OK  rt3bcwrite  %%~zs 字节
) else (
    echo       [缺失] rt3bcwrite
    set MISSING=1
)

for %%s in ("!UBIFILE!") do echo       OK  !UBIFILE!  %%~zs 字节

if !MISSING!==1 (
    echo.
    echo [错误] 缺少 rt3bcwrite。
    echo        请把它和镜像放在本文件所在目录。
    echo.
    pause
    exit /b 1
)
echo.

REM ============================================================
REM  4. 放行防火墙
REM ============================================================
echo [4/4] 放行防火墙 8899 端口 ...
netsh advfirewall firewall delete rule name="RT3000-Flash-HTTP" >nul 2>&1
netsh advfirewall firewall add rule name="RT3000-Flash-HTTP" dir=in action=allow protocol=TCP localport=8899 >nul 2>&1
if errorlevel 1 (
    echo       [警告] 放行失败，可能需要管理员权限。
    echo       如果设备下载失败，请右键本文件 -^> 以管理员身份运行。
) else (
    echo       OK
)
echo.

REM ============================================================
REM  5. 打印设备侧命令
REM ============================================================
echo ============================================================
echo   在设备的 telnet 窗口里执行下面两条命令：
echo.
echo     cd /tmp
echo     wget http://!MYIP!:8899/rt3bcwrite -O /tmp/rt3bcwrite
echo     wget http://!MYIP!:8899/!UBIFILE! -O /tmp/factory.ubi
echo.
echo   下载完成后校验：
echo.
echo     sha256sum /tmp/rt3bcwrite /tmp/factory.ubi
echo.
echo ============================================================
echo.
echo   服务已启动。保持本窗口开着，不要关闭！
echo   刷完后按 Ctrl+C 停止，或直接关窗口。
echo   关闭后请在管理员命令提示符清理防火墙规则：
echo     netsh advfirewall firewall delete rule name="RT3000-Flash-HTTP"
echo.
echo ============================================================
echo.

where py >nul 2>&1
if not errorlevel 1 (
    py -m http.server 8899 --bind !MYIP!
) else (
    where python >nul 2>&1
    if not errorlevel 1 (
        python -m http.server 8899 --bind !MYIP!
    ) else (
        echo [错误] 没找到 Python。
        echo        请安装 Python：https://www.python.org/downloads/
        echo        安装时务必勾选 "Add Python to PATH"
        echo.
        echo   替代方案：用 HFS 等简易 HTTP 服务器，
        echo             把本目录设为根目录，端口设为 8899。
        echo.
        pause
        exit /b 1
    )
)

echo.
echo 服务已停止。
pause
