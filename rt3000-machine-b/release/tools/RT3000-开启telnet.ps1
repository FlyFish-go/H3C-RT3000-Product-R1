# ============================================================
#  RT3000 一键开启 telnet
#  把原厂后台导出的配置备份 (.cfg) 改成「已开启 telnet」的版本
#
#  用法：把 RT3000 的 .cfg 备份文件拖到本脚本上，或双击后按提示选择
# ============================================================

$ErrorActionPreference = "Stop"
$OutputEncoding = [System.Text.UTF8Encoding]::new($false)
[Console]::OutputEncoding = [System.Text.UTF8Encoding]::new($false)

function Write-Title($text) {
    Write-Host ""
    Write-Host "============================================================" -ForegroundColor Cyan
    Write-Host "  $text" -ForegroundColor Cyan
    Write-Host "============================================================" -ForegroundColor Cyan
}
function Write-OK($text)   { Write-Host "  [OK]   $text" -ForegroundColor Green }
function Write-Err($text)  { Write-Host "  [错误] $text" -ForegroundColor Red }
function Write-Warn($text) { Write-Host "  [注意] $text" -ForegroundColor Yellow }
function Write-Info($text) { Write-Host "         $text" -ForegroundColor Gray }

Write-Title "RT3000 一键开启 telnet"

# ---------- 1. 取得输入文件 ----------
$inFile = $null
if ($args.Count -ge 1) {
    $inFile = $args[0]
} else {
    Write-Host ""
    Write-Host "  请把 RT3000 后台导出的配置文件（.cfg）拖到本窗口，然后回车：" -ForegroundColor White
    Write-Host "  （或者直接在这里输入文件的完整路径）" -ForegroundColor Gray
    Write-Host ""
    $userInput = Read-Host "  文件"
    $inFile = $userInput.Trim('"').Trim()
}

if ([string]::IsNullOrWhiteSpace($inFile)) {
    Write-Err "没有提供文件。"
    Read-Host "按回车退出"; exit 1
}
if (-not (Test-Path -LiteralPath $inFile)) {
    Write-Err "找不到文件：$inFile"
    Read-Host "按回车退出"; exit 1
}
$inFile = (Resolve-Path -LiteralPath $inFile).Path
Write-OK "输入文件：$inFile"

# ---------- 2. 读入并做基本检查 ----------
$raw = [System.IO.File]::ReadAllBytes($inFile)
Write-Info ("文件大小：{0} 字节" -f $raw.Length)

# 查 BOM（前 3 字节 EF BB BF）
if ($raw.Length -ge 3 -and $raw[0] -eq 0xEF -and $raw[1] -eq 0xBB -and $raw[2] -eq 0xBF) {
    Write-Err "这个文件带 UTF-8 BOM（文件头是 EF BB BF），不是原厂导出的原始文件。"
    Write-Info "请重新从设备后台「备份」导出一份，不要用记事本另存过。"
    Read-Host "按回车退出"; exit 1
}

# 找第 1 行换行符
$nl = [Array]::IndexOf($raw, [byte]10)
if ($nl -lt 32) {
    Write-Err "文件格式不对：找不到第 1 行的换行符，或者第 1 行太短。"
    Write-Info "请确认这是 RT3000 后台导出的 .cfg 文件。"
    Read-Host "按回车退出"; exit 1
}

# 检查第 1 行结构：<32位md5>  <路径>
$headBytes = $raw[0..($nl-1)]
$headText  = [System.Text.Encoding]::ASCII.GetString($headBytes)
$headMd5   = $headText.Substring(0, 32)

if ($headMd5 -notmatch '^[0-9a-fA-F]{32}$') {
    Write-Err "文件格式不对：第 1 行开头不是 32 位 MD5。"
    Write-Info "实际内容：$headText"
    Read-Host "按回车退出"; exit 1
}
Write-OK "头部 MD5 格式正确：$headMd5"

# ---------- 3. 校验原文件完整性 ----------
$payload = New-Object byte[] ($raw.Length - $nl - 1)
[Array]::Copy($raw, $nl + 1, $payload, 0, $payload.Length)

