#!/bin/bash
# Деплой новой версии KM Track
# Запускать от root на сервере: bash /opt/km_track/deploy/update.sh

set -euo pipefail

APP_DIR="/opt/km_track"

echo "=== Обновление кода ==="
cd "$APP_DIR"
git pull

echo "=== Загрузка статических библиотек ==="
venv/bin/python deploy/download_static_libs.py

echo "=== Обновление nginx ==="
cp deploy/nginx.conf /etc/nginx/sites-available/km_track
nginx -t && systemctl reload nginx

echo "=== Обновление зависимостей ==="
venv/bin/pip install -r requirements.txt --quiet

echo "=== Перезапуск сервиса ==="
systemctl restart km_track
sleep 2
systemctl status km_track --no-pager

echo "=== Проверка health ==="
sleep 1
curl -sf http://127.0.0.1:8000/health && echo " OK" || echo " FAILED"

echo "Deploy complete"
