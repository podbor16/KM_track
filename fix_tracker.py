import re

# Путь к файлу
file_path = r"x:\Мой гараж\Учеба\0. ДИПЛОМ\KM_track\static\js\tracker.js"

# Читаем файл
with open(file_path, 'r', encoding='utf-8') as f:
    content = f.read()

# Исправление 1: LoadAllRunners() - правильный парсинг API
old1 = """async function loadAllRunners() {
    try {
        const timestamp = new Date().getTime(); // Cache-busting
        const response = await fetch(`${CONFIG.API_BASE}/runners?event=${CONFIG.EVENT_NAME}&v=${timestamp}`);
        allRunners = await response.json();
        console.log(`Загружено участников: ${allRunners.length}`);
        updateSelectedRunnersMarkers();
    } catch (error) {
        console.error('Ошибка загрузки участников:', error);
        updateStatus('Ошибка загрузки данных');
    }
}"""

new1 = """async function loadAllRunners() {
    try {
        const timestamp = new Date().getTime(); // Cache-busting
        const response = await fetch(`${CONFIG.API_BASE}/runners?event=${CONFIG.EVENT_NAME}&v=${timestamp}`);
        const data = await response.json();
        // API возвращает RunnersListResponse со структурой { runners, total, ... }
        allRunners = Array.isArray(data) ? data : (data.runners || []);
        console.log(`✅ Загружено участников: ${allRunners.length}`);
        updateSelectedRunnersMarkers();
    } catch (error) {
        console.error('❌ Ошибка загрузки участников:', error);
        updateStatus('Ошибка загрузки данных');
    }
}"""

content = content.replace(old1, new1)
print("✅ Исправлено loadAllRunners()")

# Исправление 2: LoadStats() 
old2 = """        const runners = await response.json();
        
        const stats = {
            total: runners.length,
            on_track: runners.filter(r => ['started', 'running'].includes(r.status)).length,
            finished: runners.filter(r => r.status === 'finished').length,
            not_started: runners.filter(r => r.status === 'notstarted').length
        };"""

new2 = """        const data = await response.json();
        const runners = Array.isArray(data) ? data : (data.runners || []);
        
        const stats = {
            total: runners.length,
            on_track: runners.filter(r => ['started', 'running'].includes(r.status)).length,
            finished: runners.filter(r => r.status === 'finished').length,
            not_started: runners.filter(r => r.status === 'notstarted').length
        };"""

# Находим в loadStats()
if 'async function loadStats()' in content:
    content = content.replace(old2, new2)
    print("✅ Исправлено loadStats()")

# Исправление 3: Regex в parse_pace_to_kmh_helper()
old3 = "    const match = paceStr.match(/(\\\\d+)[::\\'](\\\\d+)/);"
new3 = "    const match = paceStr.match(/(\\d+)[:']([\\d]+)/);"

content = content.replace(old3, new3)
print("✅ Исправлен regex в parse_pace_to_kmh_helper()")

# Исправление 4: updateSelectedRunnersMarkers()
old4 = """function updateSelectedRunnersMarkers() {
    const selectedRunners = allRunners.filter(runner =>
        selectedRunnerIds.has(String(runner.id))
    );
    updateRunnerMarkers(selectedRunners);
}"""

new4 = """function updateSelectedRunnersMarkers() {
    const selectedRunners = allRunners.filter(runner => {
        const runnerId = String(runner.id || runner.bib || runner.dorsal);
        return selectedRunnerIds.has(runnerId);
    });
    updateRunnerMarkers(selectedRunners);
}"""

content = content.replace(old4, new4)
print("✅ Исправлено updateSelectedRunnersMarkers()")