$md5 = [System.Security.Cryptography.MD5]::Create()
$calcHash = ($md5.ComputeHash($payload) | ForEach-Object { $_.ToString("x2") }) -join ""

if ($calcHash -ne $headMd5.ToLower()) {
    Write-Err "原文件校验失败，说明文件已经损坏或被改动过。"
    Write-Info "头部声明：$($headMd5.ToLower())"
    Write-Info "实际计算：$calcHash"
    Write-Info "请重新从设备后台「备份」导出一份。"
    Read-Host "按回车退出"; exit 1
}
Write-OK "原文件完整性校验通过"

# ---------- 4. 检查是否已经开过 ----------
$payloadText = [System.Text.Encoding]::ASCII.GetString($payload)

# 只认 key=value，不依赖行首缩进是 TAB 还是空格（不同固件版本可能不同）
$keyName    = "telnetenable="
$valOff     = "disable"
$valOn      = "enable"
$needleOff  = $keyName + $valOff
$needleOn   = $keyName + $valOn

$countOff = ([regex]::Matches($payloadText, [regex]::Escape($needleOff))).Count
$countOn  = ([regex]::Matches($payloadText, [regex]::Escape($needleOn))).Count

if ($countOff -eq 0 -and $countOn -eq 1) {
    Write-Warn "这个文件里 telnet 已经是开启状态了，不需要再改。"
    Write-Info "如果你还没导入过，可以直接用它去恢复配置。"
    Read-Host "按回车退出"; exit 0
}

if ($countOff -eq 0 -and $countOn -eq 0) {
    Write-Err "没有在文件里找到开启 telnet 所需的配置项（telnetenable）。"
    Write-Info "可能原因："
    Write-Info "  1. 这不是 RT3000 原厂固件的备份文件"
    Write-Info "  2. 设备固件版本不同，配置项名称不一样"
    Write-Info "  3. 文件被别的工具改过"
    Read-Host "按回车退出"; exit 1
}
if ($countOff -ne 1 -or $countOn -ne 0) {
    Write-Err "telnetenable 状态不唯一：disable=$countOff，enable=$countOn；预期恰好一处 disable。"
    Write-Info "请重新从原厂后台导出配置，不修改有歧义的文件。"
    Read-Host "按回车退出"; exit 1
}
Write-OK "找到目标配置项（telnetenable=disable）"

# ---------- 5. 执行替换 ----------
# 只替换值部分（disable -> enable），保留行首缩进原样，避免破坏格式
$needleOffBytes = [System.Text.Encoding]::ASCII.GetBytes($needleOff)
$needleOnBytes  = [System.Text.Encoding]::ASCII.GetBytes($needleOn)

# 在字节层面查找第一个匹配位置
$pos = -1
for ($i = 0; $i -le $payload.Length - $needleOffBytes.Length; $i++) {
    $match = $true
    for ($j = 0; $j -lt $needleOffBytes.Length; $j++) {
        if ($payload[$i + $j] -ne $needleOffBytes[$j]) { $match = $false; break }
    }
    if ($match) { $pos = $i; break }
}
if ($pos -lt 0) {
    Write-Err "内部错误：定位失败。"
    Read-Host "按回车退出"; exit 1
}

# enable 比 disable 少 1 字节，重建数组（不能用「补空格」的方式，那会污染配置值）
$newPayload = New-Object byte[] ($payload.Length - 1)
[Array]::Copy($payload, 0, $newPayload, 0, $pos)
[Array]::Copy($needleOnBytes, 0, $newPayload, $pos, $needleOnBytes.Length)
$tailStart = $pos + $needleOffBytes.Length
$tailLen   = $payload.Length - $tailStart
[Array]::Copy($payload, $tailStart, $newPayload, $pos + $needleOnBytes.Length, $tailLen)

# 重新算 MD5
$md5b = [System.Security.Cryptography.MD5]::Create()
$newHash = ($md5b.ComputeHash($newPayload) | ForEach-Object { $_.ToString("x2") }) -join ""

