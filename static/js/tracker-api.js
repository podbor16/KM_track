// tracker-api.js: глобальное состояние, утилиты, API, запуск

// Конфигурация
const CONFIG = {
    API_BASE: '/api',
    UPDATE_INTERVAL: 2000,
    MAX_SELECTED: 5,
    EVENT_NAME: 'night_run',
    EVENT_DB_NAME: 'Ночной забег',
    EVENT_YEAR: new Date().getFullYear(),
    EVENT_ID: 67,
    STORAGE_KEY: 'night_run_selected_runners',
    KT1_COORDS: [55.9988248, 92.8350464],
    GPX_FILE: '/static/map/2026/night_run.gpx',
    START_LAT: 56.0075,
    START_LON: 92.7246
};

// Глобальные переменные (доступны всем модулям)
let map = null;
let routeLayer = null;
let routeCoordinates = [];
let runnerMarkers = {};
let selectedRunnerIds = new Set();
let allRunners = [];
let routeType = 'shuttle';
let runnerPositions = {};
let activePopups = new Map();
let eventDistance = 0;

let runnerAnimations = {};
let animationFrameId = null;

const runnerMaxDistance = {};
const _maxDistKeyPrefix = () => `km_max_dist_${CONFIG.EVENT_ID || CONFIG.EVENT_NAME || 'ev'}_`;

function _loadMaxDist(rId) {
    try { return parseFloat(sessionStorage.getItem(_maxDistKeyPrefix() + rId)) || 0; }
    catch { return 0; }
}
function _saveMaxDist(rId, dist) {
    try { sessionStorage.setItem(_maxDistKeyPrefix() + rId, String(dist)); }
    catch {}
}

let serverTimeUnix = Date.now();
let raceGunUnixMs = null;

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
    if (!String(duration).startsWith('PT')) return duration;

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
        'Withdrawn':    'Снялся',
        'withdrawn':    'Снялся',
    };
    return statusMap[status] || status;
}

function getStatusColor(status) {
    const s = (status || '').toLowerCase();
    if (s.includes('finish'))  return STATUS_COLORS.finished;
    if (s.includes('running') || s.includes('started')) return STATUS_COLORS.running;
    return STATUS_COLORS.notstarted;
}

function updateStatus(message) {
    const statusPanel = document.getElementById('statusPanel');
    if (statusPanel) statusPanel.textContent = message;
}

