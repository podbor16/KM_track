#!/usr/bin/env python3
import os

print('📊 Статистика проекта:')
print()
print('Backend модули:')

server_files = ['server/config.py', 'server/models.py', 'server/routes_service.py', 
                'server/runners_service.py', 'server/api.py', 'server/flask_server.py']

for fname in server_files:
    if os.path.exists(fname):
        with open(fname, 'r', encoding='utf-8') as f:
            lines = len(f.readlines())
        print(f'  {os.path.basename(fname)}: {lines} строк')

print()
print('Frontend:')
for fname in ['maps/rosneft.html', 'maps/snow7.html']:
    if os.path.exists(fname):
        with open(fname, 'r', encoding='utf-8') as f:
            lines = len(f.readlines())
        print(f'  {os.path.basename(fname)}: {lines} строк')

print()
print('Static:')
js_file = 'server/static/tracker.js'
if os.path.exists(js_file):
    with open(js_file, 'r', encoding='utf-8') as f:
        print(f'  tracker.js: {len(f.readlines())} строк')

print()
print('✅ Рефакторинг завершен!')
