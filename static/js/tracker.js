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
    STORAGE_KEY: 'night_run_selected_runners',
    // Координаты контрольной точки 1 (разворот)
    KT1_COORDS: [55.9988248, 92.8350464]
};

// Глобальные переменные
let map = null;
let routeLayer = null;
let routeCoordinates = [];
let runnerMarkers = {};
let selectedRunnerIds = new Set();
let allRunners = [];
let routeType = 'shuttle';
let runnerPositions = {};
let activePopups = new Map();
let eventDistance = 0; // Дистанция события в км

// Объект для плавной анимации позиций
let runnerAnimations = {};
let animationFrameId = null;

// Максимальная дистанция каждого маркера — никогда не движемся назад
const runnerMaxDistance = {};

// Ключ-префикс для sessionStorage: привязан к событию, переживает перезагрузку страницы
const _maxDistKeyPrefix = () => `km_max_dist_${CONFIG.EVENT_ID || CONFIG.EVENT_NAME || 'ev'}_`;

function _loadMaxDist(rId) {
    try { return parseFloat(sessionStorage.getItem(_maxDistKeyPrefix() + rId)) || 0; }
    catch { return 0; }
}
function _saveMaxDist(rId, dist) {
    try { sessionStorage.setItem(_maxDistKeyPrefix() + rId, String(dist)); }
    catch {}
}

// Время сервера в момент последнего ответа API (Unix ms) — для экстраполяции позиции
let serverTimeUnix = Date.now();
// Абсолютное время выстрела пистолета (Unix ms) — для астрономического времени старта
let raceGunUnixMs = null;

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

/**
 * Находит последнюю пройденную контрольную точку
 * Возвращает {name, time, pace} или null
 */
function getLastCheckpoint(runner) {
    if (!runner.checkpoints) return null;
    
    const checkpoints = [
        { code: 'start', name: 'Старт', data: { time: '0', pace: '0' } }, // Start не имеет реальных данных
        { code: 'kt1', name: 'КТ1', data: runner.checkpoints.kt1 },
        { code: 'kt2', name: 'КТ2', data: runner.checkpoints.kt2 },
        { code: 'kt3', name: 'КТ3', data: runner.checkpoints.kt3 },
        { code: 'kt4', name: 'КТ4', data: runner.checkpoints.kt4 },
        { code: 'kt5', name: 'КТ5', data: runner.checkpoints.kt5 }
    ];
    
    let lastCheckpoint = null;
    
    for (const checkpoint of checkpoints) {
        if (checkpoint.data && checkpoint.data.time) {
            lastCheckpoint = {
                name: checkpoint.name,
                code: checkpoint.code,
                time: checkpoint.data.time,
                pace: checkpoint.data.pace
            };
        }
    }
    
    return lastCheckpoint;
}

/**
 * Преобразует время в формате PT48S в секунды
 */
function durationToSeconds(duration) {
    if (!duration || duration === 'null' || duration === null) return 0;
    if (typeof duration === 'number') return duration;
    
    const match = String(duration).match(/PT(?:(\d+)H)?(?:(\d+)M)?(?:(\d+)S)?/);
    if (!match) return 0;
    
    return (parseInt(match[1] || 0) * 3600) +
           (parseInt(match[2] || 0) * 60) +
           parseInt(match[3] || 0);
}

/**
 * Форматирует время в секундах в читаемый формат MM:SS или HH:MM:SS
 */
function secondsToTime(totalSeconds) {
    if (!totalSeconds) return '--:--';
    const h = Math.floor(totalSeconds / 3600);
    const m = Math.floor((totalSeconds % 3600) / 60);
    const s = totalSeconds % 60;
    
    if (h > 0) {
        return `${h}:${String(m).padStart(2, '0')}:${String(s).padStart(2, '0')}`;
    }
    return `${m}:${String(s).padStart(2, '0')}`;
}

/**
 * Вычисляет темп в формате м'сс"/км на основе времени (ISO 8601) и расстояния
 * Темп = (время в секундах / расстояние в км) в формате минуты'секунды"/км
 */
