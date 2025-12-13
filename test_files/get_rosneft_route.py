# get_rosneft_route.py
"""
Скрипт для получения координат трассы Роснефть из OpenStreetMap
Way ID: 553966988 (МСК Радуга, Красноярск)
Дистанция: 5 км
"""
import requests
import json


def get_osm_route(way_id):
    """Получаем координаты маршрута из OSM через Overpass API"""

    # Упрощенный запрос
    query = f"""
    [out:json][timeout:60];
    (
      way({way_id});
      node(w);
    );
    out body;
    """

    # Пробуем разные серверы Overpass API
    servers = [
        "https://overpass.kumi.systems/api/interpreter",
        "https://overpass-api.de/api/interpreter",
        "https://overpass.openstreetmap.ru/api/interpreter"
    ]

    for server in servers:
        url = f"{server}?data={requests.utils.quote(query)}"
        print(f"🌐 Запрос к {server} для way {way_id}...")

        try:
            response = requests.get(url, timeout=60)
            response.raise_for_status()

            data = response.json()

            # Извлекаем way и nodes
            ways = [e for e in data.get('elements', []) if e.get('type') == 'way']
            nodes = [e for e in data.get('elements', []) if e.get('type') == 'node']

            if not ways:
                print(f"⚠️  Way {way_id} не найден на {server}, пробуем следующий...")
                continue

            way = ways[0]
            print(f"✅ Найден маршрут на {server}:")
            print(f"   ID: {way.get('id')}")
            print(f"   Узлов: {len(way.get('nodes', []))}")
            print(f"   Теги: {way.get('tags', {})}")

            # Собираем координаты в правильном порядке
            coordinates = []
            for node_id in way.get('nodes', []):
                node = next((n for n in nodes if n['id'] == node_id), None)
                if node:
                    coordinates.append([node['lat'], node['lon']])

            print(f"📍 Получено координат: {len(coordinates)}")

            # Вычисляем примерную длину маршрута
            total_distance = calculate_route_length(coordinates)
            print(f"📏 Примерная длина маршрута: {total_distance:.2f} км")

            return {
                'way_id': way_id,
                'coordinates': coordinates,
                'tags': way.get('tags', {}),
                'node_count': len(coordinates),
                'estimated_length_km': round(total_distance, 2)
            }

        except Exception as e:
            print(f"❌ Ошибка на {server}: {e}")
            continue

    print(f"❌ Не удалось получить данные ни с одного сервера")
    return None


def calculate_route_length(coordinates):
    """Вычисляем длину маршрута по координатам (формула гаверсинуса)"""
    import math

    def haversine(lat1, lon1, lat2, lon2):
        R = 6371  # Радиус Земли в км

        lat1_rad = math.radians(lat1)
        lat2_rad = math.radians(lat2)
        delta_lat = math.radians(lat2 - lat1)
        delta_lon = math.radians(lon2 - lon1)

        a = math.sin(delta_lat / 2) ** 2 + \
            math.cos(lat1_rad) * math.cos(lat2_rad) * \
            math.sin(delta_lon / 2) ** 2

        c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))

        return R * c

    total = 0
    for i in range(len(coordinates) - 1):
        lat1, lon1 = coordinates[i]
        lat2, lon2 = coordinates[i + 1]
        total += haversine(lat1, lon1, lat2, lon2)

    return total


def save_route_to_json(route_data, filename='rosneft_route.json'):
    """Сохраняем данные маршрута в JSON файл"""
    with open(filename, 'w', encoding='utf-8') as f:
        json.dump(route_data, f, ensure_ascii=False, indent=2)
    print(f"💾 Данные сохранены в {filename}")


if __name__ == "__main__":
    print("=" * 60)
    print("🏃 Получение трассы Роснефть из OpenStreetMap")
    print("=" * 60)

    WAY_ID = 553966988  # МСК Радуга, Красноярск

    route_data = get_osm_route(WAY_ID)

    if route_data:
        print("\n" + "=" * 60)
        print("📊 РЕЗУЛЬТАТ:")
        print("=" * 60)
        print(f"Way ID: {route_data['way_id']}")
        print(f"Точек на маршруте: {route_data['node_count']}")
        print(f"Длина маршрута: {route_data['estimated_length_km']} км")
        print(f"Теги: {route_data['tags']}")

        # Сохраняем в файл
        save_route_to_json(route_data, 'C:/Users/podbo/Работа/КРАСМАРАФОН/KM_track/rosneft_route.json')

        print("\n📍 Первые 5 координат:")
        for i, coord in enumerate(route_data['coordinates'][:5], 1):
            print(f"   {i}. [{coord[0]}, {coord[1]}]")

        print("\n✅ Готово! Данные можно использовать в flask_server.py")
    else:
        print("\n❌ Не удалось получить данные маршрута")
