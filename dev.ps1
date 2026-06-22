$VPS = "root@89.108.88.104"

# --- Redis ---
$redisUp = (Test-NetConnection -ComputerName 127.0.0.1 -Port 6379 -WarningAction SilentlyContinue).TcpTestSucceeded
if (-not $redisUp) {
    Write-Host "Starting Redis in WSL..."
    wsl -d Ubuntu -u root -- redis-server --daemonize yes --bind 127.0.0.1 --port 6379
    Start-Sleep -Seconds 1
} else {
    Write-Host "Redis already running"
}

# --- SSH tunnel (MySQL 3306) ---
$dbUp = (Test-NetConnection -ComputerName 127.0.0.1 -Port 3306 -WarningAction SilentlyContinue).TcpTestSucceeded
if (-not $dbUp) {
    Write-Host "Starting SSH tunnel to DB..."
    Start-Process -NoNewWindow -FilePath "ssh" -ArgumentList "-N -L 3306:127.0.0.1:3306 $VPS"
    Start-Sleep -Seconds 2
} else {
    Write-Host "DB tunnel already running"
}

# --- Uvicorn ---
Write-Host "Starting uvicorn..."
uvicorn app:app --reload --port 8000