function calculatePaceFromTime(isoTime, distanceKm) {
    if (!isoTime || !distanceKm || distanceKm <= 0) return null;
    
    const totalSeconds = durationToSeconds(isoTime);
    if (totalSeconds <= 0) return null;
    
    const distance = parseFloat(distanceKm);
    if (distance <= 0) return null;
    
    // Вычисляем секунды на км
    const secondsPerKm = totalSeconds / distance;
    
    // Преобразуем в соответствующее количество минут и секунд
    const minutes = Math.floor(secondsPerKm / 60);
    const seconds = Math.round(secondsPerKm % 60);
    
    return `${minutes}'${String(seconds).padStart(2, '0')}"/km`;
}

/**
 * Находит ближайшую точку на маршруте к заданным координатам
 * Возвращает {index, percent} - индекс точки и процент маршрута
 */
function findNearestPointOnRoute(targetLat, targetLon) {
    if (!routeCoordinates || routeCoordinates.length === 0) {
        return { index: 0, percent: 0 };
    }

    let minDistance = Infinity;
    let nearestIndex = 0;

    // Вычисляем расстояние Хаверсина между точками
    for (let i = 0; i < routeCoordinates.length; i++) {
        const [lat, lon] = routeCoordinates[i];
        const dLat = (targetLat - lat) * Math.PI / 180;
        const dLon = (targetLon - lon) * Math.PI / 180;
        const a = Math.sin(dLat / 2) * Math.sin(dLat / 2) +
                  Math.cos(lat * Math.PI / 180) * Math.cos(targetLat * Math.PI / 180) *
                  Math.sin(dLon / 2) * Math.sin(dLon / 2);
        const c = 2 * Math.atan2(Math.sqrt(a), Math.sqrt(1 - a));
        const distance = 6371 * c; // Радиус Земли в км

        if (distance < minDistance) {
            minDistance = distance;
            nearestIndex = i;
        }
    }

    const maxIndex = routeCoordinates.length - 1;
    const percent = (nearestIndex / maxIndex) * 100;
    return { index: nearestIndex, percent };
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
    loadSelectedFromStorage();
    await initMap();
    await loadAllRunners();

    if (selectedRunnerIds.size > 0) {
        updateSelectedList();
        initializeSelectedRunnersMarkers();
    }

    setupSearch();
    await loadAnalytics();
    startAutoUpdate();
    startAnimationLoop();

    updateStatus('✅ Трекер запущен (Event 67 - Ночной забег)');
}


// ============================================
// РАБОТА С КАРТОЙ
// ============================================

async function initMap() {
    map = L.map('map').setView([56.0075, 92.7246], 15);
    map.attributionControl.setPrefix('');

    L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', {
        attribution: '© OpenStreetMap contributors'
    }).addTo(map);

    await loadRouteFromAPI();
}

async function loadRouteFromAPI() {
    try {
        updateStatus('Загрузка GPX маршрута...');
        
        const gpxPath = getGPXPathForEvent(CONFIG.EVENT_NAME);
        
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
        
        return coordinates;
        
    } catch (error) {
        console.error('❌ Ошибка при парсинге GPX:', error);
        return [];
    }
}


// ============================================
// ЗАГРУЗКА УЧАСТНИКОВ
// ============================================

