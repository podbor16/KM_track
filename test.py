# test_osm_way.py
import requests


def test_osm_way(way_id):
    """Проверяем существование way в OSM"""

    # Правильный Overpass API запрос
    query = f"""
    [out:json];
    way({way_id});
    out body;
    >;
    out skel qt;
    """

    url = f"https://overpass-api.de/api/interpreter?data={requests.utils.quote(query)}"

    print(f"🌐 Запрос: {url[:100]}...")

    try:
        response = requests.get(url, timeout=10)
        response.raise_for_status()

        data = response.json()

        print(f"✅ Ответ получен")
        print(f"📊 Элементов в ответе: {len(data.get('elements', []))}")

        # Ищем way
        ways = [e for e in data.get('elements', []) if e.get('type') == 'way']
        nodes = [e for e in data.get('elements', []) if e.get('type') == 'node']

        print(f"🔍 Найдено ways: {len(ways)}")
        print(f"🔍 Найдено nodes: {len(nodes)}")

        if ways:
            way = ways[0]
            print(f"\n📋 Информация о маршруте:")
            print(f"   ID: {way.get('id')}")
            print(f"   Узлов: {len(way.get('nodes', []))}")
            print(f"   Теги: {way.get('tags', {})}")

            if way.get('tags'):
                print(f"   Название: {way.get('tags', {}).get('name', 'нет')}")
                print(f"   Спорт: {way.get('tags', {}).get('sport', 'нет')}")

            # Выводим первые 5 координат
            if nodes:
                print(f"\n📍 Пример координат (первые 5):")
                for i, node_id in enumerate(way.get('nodes', [])[:5]):
                    node = next((n for n in nodes if n['id'] == node_id), None)
                    if node:
                        print(f"   {i + 1}. [{node['lat']}, {node['lon']}]")

        return data

    except Exception as e:
        print(f"❌ Ошибка: {e}")
        return None


if __name__ == "__main__":
    print("🧪 Тестируем OSM way ID: 181589417")
    print("=" * 50)

    result = test_osm_way(181589417)

    if not result or len(result.get('elements', [])) == 0:
        print("\n⚠️  Way не найден. Возможные причины:")
        print("   1. Неправильный ID")
        print("   2. Way был удален из OSM")
        print("   3. Нужно использовать другой Overpass API запрос")

        print("\n🔄 Пробуем альтернативный запрос...")

        # Пробуем другой формат запроса
        alt_query = """
        [out:json];
        (
          way(181589417);
          node(w);
        );
        out body;
        """

        alt_url = f"https://overpass-api.de/api/interpreter?data={requests.utils.quote(alt_query)}"

        try:
            alt_response = requests.get(alt_url, timeout=10)
            alt_data = alt_response.json()

            print(f"📊 Результат альтернативного запроса:")
            print(f"   Элементов: {len(alt_data.get('elements', []))}")

            # Проверяем элементы
            for element in alt_data.get('elements', []):
                if element.get('type') == 'way':
                    print(f"✅ Найден way: {element.get('id')}")
                    print(f"   Узлов: {len(element.get('nodes', []))}")
                    if element.get('tags'):
                        print(f"   Теги: {element.get('tags')}")

        except Exception as alt_e:
            print(f"❌ Ошибка альтернативного запроса: {alt_e}")