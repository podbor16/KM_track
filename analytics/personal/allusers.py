import json
import os

def format_time(milliseconds):
    """Форматирует время в миллисекундах в формат MM:SS.mmm"""
    seconds_total = milliseconds / 1000
    minutes = int(seconds_total // 60)
    seconds = int(seconds_total % 60)
    millisecs = int((seconds_total - int(seconds_total)) * 1000)
    return f"{minutes:02d}:{seconds:02d}.{millisecs:03d}"

def analyze_race_data():
    # Загружаем данные из race_data.json
    race_data_path = os.path.join(os.path.dirname(__file__), '..', '..', 'tracker', 'race_data.json')
    with open(race_data_path, 'r', encoding='utf-8') as file:
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
    
    print ("Аналитика по всем участникам забега:\n")
    # Выводим топ-3 по времени финиша
    print("Топ-3 участников по времени финиша:")
    for i, runner in enumerate(finished_runners[:3], 1):
        print(f"{i} - {runner['name']} {runner['surname']} - {runner['time_str']}")
    print()
    
    # Выводим топ-3 мужчин
    print("Топ-3 мужчин по времени финиша:")
    for i, runner in enumerate(finished_male_runners[:3], 1):
        print(f"{i} - {runner['name']} {runner['surname']} - {runner['time_str']}")
    print()
    
    # Выводим топ-3 женщин
    print("Топ-3 женщин по времени финиша:")
    for i, runner in enumerate(finished_female_runners[:3], 1):
        print(f"{i} - {runner['name']} {runner['surname']} - {runner['time_str']}")
    print()
    
    # Выводим общую статистику
    total_runners = len(runners)
    print(f"Общее количество участников: {total_runners}")
    print(f"1. Не стартовало: {not_started}")
    print(f"2. На трассе: {running}")
    print(f"3. Финишировало: {finished}\n")

    print("Статистика по полу:")
    print(f"Мужчин: {male_count}")
    # Вычисляем и выводим среднее чистое время для мужчин и женщин
    if finished_male_runners:
        male_total_time = sum(runner['net_time'] for runner in finished_male_runners)
        male_avg_time = male_total_time / len(finished_male_runners)
        print(f"Среднее чистое время мужчин: {format_time(male_avg_time)}\n")
    else:
        print("Среднее чистое время мужчин: Н/Д\n")

    print(f"Женщин: {female_count}")
    
    if finished_female_runners:
        female_total_time = sum(runner['net_time'] for runner in finished_female_runners)
        female_avg_time = female_total_time / len(finished_female_runners)
        print(f"Среднее чистое время женщин: {format_time(female_avg_time)}\n")
    else:
        print("Среднее чистое время женщин: Н/Д\n")

if __name__ == "__main__":
    analyze_race_data()