async function loadAllRunners() {
    try {
        updateStatus('Загрузка участников...');

        const _params = new URLSearchParams({ v: Date.now() });
        if (CONFIG.EVENT_ID != null) _params.set('event_id', CONFIG.EVENT_ID);
        else if (CONFIG.EVENT_NAME)  _params.set('event_name', CONFIG.EVENT_NAME);
        const response = await fetch(`${CONFIG.API_BASE}/event-results?${_params}`);

        if (!response.ok) throw new Error(`Ошибка загрузки: ${response.status}`);

        const data = await response.json();

        // Синхронизируем время сервера для точной экстраполяции позиций
        if (data.server_time_unix) serverTimeUnix = data.server_time_unix;
        if (data.race_gun_unix_ms) raceGunUnixMs = data.race_gun_unix_ms;

        // Загружаем дистанцию события из первого участника
        if (data.results && data.results.length > 0) {
            eventDistance = parseFloat(data.results[0].distance) || 0;
        }

        allRunners = (data.results || []).map((runner) => {
            
            // Извлекаем данные KT1 из вложенного объекта checkpoints
            // ВАЖНО: поле называется 'time', а не 'time_clear'
            const kt1Data = runner.checkpoints?.kt1;
            let kt1Time = kt1Data?.time;
            
            // Обработка невалидных значений
            if (kt1Time === 'undefined' || kt1Time === undefined || kt1Time === null || kt1Time === 'null') {
                kt1Time = null;
            }
            
            // Вычисляем темпы на основе времени финиша и дистанции (если API их не вернул)
            const distanceKm = runner.distance || runner.event_distance || eventDistance;
            const calculatedGunPace = calculatePaceFromTime(runner.time_gun_finish, distanceKm);
            const calculatedCleanPace = calculatePaceFromTime(runner.time_clear_finish, distanceKm);
            
            return {
                id:                   runner.id || runner.start_number,
                start_number:         runner.start_number,
                surname:              runner.surname || '',
                name:                 runner.name || '',
                full_name:            `${runner.surname || ''} ${runner.name || ''}`.trim(),
                sex:                  runner.sex,
                category:             runner.category || '',
                status:               runner.race_status,
                time_gun_finish:      parseDuration(runner.time_gun_finish),
                time_clear_finish:    parseDuration(runner.time_clear_finish),
                // ВАЖНО: сохраняем ИСХОДНОЕ значение (из nested checkpoints.kt1.time) для проверки наличия KT1
                time_clear_kt1_raw:   kt1Time,
                time_clear_kt1:       parseDuration(kt1Time),
                finish_pace_avg:      parseDuration(runner.finish_pace_avg),
                // Вычисляем темпы из времени и дистанции, так как API их не возвращает
                finish_pace_avg_gun:  calculatedGunPace,
                finish_pace_avg_clean: calculatedCleanPace,
                rank_absolute:        runner.rank_absolute,
                rank_sex:             runner.rank_sex,
                rank_category:        runner.rank_category,
                bib:                  runner.start_number,
                dorsal:               runner.start_number,
                checkpoints:          runner.checkpoints || {},
                // Live-данные для анимации
                speed:                runner.speed != null ? runner.speed : 10.0,
                current_distance:     runner.current_distance || 0,
                current_pace:         runner.current_pace || '6:00',
                pace_source:          runner.pace_source || '',
                prev_year:            runner.prev_year || null,
                time_clear_start_s:   runner.time_clear_start_s ?? null,
            };
        });

        // Диагностика: что API вернул для отслеживаемых участников
        selectedRunnerIds.forEach(id => {
            const r = allRunners.find(x => String(x.id) === String(id));
            if (r) console.log(
                `[API_CHECK] #${r.start_number} ${r.full_name}:`,
                `status=${r.status}`,
                `speed=${r.speed}`,
                `current_pace=${r.current_pace}`,
                `pace_source=${r.pace_source}`
            );
        });

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
    runnerPositions = {};
    runnerAnimations = {};

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
    const status = (runner.status || '').toLowerCase();
    
    // Астрономическое время старта (если известно время выстрела пистолета)
    let startClockHTML = '';
    if (raceGunUnixMs != null && runner.time_clear_start_s != null) {
        const startUnix = raceGunUnixMs + runner.time_clear_start_s * 1000;
        const startTime = new Date(startUnix).toLocaleTimeString('ru-RU', { hour: '2-digit', minute: '2-digit', second: '2-digit' });
        startClockHTML = `<div><strong>Время старта:</strong> ${startTime}</div>`;
    }

    // Базовая информация
    const baseHTML = `
        <div style="font-size: 12px; min-width: 220px; text-align: left;">
            <div style="text-align: center; margin-bottom: 8px;">
                <div><strong>№${runner.start_number}</strong></div>
                <div><strong>${runner.full_name}</strong></div>
            </div>
            <div style="border-top: 1px solid #ddd; padding-top: 8px; margin-bottom: 8px;">
                ${runner.category ? `<div><strong>Категория:</strong> ${runner.category}</div>` : ''}
                ${startClockHTML}
            </div>
    `;
    
    let contentHTML = '';
    
    if (status.includes('finish')) {
        // FINISHED - расширенная информация с темпами и местами
        const officialTime = runner.time_gun_finish
            ? `<div><strong>Официальное время:</strong> ${runner.time_gun_finish}</div>`
            : '';
        const clearTime = runner.time_clear_finish        
            ? `<div><strong>Чистое время:</strong> ${runner.time_clear_finish}</div>` 
            : '';
        const officialPace = runner.finish_pace_avg_gun
            ? `<div><strong>Официальный темп:</strong> ${runner.finish_pace_avg_gun}</div>`
            : '';
        const cleanPace = runner.finish_pace_avg_clean
            ? `<div><strong>Чистый темп:</strong> ${runner.finish_pace_avg_clean}</div>`
            : '';
        const rankSex = runner.rank_sex
            ? `<div><strong>Место (пол):</strong> ${runner.rank_sex}</div>`
            : '';
        const rankCategory = runner.rank_category
            ? `<div><strong>Место (категория):</strong> ${runner.rank_category}</div>`
            : '';
        
        contentHTML = `
            <div style="border-top: 1px solid #ddd; padding-top: 8px;">
                <div><strong>Статус:</strong> ${getStatusText(runner.status)}</div>
                <div><strong>Место (абсолют):</strong> ${runner.rank_absolute || '-'}</div>
                ${officialTime}
                ${clearTime}
                ${officialPace}
                ${cleanPace}
                ${rankSex}
                ${rankCategory}
            </div>
        `;
    } else if (status.includes('running') || status.includes('started')) {
        // RUNNING - подробная информация
        const lastCP = getLastCheckpoint(runner);
        const lastCPTime = lastCP ? parseDuration(lastCP.time) : '-';
        const lastCPPace = lastCP ? parseDuration(lastCP.pace) : '-';
        
        // Прогнозируемое время финиша
        let predictedFinish = '-';
        if (lastCP && lastCP.pace) {
            const paceSeconds = durationToSeconds(lastCP.pace);
            if (paceSeconds > 0 && eventDistance > 0) {
                const predictedSeconds = (eventDistance * 1000) / (1000 / paceSeconds); // расстояние в км * темп на км
                predictedFinish = secondsToTime(predictedSeconds);
            }
        }
        
        let paceLabel = 'Текущий темп';
        if (runner.pace_source === 'personal' && runner.prev_year) {
            paceLabel = `Прогноз (личный ${runner.prev_year})`;
        } else if (runner.pace_source === 'category' && runner.prev_year) {
            paceLabel = `Прогноз (ср. кат. ${runner.prev_year})`;
        }
        const currentPace = runner.current_pace
            ? `<div><strong>${paceLabel}:</strong> ${runner.current_pace} мин/км</div>`
            : '';

        contentHTML = `
            <div style="border-top: 1px solid #ddd; padding-top: 8px;">
                <div><strong>Статус:</strong> ${getStatusText(runner.status)}</div>
                <div><strong>Последняя КТ:</strong> ${lastCP ? lastCP.name : '-'}</div>
                <div><strong>Время на КТ:</strong> ${lastCPTime}</div>
                <div><strong>Темп на КТ:</strong> ${lastCPPace}</div>
                ${currentPace}
                <div><strong>Место:</strong> ${runner.rank_absolute || '-'}</div>
                <div style="border-top: 1px solid #eee; margin-top: 6px; padding-top: 6px;">
                    <div><strong>Прогноз финиша:</strong> ${predictedFinish}</div>
                </div>
            </div>
        `;
    } else {
        // NOT STARTED
        contentHTML = `
            <div style="border-top: 1px solid #ddd; padding-top: 8px;">
                <div><strong>Статус:</strong> ${getStatusText(runner.status)}</div>
            </div>
        `;
    }
    
    return baseHTML + contentHTML + '</div>';
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
}

/**
 * Вычисляет текущую дистанцию участника (км) на основе данных последнего API-ответа.
 * Экстраполирует позицию от момента ответа сервера до текущего момента.
 * Не зависит от накопленного состояния — безопасна при рефреше и пересэлекте.
 */
function calculateCurrentDistanceKm(runner) {
    const rId = String(runner.id);
    const elapsedSinceApiH = (Date.now() - serverTimeUnix) / 3_600_000;
    const speed = (runner.speed > 0) ? runner.speed : 10.0;

    // Экстраполируем позицию от момента последнего API-ответа до сейчас.
    // Бэкенд больше не кэпит на КТ, поэтому current_distance растёт непрерывно.
    const apiExtrapolated = Math.max(0, (runner.current_distance || 0) + speed * elapsedSinceApiH);

    // Защита от прыжков назад: используем sessionStorage только если
    // значение из него не сильно опережает то, что вернул сервер.
    // Это защищает от устаревших данных предыдущей сессии.
    let storedMax = _loadMaxDist(rId);
    const serverDist = runner.current_distance || 0;
    if (storedMax > 0 && serverDist > 0 && storedMax > serverDist * 1.1) {
        // Stored max на >10% впереди сервера — данные устарели, сбрасываем
        storedMax = 0;
        try { sessionStorage.removeItem(_maxDistKeyPrefix() + rId); } catch {}
    }

    const dist = Math.max(runnerMaxDistance[rId] || 0, storedMax, apiExtrapolated);
    runnerMaxDistance[rId] = dist;
    _saveMaxDist(rId, dist);
    return dist;
}

function updateRunnerMarkerPosition(runner) {
    const runnerId = String(runner.id);
    const marker = runnerMarkers[runnerId];

    if (!marker || !routeCoordinates.length) return;

    // Определяем целевую позицию на основе времени (не накопленного состояния)
    let targetProgressPercent = 0;
    let shouldTeleport = false;

    const s = (runner.status || '').toLowerCase();
    const totalDistKm = eventDistance || 5.0;

    if (s.includes('notstart') || s.includes('not started')) {
        targetProgressPercent = 0;
    } else if (s.includes('finish')) {
        targetProgressPercent = 100;
        shouldTeleport = true;
    } else if (s.includes('running') || s.includes('started')) {
        // Позиция = текущая дистанция от сервера + экстраполяция по времени
        const distKm = calculateCurrentDistanceKm(runner);
        targetProgressPercent = Math.min(100, distKm / totalDistKm * 100);
    }

    const maxIndex = Math.max(0, routeCoordinates.length - 1);
    const targetIndex = Math.min(maxIndex, Math.round(maxIndex * targetProgressPercent / 100));

    // Инициализируем анимацию если её еще нет
    if (!runnerAnimations[runnerId]) {
        runnerAnimations[runnerId] = {
            currentIndex: targetIndex,
            targetIndex: targetIndex,
            startTime: Date.now(),
            animationDuration: shouldTeleport ? 0 : CONFIG.UPDATE_INTERVAL
        };
    } else {
        // ВАЖНО: перед перезапуском анимации сохраняем текущую фактическую позицию
        // чтобы избежать отскока к целому индексу, ЕСЛИ это не телепорт
        const now = Date.now();
        const anim = runnerAnimations[runnerId];
        
        if (shouldTeleport) {
            // При телепорте сразу устанавливаем целевой индекс
            anim.currentIndex = targetIndex;
            anim.targetIndex = targetIndex;
        } else {
            // При плавном движении сохраняем текущую интерполированную позицию
            const elapsed = Math.max(0, now - anim.startTime);
            const progress = anim.animationDuration > 0 ? Math.min(1, elapsed / anim.animationDuration) : 1;
            const currentIndex = anim.currentIndex + (anim.targetIndex - anim.currentIndex) * progress;
            anim.currentIndex = currentIndex;
            anim.targetIndex = targetIndex;
        }
        
        // Обновляем время и длительность анимации
        anim.startTime = now;
        anim.animationDuration = shouldTeleport ? 0 : CONFIG.UPDATE_INTERVAL;
    }

    marker.setIcon(buildMarkerIcon(runner));

    if (marker.getPopup()) {
        marker.getPopup().setContent(buildPopupContent(runner));
    }
}

/**
 * Плавная анимация позиции маркера на протяжении интервала обновления
 * Интерполирует позицию между текущим и целевым индексом на маршруте
 */
function animateRunnerFrame() {
    const now = Date.now();

    Object.entries(runnerAnimations).forEach(([runnerId, anim]) => {
        const marker = runnerMarkers[runnerId];
        if (!marker || !routeCoordinates.length) return;

        const elapsed = now - anim.startTime;
        const progress = Math.min(1, elapsed / anim.animationDuration);

        // Линейная интерполяция индекса
        const currentIndex = anim.currentIndex + (anim.targetIndex - anim.currentIndex) * progress;
        
        // Получаем позиции для интерполяции между двумя точками маршрута
        const floorIndex = Math.floor(currentIndex);
        const ceilIndex = Math.ceil(currentIndex);
        const fracIndex = currentIndex - floorIndex;

        let position;
        if (floorIndex === ceilIndex) {
            position = routeCoordinates[floorIndex];
        } else {
            // Интерполируем между двумя соседними точками
            const p1 = routeCoordinates[floorIndex];
            const p2 = routeCoordinates[ceilIndex];
            position = [
                p1[0] + (p2[0] - p1[0]) * fracIndex,
                p1[1] + (p2[1] - p1[1]) * fracIndex
            ];
        }

        if (position) {
            marker.setLatLng(position);
        }

        // Когда анимация завершена
        if (progress >= 1) {
            anim.currentIndex = anim.targetIndex;
            anim.startTime = now; // Готово к следующей анимации
        }
    });

    // Продолжаем анимационный цикл
    animationFrameId = requestAnimationFrame(animateRunnerFrame);
}

/**
 * Запускает основной animation loop для плавного движения маркеров
 */
function startAnimationLoop() {
    if (!animationFrameId) {
        animateRunnerFrame();
    }
}

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

    if (runnerMarkers[runnerId_str]) {
        // Маркер уже существует (был скрыт при десэлекте) — просто показываем
        if (!map.hasLayer(runnerMarkers[runnerId_str])) {
            runnerMarkers[runnerId_str].addTo(map);
        }
    } else {
        // Создаём новый маркер; позиция вычислится по времени на первом тике
        createRunnerMarker(runner);
    }

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

    // Только скрываем маркер с карты, не удаляем объект и анимацию
    // При повторном выборе маркер восстановится на правильной позиции
    if (runnerMarkers[runnerId_str]) {
        if (map.hasLayer(runnerMarkers[runnerId_str])) {
            map.removeLayer(runnerMarkers[runnerId_str]);
        }
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


        const _aParams = new URLSearchParams({ v: Date.now() });
        if (CONFIG.EVENT_ID != null) _aParams.set('event_id', CONFIG.EVENT_ID);
        else if (CONFIG.EVENT_NAME)  _aParams.set('event_name', CONFIG.EVENT_NAME);
        const response = await fetch(`${CONFIG.API_BASE}/event-results?${_aParams}`);

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


    let isLoading = false;

    setInterval(() => {
        // Запускаем загрузку параллельно, БЕЗ await - не блокируем цикл
        if (!isLoading) {
            isLoading = true;
            loadAllRunners()
                .catch(error => console.error('❌ Ошибка при загрузке данных:', error))
                .finally(() => { isLoading = false; });
        }

        // Обновляем позиции маркеров НЕЗАВИСИМО от загрузки данных
        // Маркеры продолжат плавно двигаться, даже если идёт загрузка
        selectedRunnerIds.forEach(runnerId => {
            const runner = allRunners.find(r => String(r.id) === String(runnerId));
            if (runner) updateRunnerMarkerPosition(runner);
        });

        updateSelectedList();
        updateStatus(`🔄 Обновлено ${new Date().toLocaleTimeString()} | Event 67`);

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