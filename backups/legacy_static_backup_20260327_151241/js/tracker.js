// legacy/static/tracker.js
/**
 * Основная логика трекера забега Event 67 (Ночной забег)
 * Загружает участников из БД и отслеживает их позиции на карте
 */

// Конфигурация
const CONFIG = {
    API_BASE: '/api',
    UPDATE_INTERVAL: 2000,
    MAX_SELECTED: 5,
    EVENT_NAME: 'night_run',
    EVENT_ID: 67,
    STORAGE_KEY: 'night_run_selected_runners'
};

// Глобальные переменные
let map = null;
let routeLayer = null;
let routeCoordinates = [];
let runnerMarkers = {};
let selectedRunnerIds = new Set();
let allRunners = [];
let isUpdating = false;
let routeType = 'shuttle';
let runnerPositions = {};
let activePopups = new Map();

// Цвета для статусов
const STATUS_COLORS = {
    'notstarted': '#9E9E9E',
    'running':    '#EE2D62',
    'finished':   '#1a1a1a'
};


// ============================================
// ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ
// ============================================

function parseDuration(duration) {
    if (!duration) return null;

    // Уже в читаемом формате
    if (!String(duration).startsWith('PT')) return duration;

    // Парсим ISO 8601: PT1H26M0S или PT1560S
    const match = String(duration).match(/PT(?:(\d+)H)?(?:(\d+)M)?(?:(\d+)S)?/);
    if (!match) return duration;

    const totalSeconds =
        (parseInt(match[1] || 0) * 3600) +
        (parseInt(match[2] || 0) * 60) +
        parseInt(match[3] || 0);

    const h = Math.floor(totalSeconds / 3600);
    const m = Math.floor((totalSeconds % 3600) / 60);
    const s = totalSeconds % 60;

    if (h > 0) {
        return `${h}:${String(m).padStart(2, '0')}:${String(s).padStart(2, '0')}`;
    }
    return `${m}:${String(s).padStart(2, '0')}`;
}

function getStatusText(status) {
    if (!status) return 'Неизвестно';

    const statusMap = {
        'Not started':  'Не стартовал',
        'notstarted':   'Не стартовал',
        'Running':      'На трассе',
        'running':      'На трассе',
        'started':      'На трассе',
        'Finished':     'Финишировал',
        'finished':     'Финишировал',
        'Disqualified': 'Нарушение',
        'disqualified': 'Нарушение',
        'Disqualifed':  'Нарушение',
        'Withdrawn':    'Снялся',
        'withdrawn':    'Снялся'
    };

    return statusMap[status] || status;
}

function getStatusColor(status) {
    if (!status) return STATUS_COLORS.notstarted;
    const s = status.toLowerCase();
    if (s.includes('finish'))                            return STATUS_COLORS.finished;
    if (s.includes('running') || s.includes('started')) return STATUS_COLORS.running;
    return STATUS_COLORS.notstarted;
}

function updateStatus(message) {
    const statusPanel = document.getElementById('statusPanel');
    if (statusPanel) statusPanel.textContent = message;
}


// ============================================
// РАБОТА С ЛОКАЛЬНЫМ ХРАНИЛИЩЕМ
// ============================================

function saveSelectedToStorage() {
    try {
        localStorage.setItem(CONFIG.STORAGE_KEY, JSON.stringify(Array.from(selectedRunnerIds)));
    } catch (error) {
        console.error('Ошибка сохранения в localStorage:', error);
    }
}

function loadSelectedFromStorage() {
    try {
        const stored = localStorage.getItem(CONFIG.STORAGE_KEY);
        if (stored) {
            const arr = JSON.parse(stored);
            selectedRunnerIds = new Set(arr);
            console.log('📂 Загружено выбранных из localStorage:', arr);
            return arr;
        }
    } catch (error) {
        console.error('Ошибка загрузки из localStorage:', error);
    }
    return [];
}

function clearSelectedStorage() {
    try {
        localStorage.removeItem(CONFIG.STORAGE_KEY);
    } catch (error) {
        console.error('Ошибка очистки localStorage:', error);
    }
}


// ============================================
// ИНИЦИАЛИЗАЦИЯ ТРЕКЕРА
// ============================================

