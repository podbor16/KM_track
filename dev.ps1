# Local dev stack: Redis (WSL2) + local DB (isolated from prod, see
# .env.local) + uvicorn. One command: .\dev.ps1

# --- .env.local -> environment variables of this process ---
# Process env vars take priority over .env (load_dotenv won't override
# already-set vars), so DB_* from .env.local override the prod values from
# .env only for the uvicorn started here.
$envLocal = Join-Path $PSScriptRoot ".env.local"
if (Test-Path $envLocal) {
    Get-Content $envLocal | ForEach-Object {
        if ($_ -match '^\s*([A-Za-z_][A-Za-z0-9_]*)\s*=\s*(.*)\s*$') {
            [System.Environment]::SetEnvironmentVariable($matches[1], $matches[2], "Process")
        }
    }
    Write-Host "Loaded .env.local (DB_HOST=$env:DB_HOST DB_PORT=$env:DB_PORT DB_NAME=$env:DB_NAME)"
} else {
    Write-Host "No .env.local found - uvicorn will use the prod DB from .env (see README)"
}

# --- Redis ---
$redisUp = (Test-NetConnection -ComputerName 127.0.0.1 -Port 6379 -WarningAction SilentlyContinue).TcpTestSucceeded
if (-not $redisUp) {
    Write-Host "Starting Redis in WSL..."
    wsl -d Ubuntu -u root -- redis-server --daemonize yes --bind 127.0.0.1 --port 6379
    # On a cold WSL2 VM boot, the Linux process comes up fast but Windows'
    # localhost-forwarding proxy can lag a few seconds behind - poll instead
    # of a fixed 1s sleep (was causing a startup race: uvicorn saw Redis as
    # down and disabled SSE for the whole run even though Redis was fine
    # a couple seconds later).
    for ($i = 0; $i -lt 20; $i++) {
        Start-Sleep -Seconds 1
        if ((Test-NetConnection -ComputerName 127.0.0.1 -Port 6379 -WarningAction SilentlyContinue).TcpTestSucceeded) { break }
    }
} else {
    Write-Host "Redis already running"
}

# --- Local DB (MySQL80, port comes from .env.local) ---
$dbPort = if ($env:DB_PORT) { $env:DB_PORT } else { 3308 }
$dbUp = (Test-NetConnection -ComputerName 127.0.0.1 -Port $dbPort -WarningAction SilentlyContinue).TcpTestSucceeded
if ($dbUp) {
    Write-Host "Local DB reachable on port $dbPort"
} else {
    Write-Host "Local DB (port $dbPort) not reachable - check the MySQL80 service (Get-Service MySQL80)"
}

# --- Uvicorn ---
Write-Host "Starting uvicorn..."
uvicorn app:app --reload --port 8000
