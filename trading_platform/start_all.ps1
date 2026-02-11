# Скрипт для запуска всей системы
param(
    [string]$RedisUrl = "redis://localhost:6379"
)

Write-Host "=== Запуск Trading Platform ===" -ForegroundColor Cyan

# Проверка Redis
Write-Host "`n[1/4] Проверка Redis..." -ForegroundColor Yellow
$redisRunning = $false
$test = Test-NetConnection -ComputerName localhost -Port 6379 -InformationLevel Quiet -WarningAction SilentlyContinue
if ($test) {
    $result = python -c "import redis; r = redis.Redis.from_url('$RedisUrl', socket_connect_timeout=1); r.ping(); print('OK')" 2>$null
    if ($LASTEXITCODE -eq 0) {
        $redisRunning = $true
        Write-Host "✓ Redis запущен и работает" -ForegroundColor Green
    }
}

if (-not $redisRunning) {
    Write-Host "✗ Redis не запущен!" -ForegroundColor Red
    Write-Host "  Варианты запуска Redis:" -ForegroundColor Yellow
    Write-Host "  1. Docker: docker run -d -p 6379:6379 --name redis redis:latest" -ForegroundColor White
    Write-Host "  2. WSL: wsl -e bash -c 'sudo apt install redis-server && sudo service redis-server start'" -ForegroundColor White
    Write-Host "  3. Windows: скачайте с https://github.com/microsoftarchive/redis/releases" -ForegroundColor White
    Write-Host "`n  Система будет работать, но данных не будет!" -ForegroundColor Yellow
    $continue = Read-Host "Продолжить без Redis? (y/n)"
    if ($continue -ne "y") {
        exit
    }
}

# Установка PYTHONPATH
$env:PYTHONPATH = "$PSScriptRoot"
$scriptPath = $PSScriptRoot

# Остановка старых процессов
Write-Host "`n[2/4] Остановка старых процессов..." -ForegroundColor Yellow
Get-Process python -ErrorAction SilentlyContinue | Stop-Process -Force -ErrorAction SilentlyContinue
Start-Sleep -Seconds 2

# Запуск API
Write-Host "`n[3/4] Запуск API сервера..." -ForegroundColor Yellow
$apiCmd = "cd '$scriptPath'; `$env:PYTHONPATH = '$scriptPath'; Write-Host 'API Server on http://localhost:8000' -ForegroundColor Green; python api\main.py --host 127.0.0.1 --port 8000 --redis $RedisUrl"
Start-Process powershell -ArgumentList "-NoExit", "-Command", $apiCmd
Start-Sleep -Seconds 3

# Проверка API
$apiRunning = Test-NetConnection -ComputerName 127.0.0.1 -Port 8000 -InformationLevel Quiet -WarningAction SilentlyContinue
if ($apiRunning) {
    Write-Host "✓ API запущен: http://localhost:8000" -ForegroundColor Green
} else {
    Write-Host "✗ API не запустился" -ForegroundColor Red
}

# Запуск Ingestor (если Redis работает)
if ($redisRunning) {
    Write-Host "`n[4/4] Запуск Bybit Ingestor..." -ForegroundColor Yellow
    $ingestorCmd = "cd '$scriptPath'; `$env:PYTHONPATH = '$scriptPath'; Write-Host 'Bybit Ingestor for BTCUSDT...' -ForegroundColor Green; python ingestors\bybit\main.py --redis $RedisUrl --symbol BTCUSDT"
    Start-Process powershell -ArgumentList "-NoExit", "-Command", $ingestorCmd
    Write-Host "✓ Ingestor запущен" -ForegroundColor Green
} else {
    Write-Host "`n[4/4] Ingestor не запущен (нужен Redis)" -ForegroundColor Yellow
}

# Запуск Frontend
Write-Host "`n[5/5] Проверка Frontend..." -ForegroundColor Yellow
$frontendRunning = Test-NetConnection -ComputerName localhost -Port 5173 -InformationLevel Quiet -WarningAction SilentlyContinue
if ($frontendRunning) {
    Write-Host "✓ Frontend уже запущен: http://localhost:5173" -ForegroundColor Green
} else {
    Write-Host "Запуск Frontend..." -ForegroundColor Yellow
    $frontendCmd = "cd '$scriptPath\frontend'; Write-Host 'Frontend on http://localhost:5173' -ForegroundColor Green; npm run dev"
    Start-Process powershell -ArgumentList "-NoExit", "-Command", $frontendCmd
    Start-Sleep -Seconds 3
    Write-Host "✓ Frontend запускается: http://localhost:5173" -ForegroundColor Green
}

Write-Host "`n=== Готово! ===" -ForegroundColor Green
Write-Host "Frontend: http://localhost:5173" -ForegroundColor Cyan
Write-Host "API: http://localhost:8000" -ForegroundColor Cyan
Write-Host "API Docs: http://localhost:8000/docs" -ForegroundColor Cyan

if (-not $redisRunning) {
    Write-Host "`n⚠ ВНИМАНИЕ: Redis не запущен - данных не будет!" -ForegroundColor Red
    Write-Host "Запустите Redis и перезапустите скрипт для получения данных." -ForegroundColor Yellow
}
