#!/bin/bash
# Первоначальная настройка VPS для KM Track
# Запускать от root на свежем Ubuntu 24.04
# Использование: bash setup.sh <git_repo_url>
#
# Пример: bash setup.sh https://github.com/podbor16/KM_track.git

set -euo pipefail

REPO_URL="${1:-}"
APP_DIR="/opt/km_track"
APP_USER="km"
DOMAIN="analytics.krasmarafon.ru"

if [ -z "$REPO_URL" ]; then
    echo "Использование: bash setup.sh <git_repo_url>"
    exit 1
fi

echo "=== Установка зависимостей ==="
apt update && apt install -y \
    python3.12 python3.12-venv python3-pip \
    nginx certbot python3-certbot-nginx \
    git curl htop

echo "=== Создание пользователя $APP_USER ==="
if ! id "$APP_USER" &>/dev/null; then
    useradd -m -s /bin/bash "$APP_USER"
fi

echo "=== Клонирование репозитория ==="
if [ -d "$APP_DIR/.git" ]; then
    echo "Репозиторий уже склонирован, обновляю..."
    git -C "$APP_DIR" pull
else
    git clone "$REPO_URL" "$APP_DIR"
fi
chown -R "$APP_USER:$APP_USER" "$APP_DIR"

echo "=== Virtualenv и зависимости ==="
cd "$APP_DIR"
python3.12 -m venv venv
venv/bin/pip install --upgrade pip
venv/bin/pip install -r requirements.txt

echo "=== Swap 1 GB ==="
if [ ! -f /swapfile ]; then
    fallocate -l 1G /swapfile
    chmod 600 /swapfile
    mkswap /swapfile
    swapon /swapfile
    echo '/swapfile none swap sw 0 0' >> /etc/fstab
    echo "Swap создан"
else
    echo "Swap уже существует"
fi

echo "=== Nginx ==="
cp "$APP_DIR/deploy/nginx.conf" /etc/nginx/sites-available/km_track
ln -sf /etc/nginx/sites-available/km_track /etc/nginx/sites-enabled/km_track
rm -f /etc/nginx/sites-enabled/default
nginx -t && systemctl reload nginx

echo "=== SSL (Let's Encrypt) ==="
echo "Убедись что DNS-запись analytics.krasmarafon.ru → $(curl -s ifconfig.me) уже создана!"
read -p "DNS настроен? (y/n): " dns_ok
if [ "$dns_ok" = "y" ]; then
    certbot --nginx -d "$DOMAIN" --non-interactive --agree-tos -m admin@krasmarafon.ru
    systemctl reload nginx
else
    echo "Настрой DNS и запусти: certbot --nginx -d $DOMAIN"
fi

echo "=== Systemd unit ==="
cp "$APP_DIR/deploy/km_track.service" /etc/systemd/system/
systemctl daemon-reload
systemctl enable km_track

echo ""
echo "=== ГОТОВО! ==="
echo "Следующий шаг — скопировать .env файл:"
echo "  scp .env root@SERVER_IP:$APP_DIR/.env"
echo ""
echo "Затем запустить приложение:"
echo "  systemctl start km_track"
echo "  systemctl status km_track"
echo ""
echo "Проверить:"
echo "  curl http://127.0.0.1:8000/health"
echo "  curl https://$DOMAIN/health"
