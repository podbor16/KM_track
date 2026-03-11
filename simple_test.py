#!/usr/bin/env python
# -*- coding: utf-8 -*-
import io
import sys
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

from src.analytics.db_connection_optimized import get_race_stats_from_db
import json

print('Testing get_race_stats_from_db function...')

results = get_race_stats_from_db('Ночной забег')

if results and results.get('years_data'):
    print('\nRESULT:')
    print(json.dumps(results, indent=2, ensure_ascii=False))
else:
    print('No data')