async function init() {
    console.log('🚀 Инициализация трекера Event 67 (Ночной забег)');

    loadSelectedFromStorage();
    await initMap();
    await loadAllRunners();

    if (selectedRunnerIds.size > 0) {
        console.log('📍 Восстановлено выбранных участников:', selectedRunnerIds.size);
        updateSelectedList();
        initializeSelectedRunnersMarkers();
    }

    setupSearch();
    await loadAnalytics();
    startAutoUpdate();

    updateStatus('✅ Трекер запущен (Event 67 - Ночной забег)');
}


// ============================================
// РАБОТА С КАРТОЙ
// ============================================

async function initMap() {
    console.log('🗺️ Инициализация карты...');

    map = L.map('map').setView([56.0075, 92.7246], 15);
    map.attributionControl.setPrefix('');

    L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', {
        attribution: '© OpenStreetMap contributors'
    }).addTo(map);

    await loadRouteFromAPI();

    console.log('✅ Карта инициализирована');
}

async function loadRouteFromAPI() {
    try {
        updateStatus('Загрузка GPX маршрута...');
        
        const gpxPath = getGPXPathForEvent(CONFIG.EVENT_NAME);
        console.log('📂 Загружаю GPX:', gpxPath);
        
        const gpxResponse = await fetch(gpxPath);
        
        if (!gpxResponse.ok) {
            throw new Error(`Ошибка загрузки GPX (статус ${gpxResponse.status})`);
        }
        
        const gpxContent = await gpxResponse.text();
        routeCoordinates = parseGPXToCoordinates(gpxContent);
        
        if (routeCoordinates.length === 0) {
            throw new Error('GPX файл не содержит координат');
        }
        
        routeType = 'gpx';
        console.log(`📍 Загружен GPX маршрут: ${routeCoordinates.length} точек`);
        
        if (routeLayer) map.removeLayer(routeLayer);

        if (routeCoordinates.length > 0) {
            routeLayer = L.polyline(routeCoordinates, {
                color: '#EE2D62',
                weight: 5,
                opacity: 0.7,
                smoothFactor: 1
            }).addTo(map);

            L.marker(routeCoordinates[0], {
                icon: L.divIcon({
                    className: 'start-marker',
                    html: '<div style="background: #EE2D62; color: white; padding: 8px 12px; border-radius: 5px; font-weight: bold; text-align: center;">🏁 СТАРТ</div>',
                    iconSize: [100, 35],
                    iconAnchor: [50, 35]
                })
            }).addTo(map);

            map.fitBounds(routeLayer.getBounds(), { padding: [50, 50] });
        }

        updateStatus('✅ Маршрут загружен');
        
    } catch (error) {
        console.error('❌ Ошибка загрузки GPX:', error);
        updateStatus('❌ Ошибка: не удалось загрузить GPX маршрут');
        alert(`Ошибка загрузки маршрута: ${error.message}`);
    }
}

/**
 * Определяет путь к GPX файлу на основе названия события
 */
function getGPXPathForEvent(eventName) {
    const paths = {
        'night_run': '/static/map/2026/night_run.gpx',
        'city_marathon': '/static/map/2026/city_marathon.gpx',
        'half_marathon': '/static/map/2026/half_marathon.gpx'
    };
    
    return paths[eventName] || '/static/map/2026/night_run.gpx';
}

/**
 * Парсит GPX файл и извлекает координаты трека
 */
function parseGPXToCoordinates(gpxContent) {
    try {
        const parser = new DOMParser();
        const xmlDoc = parser.parseFromString(gpxContent, 'text/xml');
        
        if (xmlDoc.getElementsByTagName('parsererror').length > 0) {
            throw new Error('Ошибка парсинга XML');
        }
        
        const coordinates = [];
        const trackPoints = xmlDoc.getElementsByTagName('trkpt');
        const routePoints = xmlDoc.getElementsByTagName('rtept');
        
        if (trackPoints.length > 0) {
            for (let i = 0; i < trackPoints.length; i++) {
                const lat = trackPoints[i].getAttribute('lat');
                const lon = trackPoints[i].getAttribute('lon');
                if (lat && lon) {
                    coordinates.push([parseFloat(lat), parseFloat(lon)]);
                }
            }
        }
        
        if (coordinates.length === 0 && routePoints.length > 0) {
            for (let i = 0; i < routePoints.length; i++) {
                const lat = routePoints[i].getAttribute('lat');
                const lon = routePoints[i].getAttribute('lon');
                if (lat && lon) {
                    coordinates.push([parseFloat(lat), parseFloat(lon)]);
                }
            }
        }
        
        console.log(`✅ GPX распарсен: ${coordinates.length} координат извлечено`);
        return coordinates;
        
    } catch (error) {
        console.error('❌ Ошибка при парсинге GPX:', error);
        return [];
    }
}

