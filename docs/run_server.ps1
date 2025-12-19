# Скрипт для быстрого запуска Flask сервера
# Использование: .\run_server.ps1

$projectPath = Split-Path -Parent $MyInvocation.MyCommand.Path
$venvPath = Join-Path $projectPath ".venv"

# Проверяем, существует ли виртуальное окружение
if (-not (Test-Path $venvPath)) {
    Write-Host "❌ Виртуальное окружение не найдено!" -ForegroundColor Red
    Write-Host "Создайте его командой: python -m venv .venv" -ForegroundColor Yellow
    exit 1
}

# Активируем виртуальное окружение
Write-Host "Активация виртуального окружения..." -ForegroundColor Cyan
& "$venvPath\Scripts\Activate.ps1"

# Проверяем наличие необходимых файлов
if (-not (Test-Path (Join-Path $projectPath "race_data.json"))) {
    Write-Host "⚠️  Внимание: файл race_data.json не найден!" -ForegroundColor Yellow
    Write-Host "Запустите сначала парсер API или используйте тестовые данные" -ForegroundColor Yellow
}

if (-not (Test-Path (Join-Path $projectPath "server" "flask_server.py"))) {
    Write-Host "❌ Файл flask_server.py не найден!" -ForegroundColor Red
    exit 1
}

Write-Host "`n" -ForegroundColor Green
Write-Host "🚀 Запуск Flask сервера..." -ForegroundColor Green
Write-Host "🌐 Откройте браузер: http://localhost:5000" -ForegroundColor Green
Write-Host "⏹️  Для остановки нажмите Ctrl+C" -ForegroundColor Yellow
Write-Host "`n" -ForegroundColor Green

# Запускаем сервер
Set-Location $projectPath
python -m server.flask_server
