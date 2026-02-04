# nanobot 快速部署脚本 (Windows PowerShell)
# 用法: .\deploy.ps1  或  pwsh -File deploy.ps1

$ErrorActionPreference = "Stop"
$ProjectRoot = $PSScriptRoot
$NanobotDir = Join-Path $env:USERPROFILE ".nanobot"

Write-Host "=== nanobot 部署 ===" -ForegroundColor Cyan
Set-Location $ProjectRoot

# 1. 安装依赖
Write-Host "`n[1/3] 安装 Python 包..." -ForegroundColor Yellow
pip install -e . 2>&1 | Out-Null
if ($LASTEXITCODE -ne 0) { pip install -e .; exit 1 }
Write-Host "  完成" -ForegroundColor Green

# 2. 初始化配置与工作区
Write-Host "`n[2/3] 初始化配置 (nanobot onboard)..." -ForegroundColor Yellow
& nanobot onboard
if ($LASTEXITCODE -ne 0) { exit 1 }

# 3. 提示编辑配置
Write-Host "`n[3/3] 下一步:" -ForegroundColor Yellow
Write-Host "  1. 编辑配置文件，填入 API Key:"
Write-Host "     $NanobotDir\config.json" -ForegroundColor White
Write-Host "     获取密钥: https://openrouter.ai/keys"
Write-Host "  2. 命令行对话: nanobot agent -m `"你好`""
Write-Host "  3. 交互模式:   nanobot agent"
Write-Host "  4. 启动网关:   nanobot gateway (需先在 config 中启用 telegram/whatsapp)"
Write-Host "`n详细说明见 DEPLOY.md" -ForegroundColor Cyan