function createFallbackRoute() {
    const baseCoords = [56.0075, 92.7246];
    const latOffset = 0.01;
    const coordinates = [];

    for (let i = 0; i <= 10; i++) {
        coordinates.push([
            baseCoords[0] + (latOffset * i / 10),
            baseCoords[1] + (latOffset * 0.5 * i / 10)
        ]);
    }
    for (let i = 10; i >= 0; i--) {
        coordinates.push([
            baseCoords[0] + (latOffset * i / 10),
            baseCoords[1] + (latOffset * 0.5 * i / 10)
        ]);
    }

    return {
        event: 'night_run',
        event_name: 'Ночной забег (Набережная, Красноярск)',
        event_id: 67,
        distance: 5.0,
        route_type: 'shuttle',
        coordinates
    };
}


// ============================================
// ЗАГРУЗКА УЧАСТНИКОВ
// ============================================

async function loadAllRunners() {
    try {
        updateStatus('Загрузка участников...');

        const response = await fetch(
            `${CONFIG.API_BASE}/event-results?event_id=${CONFIG.EVENT_ID}&v=${Date.now()}`
        );

        if (!response.ok) throw new Error(`Ошибка загрузки: ${response.status}`);

        const data = await response.json();

        allRunners = (data.results || []).map(runner => ({
            id:                   runner.id || runner.start_number,
            start_number:         runner.start_number,
            surname:              runner.surname || '',
            name:                 runner.name || '',
            full_name:            `${runner.surname || ''} ${runner.name || ''}`.trim(),
            sex:                  runner.sex,
            category:             runner.category || '',
            status:               runner.race_status,
            time_gun_finish: parseDuration(runner.time_gun_finish),
            time_clear_finish:    parseDuration(runner.time_clear_finish),
            finish_pace_avg:      parseDuration(runner.finish_pace_avg),
            rank_absolute:        runner.rank_absolute,
            bib:                  runner.start_number,
            dorsal:               runner.start_number
        }));

        console.log(`✅ Загружено ${allRunners.length} участников`);
        updateStatus(`✅ Загружено участников: ${allRunners.length}`);

    } catch (error) {
        console.error('❌ Ошибка при загрузке участников:', error);
        allRunners = [];
        updateStatus('Ошибка загрузки участников');
    }
}


// ============================================
// МАРКЕРЫ НА КАРТЕ
// ============================================

function initializeSelectedRunnersMarkers() {
    Object.values(runnerMarkers).forEach(marker => {
        if (map.hasLayer(marker)) map.removeLayer(marker);
    });
    runnerMarkers = {};

    selectedRunnerIds.forEach(runnerId => {
        const runner = allRunners.find(r => String(r.id) === String(runnerId));
        if (runner) createRunnerMarker(runner);
    });
}

function buildMarkerIcon(runner) {
    const color = getStatusColor(runner.status);
    const runnerId = String(runner.id);
    // Уменьшаем шрифт для трёхзначных номеров, чтобы текст не выходил за круг
    const fontSize = String(runner.start_number).length >= 3 ? '11px' : '13px';

    return L.divIcon({
        className: `runner-marker runner-${runnerId}`,
        html: `<div style="
                    background: ${color};
                    color: white;
                    width: 52px;
                    height: 52px;
                    border-radius: 50%;
                    display: flex;
                    align-items: center;
                    justify-content: center;
                    font-weight: bold;
                    font-size: ${fontSize};
                    border: 2px solid white;
                    box-shadow: 0 2px 8px rgba(0,0,0,0.3);
                    box-sizing: border-box;
                    text-align: center;
                    line-height: 1;
                    overflow: hidden;
               ">№${runner.start_number}</div>`,
        iconSize: [52, 52],
        iconAnchor: [26, 26],
        popupAnchor: [0, -28]
    });
}