function getLastCheckpoint(runner) {
    if (!runner.checkpoints) return null;

    const checkpoints = [
        { code: 'start', name: 'Старт', data: { time: '0', pace: '0' } },
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

function durationToSeconds(duration) {
    if (!duration || duration === 'null' || duration === null) return 0;
    if (typeof duration === 'number') return duration;

    const match = String(duration).match(/PT(?:(\d+)H)?(?:(\d+)M)?(?:(\d+)S)?/);
    if (!match) return 0;

    return (parseInt(match[1] || 0) * 3600) +
           (parseInt(match[2] || 0) * 60) +
           parseInt(match[3] || 0);
}

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

function calculatePaceFromTime(isoTime, distanceKm) {
    if (!isoTime || !distanceKm || distanceKm <= 0) return null;

    const totalSeconds = durationToSeconds(isoTime);
    if (totalSeconds <= 0) return null;

    const distance = parseFloat(distanceKm);
    if (distance <= 0) return null;

    const secondsPerKm = totalSeconds / distance;
    const minutes = Math.floor(secondsPerKm / 60);
    const seconds = Math.round(secondsPerKm % 60);

    return `${minutes}'${String(seconds).padStart(2, '0')}"/km`;
}

function findNearestPointOnRoute(targetLat, targetLon) {
    if (!routeCoordinates || routeCoordinates.length === 0) {
        return { index: 0, percent: 0 };
    }

    let minDistance = Infinity;
    let nearestIndex = 0;

    for (let i = 0; i < routeCoordinates.length; i++) {
        const [lat, lon] = routeCoordinates[i];
        const dLat = (targetLat - lat) * Math.PI / 180;
        const dLon = (targetLon - lon) * Math.PI / 180;
        const a = Math.sin(dLat / 2) * Math.sin(dLat / 2) +
                  Math.cos(lat * Math.PI / 180) * Math.cos(targetLat * Math.PI / 180) *
                  Math.sin(dLon / 2) * Math.sin(dLon / 2);
        const c = 2 * Math.atan2(Math.sqrt(a), Math.sqrt(1 - a));
        const distance = 6371 * c;

        if (distance < minDistance) {
            minDistance = distance;
            nearestIndex = i;
        }
    }

    return {
        index: nearestIndex,
        percent: (nearestIndex / (routeCoordinates.length - 1)) * 100
    };
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
    // Загружаем конфиг активного забега из API — перезаписываем всё из серверного рендера
    try {
        const cfg = await fetch('/api/current-event').then(r => r.json());
        if (cfg.gpx_file)     CONFIG.GPX_FILE      = '/' + cfg.gpx_file;
        if (cfg.start_lat)    CONFIG.START_LAT     = cfg.start_lat;
        if (cfg.start_lon)    CONFIG.START_LON     = cfg.start_lon;
        if (cfg.event)        CONFIG.EVENT_NAME    = cfg.event;
        if (cfg.name)         CONFIG.EVENT_DB_NAME = cfg.name;
        if (cfg.year)         CONFIG.EVENT_YEAR    = cfg.year;
        if (cfg.storage_key)  CONFIG.STORAGE_KEY   = cfg.storage_key;
        // Явно сбрасываем EVENT_ID из YAML — null если не задан, иначе значение из БД
        CONFIG.EVENT_ID = cfg.db_event_id ?? null;
    } catch {}

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

    updateStatus(`✅ Трекер запущен (${CONFIG.EVENT_DB_NAME} ${CONFIG.EVENT_YEAR})`);
}


// ============================================
// ЗАГРУЗКА ДАННЫХ ИЗ API
// ============================================

async function loadAllRunners() {
    try {
        updateStatus('Загрузка участников...');

        const _params = new URLSearchParams({ v: Date.now() });
        if (CONFIG.EVENT_ID != null) _params.set('event_id', CONFIG.EVENT_ID);
        else if (CONFIG.EVENT_DB_NAME) _params.set('event_name', CONFIG.EVENT_DB_NAME);
        else if (CONFIG.EVENT_NAME)    _params.set('event_name', CONFIG.EVENT_NAME);
        const response = await fetch(`${CONFIG.API_BASE}/event-results?${_params}`);

        if (!response.ok) throw new Error(`Ошибка загрузки: ${response.status}`);

        const data = await response.json();

        if (data.server_time_unix) serverTimeUnix = data.server_time_unix;
        if (data.race_gun_unix_ms) raceGunUnixMs = data.race_gun_unix_ms;

        if (data.results && data.results.length > 0) {
            eventDistance = parseFloat(data.results[0].distance) || 0;
        }

        allRunners = (data.results || []).map((runner) => {
            const kt1Data = runner.checkpoints?.kt1;
            let kt1Time = kt1Data?.time;

            if (kt1Time === 'undefined' || kt1Time === undefined || kt1Time === null || kt1Time === 'null') {
                kt1Time = null;
            }

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
                time_clear_kt1_raw:   kt1Time,
                time_clear_kt1:       parseDuration(kt1Time),
                finish_pace_avg:      parseDuration(runner.finish_pace_avg),
                finish_pace_avg_gun:  calculatedGunPace,
                finish_pace_avg_clean: calculatedCleanPace,
                rank_absolute:        runner.rank_absolute,
                rank_sex:             runner.rank_sex,
                rank_category:        runner.rank_category,
                bib:                  runner.start_number,
                dorsal:               runner.start_number,
                checkpoints:          runner.checkpoints || {},
                speed:                runner.speed != null ? runner.speed : 10.0,
                current_distance:     runner.current_distance || 0,
                current_pace:         runner.current_pace || '6:00',
                pace_source:          runner.pace_source || '',
                prev_year:            runner.prev_year || null,
                time_clear_start_s:   runner.time_clear_start_s ?? null,
            };
        });

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
// АНАЛИТИКА
// ============================================

async function loadAnalytics() {
    try {
        const _aParams = new URLSearchParams({ v: Date.now() });
        if (CONFIG.EVENT_ID != null) _aParams.set('event_id', CONFIG.EVENT_ID);
        else if (CONFIG.EVENT_DB_NAME) _aParams.set('event_name', CONFIG.EVENT_DB_NAME);
        else if (CONFIG.EVENT_NAME)    _aParams.set('event_name', CONFIG.EVENT_NAME);
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
    const evName = CONFIG.EVENT_DB_NAME || CONFIG.EVENT_NAME || 'Забег';
    const evYear = CONFIG.EVENT_YEAR || new Date().getFullYear();
    const distStr = (results.length > 0 && results[0].distance) ? ` (${results[0].distance})` : '';

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
            <h3>📊 ${evName} ${evYear}${distStr} — Общая статистика</h3>
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
        if (!isLoading) {
            isLoading = true;
            loadAllRunners()
                .catch(error => console.error('❌ Ошибка при загрузке данных:', error))
                .finally(() => { isLoading = false; });
        }

        selectedRunnerIds.forEach(runnerId => {
            const runner = allRunners.find(r => String(r.id) === String(runnerId));
            if (runner) updateRunnerMarkerPosition(runner);
        });

        updateSelectedList();
        updateStatus(`🔄 Обновлено ${new Date().toLocaleTimeString()} | ${CONFIG.EVENT_DB_NAME} ${CONFIG.EVENT_YEAR}`);

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
