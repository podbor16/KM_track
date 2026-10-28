#!/bin/bash
# Wrapper для load_duathlon_results.py — используется systemd-шаблоном km_duathlon_loader@.service.
set -a
source /opt/km_track/config/loader/"$1".env
set +a
exec /opt/km_track/venv/bin/python load_duathlon_results.py \
    --config "$LOADER_CONFIG" \
    --interval "${LOADER_INTERVAL:-30}"
