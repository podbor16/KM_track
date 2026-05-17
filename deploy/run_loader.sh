#!/bin/bash
# Wrapper для load_race_results.py — используется systemd-шаблоном km_race_loader@.service.
# Аргумент $1: имя конфига (без .env), напр. vesna_5km
set -a
source /opt/km_track/config/loader/"$1".env
set +a
exec /opt/km_track/venv/bin/python load_race_results.py \
    --config "$LOADER_CONFIG" \
    --distance "$LOADER_DISTANCE" \
    --interval "${LOADER_INTERVAL:-5}" \
    --reset-cache "${LOADER_RESET_CACHE:-60}"