Write-OK "内容已修改（telnetenable: disable -> enable）"
Write-Info "新 MD5：$newHash"

# ---------- 6. 组装输出 ----------
# <新MD5(32字符)> + 原第1行剩余部分(从第32字符到换行) + 新载荷
$headRemainder = New-Object byte[] ($nl - 32 + 1)
[Array]::Copy($raw, 32, $headRemainder, 0, $headRemainder.Length)

$newHashBytes = [System.Text.Encoding]::ASCII.GetBytes($newHash)
$out = New-Object byte[] ($newHashBytes.Length + $headRemainder.Length + $newPayload.Length)
[Array]::Copy($newHashBytes,    0, $out, 0, $newHashBytes.Length)
[Array]::Copy($headRemainder,   0, $out, $newHashBytes.Length, $headRemainder.Length)
[Array]::Copy($newPayload,      0, $out, $newHashBytes.Length + $headRemainder.Length, $newPayload.Length)

# ---------- 7. 自校验 ----------
$nl2 = [Array]::IndexOf($out, [byte]10)
$checkPayload = New-Object byte[] ($out.Length - $nl2 - 1)
[Array]::Copy($out, $nl2 + 1, $checkPayload, 0, $checkPayload.Length)
$md5c = [System.Security.Cryptography.MD5]::Create()
$checkHash = ($md5c.ComputeHash($checkPayload) | ForEach-Object { $_.ToString("x2") }) -join ""
$outHeadMd5 = [System.Text.Encoding]::ASCII.GetString($out[0..31])

if ($checkHash -ne $outHeadMd5) {
    Write-Err "自校验失败，输出文件不可信，已中止。"
    Read-Host "按回车退出"; exit 1
}
Write-OK "输出文件自校验通过"

# ---------- 8. 写出 ----------
$dir  = Split-Path -Parent $inFile
$base = [System.IO.Path]::GetFileNameWithoutExtension($inFile)
$outFile = Join-Path $dir ($base + "-telnet.cfg")

$n = 1
while (Test-Path -LiteralPath $outFile) {
    $outFile = Join-Path $dir ($base + "-telnet($n).cfg")
    $n++
}

[System.IO.File]::WriteAllBytes($outFile, $out)

# 写后复核：确认没有 BOM，且能读回
$verify = [System.IO.File]::ReadAllBytes($outFile)
if ($verify.Length -ge 3 -and $verify[0] -eq 0xEF -and $verify[1] -eq 0xBB -and $verify[2] -eq 0xBF) {
    Write-Err "写出后检测到 BOM，文件不可用。"
    Read-Host "按回车退出"; exit 1
}
if ($verify.Length -ne $out.Length) {
    Write-Err "写出后大小不一致。"
    Read-Host "按回车退出"; exit 1
}

Write-Host ""
Write-Host "============================================================" -ForegroundColor Green
Write-Host "  完成" -ForegroundColor Green
Write-Host "============================================================" -ForegroundColor Green
Write-Host ""
Write-Host "  输出文件：" -ForegroundColor White
Write-Host "    $outFile" -ForegroundColor Yellow
Write-Host ""
Write-Host "  文件大小：$($out.Length) 字节（原 $($raw.Length) 字节）" -ForegroundColor Gray
Write-Host ""
Write-Host "  下一步：" -ForegroundColor White
Write-Host "    1. 打开 RT3000 网页后台 -> 设备管理 -> 配置管理" -ForegroundColor Gray
Write-Host "    2. 找到「从文件中恢复设置信息」" -ForegroundColor Gray
Write-Host "    3. 选择上面这个 -telnet.cfg 文件" -ForegroundColor Gray
Write-Host "    4. 点「恢复」，设备会自动重启" -ForegroundColor Gray
Write-Host "    5. 重启后即可用 telnet 登录（密码通常是 admin）" -ForegroundColor Gray
Write-Host ""
Write-Host "  原始文件没有被改动，可随时重新运行本工具。" -ForegroundColor DarkGray
Write-Host ""

Read-Host "按回车退出"