function buildPopupContent(runner) {
    // Показываем строки времён только если данные есть
    const officialTime = runner.time_gun_finish
        ? `<strong>Официальное время финиша:</strong> ${runner.time_gun_finish}<br>`
        : '';
    const pace = runner.finish_pace_avg
        ? `<strong>Темп:</strong> ${runner.finish_pace_avg}`
        : '';
    const clearTime = runner.time_clear_finish        
        ? `<strong>Чистое время финиша:</strong> ${runner.time_clear_finish}<br>` 
        : '';

    return `
        <div style="font-size: 12px; min-width: 190px; text-align: center;">
            <div><strong>№${runner.start_number}</strong></div>
            <div style="margin-top: 8px; padding-top: 8px; border-top: 1px solid #ddd;">
                <div><strong>${runner.full_name}</strong></div>
                ${runner.category ? `
                    <div style="margin-top: 6px; color: #666;">Категория:</div>
                    <div>${runner.category}</div>
                ` : ''}
            </div>
            <div style="margin-top: 8px; padding-top: 8px; border-top: 1px solid #ddd; text-align: left;">
                <strong>Статус:</strong> ${getStatusText(runner.status)}<br>
                <strong>Место в абсолюте:</strong> ${runner.rank_absolute || '-'}<br>
                ${officialTime}
                ${clearTime}
                ${pace}
            </div>
        </div>
    `;
}

function createRunnerMarker(runner) {
    const runnerId = String(runner.id);

    if (runnerMarkers[runnerId]) {
        updateRunnerMarkerPosition(runner);
        return;
    }

    const initialPosition = routeCoordinates[0] || [56.0075, 92.7246];
    const marker = L.marker(initialPosition, { icon: buildMarkerIcon(runner) }).addTo(map);

    marker.bindPopup(buildPopupContent(runner), { minWidth: 200 });
    marker.on('click', e => e.target.openPopup());
    marker.on('popupopen',  () => activePopups.set(runnerId, true));
    marker.on('popupclose', () => activePopups.delete(runnerId));

    runnerMarkers[runnerId] = marker;
    console.log(`✅ Создан маркер: ${runner.full_name}`);
}

function updateRunnerMarkerPosition(runner) {
    const runnerId = String(runner.id);
    const marker = runnerMarkers[runnerId];

    if (!marker || !routeCoordinates.length) return;

    const s = (runner.status || '').toLowerCase();
    
    // Определяем статус для логики позиции
    const isNotStarted = s.includes('not') || s === 'notstarted';
    const isRunning = s.includes('running') || s.includes('started');
    const isFinished = s.includes('finish');
    
    let progressPercent = runnerPositions[runnerId] || 0;

    if (isNotStarted) {
        // "Не стартовал" - стоит на старте
        progressPercent = 0;
    } else if (isFinished) {
        // "Финиш" - на финише
        progressPercent = 100;
    } else if (isRunning) {
        // "На трассе" - плавно движется (увеличиваем очень медленно для плавности)
        progressPercent = Math.min(100, progressPercent + 0.02);
    }

    runnerPositions[runnerId] = progressPercent;

    const maxIndex = Math.max(0, routeCoordinates.length - 1);
    const positionIndex = Math.min(maxIndex, Math.round(maxIndex * progressPercent / 100));
    marker.setLatLng(routeCoordinates[positionIndex] || routeCoordinates[0]);

    marker.setIcon(buildMarkerIcon(runner));

    if (marker.getPopup()) {
        marker.getPopup().setContent(buildPopupContent(runner));
    }
}


// ============================================
// ВЫБОР И ОТСЛЕЖИВАНИЕ УЧАСТНИКОВ
// ============================================

