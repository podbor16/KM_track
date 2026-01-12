#!/usr/bin/env python3
import re

# Читаем rosneft.html
with open('rosneft.html', 'r', encoding='utf-8') as f:
    content = f.read()

# Заменяем весь внутренний скрипт (от первого <script> после leaflet.js до </body>)
leaflet_script_end = content.find('</script>', content.find('unpkg.com/leaflet'))

if leaflet_script_end > 0:
    body_end = content.find('</body>')
    
    before = content[:leaflet_script_end + len('</script>')]
    after = '\n    ' + content[body_end:]
    
    new_scripts = '''
        <script src="/static/tracker.js"></script>
        <script>
            // Переопределяем конфигурацию для Роснефть
            CONFIG.EVENT_NAME = 'rosneft';
            CONFIG.STORAGE_KEY = 'rosneft_selected_runners';
        </script>
    </body>
</html>'''
    
    new_content = before + new_scripts
    
    with open('rosneft.html', 'w', encoding='utf-8') as f:
        f.write(new_content)
    
    print('✅ rosneft.html успешно обновлен')
else:
    print('❌ Не найден конец скрипта leaflet')