# Исправление 5: loadAndDisplaySegmentInfo() - добавляем более надежную версию
old5 = """/**
 * Загрузить информацию о последнем сегменте спортсмена и отобразить в popup
 */
async function loadAndDisplaySegmentInfo(runnerId) {
    try {
        const response = await fetch(
            `${CONFIG.API_BASE}/runner/${runnerId}/latest-segment?event=${CONFIG.EVENT_NAME}`
        );
        
        if (!response.ok) throw new Error('Failed to fetch segment');
        
        const data = await response.json();
        if (!data.success || data.segments.length === 0) {
            updateSegmentDisplay(runnerId, null);
            return;
        }
        
        const segment = data.segments[0];
        updateSegmentDisplay(runnerId, segment);
    } catch (error) {
        console.warn(`Не удалось загрузить сегмент для спортсмена ${runnerId}:`, error);
        updateSegmentDisplay(runnerId, null);
    }
}"""

new5 = """/**
 * Загрузить информацию о последнем сегменте спортсмена и отобразить в popup
 */
async function loadAndDisplaySegmentInfo(runnerId) {
    try {
        // Даём время на рендеринг popup в DOM
        await new Promise(resolve => setTimeout(resolve, 150));
        
        let segmentDiv = document.getElementById(`segment-info-${runnerId}`);
        
        if (!segmentDiv) {
            console.warn(`⚠️ div segment-info-${runnerId} не найден в DOM`);
            return;
        }
        
        const response = await fetch(
            `${CONFIG.API_BASE}/runner/${runnerId}/latest-segment?event=${CONFIG.EVENT_NAME}`
        );
        
        if (!response.ok) throw new Error(`API Error: ${response.status}`);
        
        const data = await response.json();
        console.log(`📍 Сегмент для ${runnerId}:`, data);
        
        if (!data.success || !data.segments || data.segments.length === 0) {
            updateSegmentDisplay(runnerId, null);
            return;
        }
        
        const segment = data.segments[0];
        console.log(`✅ Загружен сегмент для ${runnerId}:`, segment);
        updateSegmentDisplay(runnerId, segment);
    } catch (error) {
        console.warn(`❌ Не удалось загрузить сегмент для спортсмена ${runnerId}:`, error);
        updateSegmentDisplay(runnerId, null);
    }
}"""

content = content.replace(old5, new5)
print("✅ Исправлено loadAndDisplaySegmentInfo()")

# Исправление 6: Добавляем функцию startContinuousTracking перед onSegmentPassed
insertion_point = "function onSegmentPassed(runnerId, segment) {"
continuous_tracking = """/**
 * Непрерывное обновление позиций маркеров на маршруте
 * Вызывается один раз при инициализации для периодического отслеживания спортсменов
 */
function startContinuousTracking() {
    console.log('🚀 Запущено непрерывное отслеживание позиций маркеров...');
    
    setInterval(async () => {
        try {
            const timestamp = new Date().getTime();
            const response = await fetch(`${CONFIG.API_BASE}/runners?event=${CONFIG.EVENT_NAME}&v=${timestamp}`);
            const data = await response.json();
            
            // Парсим ответ правильно
            const updatedRunners = Array.isArray(data) ? data : (data.runners || []);
            
            // Обновляем только выбранных спортсменов
            const selectedRunners = updatedRunners.filter(runner => {
                const runnerId = String(runner.id || runner.bib || runner.dorsal);
                return selectedRunnerIds.has(runnerId);
            });
            
            if (selectedRunners.length > 0) {
                updateRunnerMarkers(selectedRunners);
            }
        } catch (error) {
            console.warn('⚠️ Ошибка обновления позиций:', error);
        }
    }, CONFIG.UPDATE_INTERVAL);
}

"""

if insertion_point in content:
    content = content.replace(insertion_point, continuous_tracking + insertion_point)
    print("✅ Добавлена функция startContinuousTracking()")

# Пишем файл обратно
with open(file_path, 'w', encoding='utf-8') as f:
    f.write(content)

print("\n✅ Все исправления применены к tracker.js!")
print("📌 Важно: после загрузки страницы трекера вызовите startContinuousTracking() в консоли")