async function selectRunner(runnerId) {
    const runnerId_str = String(runnerId);

    if (selectedRunnerIds.size >= CONFIG.MAX_SELECTED) {
        alert(`❌ Максимум можно выбрать ${CONFIG.MAX_SELECTED} участников`);
        return;
    }
    if (selectedRunnerIds.has(runnerId_str)) {
        alert('✅ Этот участник уже отслеживается');
        return;
    }

    const runner = allRunners.find(r => String(r.id) === runnerId_str);
    if (!runner) {
        alert('❌ Участник не найден в базе');
        return;
    }

    selectedRunnerIds.add(runnerId_str);
    saveSelectedToStorage();
    createRunnerMarker(runner);
    updateSelectedList();
    updateStatus(`✅ Отслеживание: ${runner.full_name} (${selectedRunnerIds.size}/${CONFIG.MAX_SELECTED})`);

    const resultsDiv = document.getElementById('searchResults');
    if (resultsDiv && resultsDiv.style.display !== 'none') {
        searchRunners();
    }
}

async function deselectRunner(runnerId) {
    const runnerId_str = String(runnerId);
    selectedRunnerIds.delete(runnerId_str);
    saveSelectedToStorage();

    if (runnerMarkers[runnerId_str]) {
        if (map.hasLayer(runnerMarkers[runnerId_str])) {
            map.removeLayer(runnerMarkers[runnerId_str]);
        }
        delete runnerMarkers[runnerId_str];
        delete runnerPositions[runnerId_str];
        activePopups.delete(runnerId_str);
    }

    updateSelectedList();
    updateStatus(`Отслеживание остановлено (${selectedRunnerIds.size}/${CONFIG.MAX_SELECTED})`);
}

async function clearSelection() {
    if (!confirm('Удалить всех отслеживаемых участников?')) return;

    for (const runnerId of Array.from(selectedRunnerIds)) {
        await deselectRunner(runnerId);
    }
    clearSelectedStorage();
}

function updateSelectedList() {
    const selectedListDiv = document.getElementById('selectedList');
    if (!selectedListDiv) return;

    if (selectedRunnerIds.size === 0) {
        selectedListDiv.innerHTML = '<div style="color: #999; text-align: center; padding: 15px; font-size: 13px;">Нет отслеживаемых участников</div>';
        return;
    }

    let html = '<div style="padding: 8px; border: 1px solid #ddd; border-radius: 5px; max-height: 320px; overflow-y: auto; background: #f9f9f9;">';

    selectedRunnerIds.forEach(runnerId => {
        const runner = allRunners.find(r => String(r.id) === String(runnerId));
        if (!runner) return;
        html += `
            <div style="padding: 8px; border-bottom: 1px solid #eee; display: flex; justify-content: space-between; align-items: center; gap: 8px;">
                <div style="flex: 1; min-width: 0;">
                    <strong style="display: block; font-size: 13px;">№${runner.start_number}</strong>
                    <div style="font-size: 12px; font-weight: 500; color: #333; white-space: nowrap; overflow: hidden; text-overflow: ellipsis;">${runner.full_name}</div>
                    <div style="font-size: 11px; color: #666;">${runner.category || ''}</div>
                </div>
                <button onclick="deselectRunner('${runnerId}')" style="padding: 3px 6px; background: #f0f0f0; border: 1px solid #ccc; border-radius: 3px; cursor: pointer; font-size: 12px; white-space: nowrap;">✕</button>
            </div>
        `;
    });

    html += '</div>';
    html += `<button onclick="clearSelection()" style="margin-top: 8px; padding: 6px 10px; background: #fff3cd; border: 1px solid #ffc107; border-radius: 3px; cursor: pointer; width: 100%; font-size: 12px;">🗑️ Очистить (${selectedRunnerIds.size}/${CONFIG.MAX_SELECTED})</button>`;

    selectedListDiv.innerHTML = html;
}


// ============================================
// ПОИСК УЧАСТНИКОВ
// ============================================

