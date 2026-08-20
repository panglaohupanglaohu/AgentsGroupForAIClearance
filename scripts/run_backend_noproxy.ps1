# 启动后端并清除继承的代理变量（本机 127.0.0.1:1080 代理常已停机，会导致所有外部 RSS 抓取失败）
$ErrorActionPreference = 'Continue'
$root = Split-Path -Parent $PSScriptRoot

foreach ($name in 'HTTP_PROXY','HTTPS_PROXY','http_proxy','https_proxy','ALL_PROXY','all_proxy') {
    [Environment]::SetEnvironmentVariable($name, $null, 'Process')
}
$env:NO_PROXY = '*'
$env:PYTHONIOENCODING = 'utf-8'

$py = Join-Path $root '.venv\Scripts\python.exe'
if (-not (Test-Path $py)) { $py = 'python' }

Set-Location (Join-Path $root 'src\backend')
& $py main.py --port 8080
