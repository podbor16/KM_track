import json
import sys
import os
# Добавляем путь к директории analytics в sys.path
sys.path.append(os.path.join(os.path.dirname(__file__), '..', '..'))

from analytics.personal.allusers import analyze_race_data, format_time
from config import RACE_DATA_FILE

def get_formatted_analytics():
    """Получить аналитику в формате, подходящем для веб-интерфейса"""
    
    # Загружаем данные из race_data.json
    with open(RACE_DATA_FILE, 'r', encoding='utf-8') as file:
        data = json.load(file)
    
    runners = data['data']
    
    # Счетчики статусов
    not_started = 0
    running = 0
    finished = 0
    
    # Счетчики полов
    male_count = 0
    female_count = 0
    
    # Анализируем данные
    for runner in runners:
        status = runner.get('status', '')
        gender = runner.get('gender', '')
        
        # Считаем статусы
        if status == 'notstarted':
            not_started += 1
        elif status == 'running':
            running += 1
        elif status == 'finished':
            finished += 1
        
        # Считаем пол
        if gender == 'male':
            male_count += 1
        elif gender == 'female':
            female_count += 1
    
    # Получаем финишировавших участников с временем
    finished_runners = []
    finished_male_runners = []
    finished_female_runners = []
    
    for runner in runners:
        if runner.get('status') == 'finished':
            finish_time = runner.get('times.official_:::finish:::')
            start_time = runner.get('times.real_:::start:::')
            
            if finish_time is not None and start_time is not None:
                net_time = finish_time - start_time
                
                finished_runner = {
                    'name': runner.get('name', ''),
                    'surname': runner.get('surname', ''),
                    'gender': runner.get('gender', ''),
                    'net_time': net_time,
                    'time_str': format_time(net_time)
                }
                
                finished_runners.append(finished_runner)
                
                if runner.get('gender') == 'male':
                    finished_male_runners.append(finished_runner)
                elif runner.get('gender') == 'female':
                    finished_female_runners.append(finished_runner)
    
    # Сортируем по времени (по возрастанию)
    finished_runners.sort(key=lambda x: x['net_time'])
    finished_male_runners.sort(key=lambda x: x['net_time'])
    finished_female_runners.sort(key=lambda x: x['net_time'])
    
    # Подготовка результата
    result = {
        'general_stats': {
            'total_runners': len(runners),
            'not_started': not_started,
            'on_track': running,
            'finished': finished
        },
        'gender_stats': {
            'male_count': male_count,
            'female_count': female_count
        },
        'top_finishers': {
            'overall': finished_runners[:3],
            'male': finished_male_runners[:3],
            'female': finished_female_runners[:3]
        }
    }
    
    # Вычисляем среднее чистое время для мужчин и женщин
    if finished_male_runners:
        male_total_time = sum(runner['net_time'] for runner in finished_male_runners)
        male_avg_time = male_total_time / len(finished_male_runners)
        result['gender_stats']['male_avg_time'] = format_time(male_avg_time)
    else:
        result['gender_stats']['male_avg_time'] = 'Н/Д'
    
    if finished_female_runners:
        female_total_time = sum(runner['net_time'] for runner in finished_female_runners)
        female_avg_time = female_total_time / len(finished_female_runners)
        result['gender_stats']['female_avg_time'] = format_time(female_avg_time)
    else:
        result['gender_stats']['female_avg_time'] = 'Н/Д'
    
    return result