function searchRunners() {
    const query = document.getElementById('searchInput');
    if (!query) return;

    const searchText = query.value.trim().toLowerCase();
    const resultsDiv = document.getElementById('searchResults');

    if (!searchText) {
        resultsDiv.innerHTML = '';
        resultsDiv.style.display = 'none';
        return;
    }

    const results = allRunners.filter(runner =>
        runner.full_name.toLowerCase().includes(searchText) ||
        String(runner.start_number).includes(searchText)
    ).slice(0, 15);

    if (results.length === 0) {
        resultsDiv.innerHTML = '<div style="padding: 10px; color: #999;">❌ Участники не найдены</div>';
        resultsDiv.style.display = 'block';
        return;
    }

    let html = '<div style="max-height: 400px; overflow-y: auto;">';

    results.forEach(runner => {
        const isSelected  = selectedRunnerIds.has(String(runner.id));
        const canSelect   = !isSelected && selectedRunnerIds.size < CONFIG.MAX_SELECTED;
        const statusColor = getStatusColor(runner.status);

        html += `
            <div style="padding: 10px; border-bottom: 1px solid #eee; display: flex; justify-content: space-between; align-items: center;">
                <div style="flex: 1;">
                    <strong>№${runner.start_number}</strong> ${runner.full_name}
                    <div style="font-size: 11px; color: #666;">${runner.category || ''}</div>
                    <div style="font-size: 11px; color: ${statusColor}; margin-top: 3px;">● ${getStatusText(runner.status)}</div>
                </div>
                <button
                    onclick="selectRunner('${runner.id}')"
                    style="padding: 6px 12px;
                           background: ${isSelected ? '#90EE90' : canSelect ? '#EE2D62' : '#ccc'};
                           color: white;
                           border: none;
                           border-radius: 3px;
                           cursor: ${canSelect ? 'pointer' : 'not-allowed'};
                           font-weight: bold;"
                    ${!canSelect && !isSelected ? 'disabled' : ''}
                >
                    ${isSelected ? '✓' : '+'}
                </button>
            </div>
        `;
    });

    html += '</div>';
    resultsDiv.innerHTML = html;
    resultsDiv.style.display = 'block';
}

function setupSearch() {
    const searchInput = document.getElementById('searchInput');
    if (!searchInput) return;

    let searchTimeout;
    searchInput.addEventListener('input', () => {
        clearTimeout(searchTimeout);
        searchTimeout = setTimeout(searchRunners, 300);
    });

    document.addEventListener('click', (event) => {
        const resultsDiv = document.getElementById('searchResults');
        if (resultsDiv && !searchInput.contains(event.target) && !resultsDiv.contains(event.target)) {
            resultsDiv.style.display = 'none';
        }
    });
}


// ============================================
// АНАЛИТИКА
// ============================================

async function loadAnalytics() {
    try {
        console.log('📊 Загрузка аналитики для Event 67');

        const response = await fetch(
            `${CONFIG.API_BASE}/event-results?event_id=${CONFIG.EVENT_ID}&v=${Date.now()}`
        );

        if (!response.ok) throw new Error('Ошибка загрузки результатов');

        const data = await response.json();
        const results = data.results || [];

        const stats = {
            total:        results.length,
            finished:     results.filter(r => r.race_status === 'Finished').length,
            not_started:  results.filter(r => r.race_status === 'Not started').length,
            running:      results.filter(r => r.race_status === 'Running').length,
            withdrawn:    results.filter(r => r.race_status === 'Withdrawn').length,
            disqualified: results.filter(r => r.race_status === 'Disqualifed' || r.race_status === 'Disqualified').length,
            male:         results.filter(r => r.sex === 'Мужчина').length,
            female:       results.filter(r => r.sex === 'Женщина').length
        };

        const analyticsPanel = document.getElementById('analyticsContent');
        if (analyticsPanel) {
            analyticsPanel.innerHTML = renderAnalyticsHTML(stats, results);
        }

    } catch (error) {
        console.error('❌ Ошибка загрузки аналитики:', error);
        const analyticsPanel = document.getElementById('analyticsContent');
        if (analyticsPanel) {
            analyticsPanel.innerHTML = `<p style="color: red;">Ошибка загрузки аналитики: ${error.message}</p>`;
        }
    }
}

function renderAnalyticsHTML(stats, results) {
    const finishedRunners = results
        .filter(r => r.race_status === 'Finished' && r.rank_absolute)
        .sort((a, b) => (a.rank_absolute || 999) - (b.rank_absolute || 999))
        .slice(0, 5);

    const topHTML = finishedRunners.length
        ? finishedRunners.map(runner => `
            <tr style="border-bottom: 1px solid #eee;">
                <td style="padding: 8px; text-align: center;">${runner.rank_absolute}</td>
                <td style="padding: 8px; text-align: center;">${runner.start_number || '-'}</td>
                <td style="padding: 8px;"><strong>${runner.surname} ${runner.name}</strong></td>
                <td style="padding: 8px;">${runner.category || '-'}</td>
                <td style="padding: 8px; font-family: monospace;">${parseDuration(runner.time_gun_finish) || '-'}</td>
                <td style="padding: 8px; font-family: monospace;">${parseDuration(runner.finish_pace_avg) || '-'}</td>
            </tr>
        `).join('')
        : '<tr><td colspan="6" style="padding: 10px; text-align: center;">Результатов нет</td></tr>';

    const totalSafe = stats.total || 1;

    return `
        <div class="analytics-section">
            <h3>📊 Ночной забег 2025 (5 км) — Общая статистика</h3>
            <div class="stats-grid">
                <div class="stat-card">
                    <div class="stat-card-value">${stats.total}</div>
                    <div class="stat-card-label">Всего участников</div>
                </div>
                <div class="stat-card">
                    <div class="stat-card-value" style="color: #4CAF50;">${stats.finished}</div>
                    <div class="stat-card-label">Финишировали</div>
                </div>
                <div class="stat-card">
                    <div class="stat-card-value" style="color: #EE2D62;">${stats.running}</div>
                    <div class="stat-card-label">На трассе</div>
                </div>
                <div class="stat-card">
                    <div class="stat-card-value" style="color: #FF9800;">${stats.not_started}</div>
                    <div class="stat-card-label">Не стартовали</div>
                </div>
                <div class="stat-card">
                    <div class="stat-card-value" style="color: #f44336;">${stats.withdrawn + stats.disqualified}</div>
                    <div class="stat-card-label">Снялись</div>
                </div>
            </div>
        </div>

        <div class="analytics-section">
            <h3>👥 Распределение по полу</h3>
            <div class="gender-stats">
                <div class="gender-stat">
                    <div class="gender-title">👨 Мужчины</div>
                    <div class="gender-count">${stats.male}</div>
                    <div class="gender-avg-time">${((stats.male / totalSafe) * 100).toFixed(1)}%</div>
                </div>
                <div class="gender-stat">
                    <div class="gender-title">👩 Женщины</div>
                    <div class="gender-count">${stats.female}</div>
                    <div class="gender-avg-time">${((stats.female / totalSafe) * 100).toFixed(1)}%</div>
                </div>
            </div>
        </div>

        <div class="analytics-section">
            <h3>🏆 Топ-5 финишёров</h3>
            <div style="overflow-x: auto;">
                <table style="width: 100%; border-collapse: collapse; font-size: 13px;">
                    <thead>
                        <tr style="background: #f5f5f5; border-bottom: 2px solid #ddd;">
                            <th style="padding: 10px; text-align: center;">#</th>
                            <th style="padding: 10px; text-align: center;">№</th>
                            <th style="padding: 10px; text-align: left;">Фамилия Имя</th>
                            <th style="padding: 10px; text-align: left;">Категория</th>
                            <th style="padding: 8px; text-align: left;">Офиц. время</th>
                            <th style="padding: 8px; text-align: left;">Темп</th>
                        </tr>
                    </thead>
                    <tbody>
                        ${topHTML}
                    </tbody>
                </table>
            </div>
        </div>
    `;
}


// ============================================
// АВТООБНОВЛЕНИЕ
// ============================================

function startAutoUpdate() {
    console.log(`⏱️ Автообновление запущено (каждые ${CONFIG.UPDATE_INTERVAL / 1000}с)`);

    setInterval(async () => {
        if (isUpdating) return;
        isUpdating = true;

        try {
            await loadAllRunners();

            selectedRunnerIds.forEach(runnerId => {
                const runner = allRunners.find(r => String(r.id) === String(runnerId));
                if (runner) updateRunnerMarkerPosition(runner);
            });

            updateSelectedList();
            updateStatus(`🔄 Обновлено ${new Date().toLocaleTimeString()} | Event 67`);

        } catch (error) {
            console.error('❌ Ошибка при обновлении:', error);
        } finally {
            isUpdating = false;
        }
    }, CONFIG.UPDATE_INTERVAL);
}


// ============================================
// ПРОЧЕЕ
// ============================================

function closeAllPopups() {
    for (const [id] of activePopups) {
        const marker = runnerMarkers[id];
        if (marker && marker._popup) marker.closePopup();
    }
    activePopups.clear();
}