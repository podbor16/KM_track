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
    CURRENT_DISTANCE: '',
    STORAGE_KEY: 'night_run_selected_runners',
    KT1_COORDS: [55.9988248, 92.8350464],
    GPX_FILE: '/static/map/2026/night_run.gpx',
    START_LAT: 56.0075,
    START_LON: 92.7246,
    LAPS: 1
};

// Глобальные переменные (доступны всем модулям)
let map = null;
let routeLayer = null;
let startMarker = null;
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

// Аналитика
let topFinishersGender = 'all'; // 'all' | 'Мужчина' | 'Женщина'
let _analyticsResults  = [];    // кэш последних results для перерисовки топа
let _lastAnalyticsRefresh = 0;  // throttle: не чаще раза в 10 сек
let eventCheckpoints = [];  // [{name, distance_km, lat, lon}, ...] — из /api/current-event
let activeRunnerId = null;  // id участника, чья панель сейчас открыта

let serverTimeUnix = Date.now();
let raceGunUnixMs = null;

const LAP_COLORS = ['#2196F3', '#4CAF50', '#FF9800', '#EE2D62'];

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

function getStatusColor(status, lap = 0) {
    const s = (status || '').toLowerCase();
    if (s.includes('finish'))  return STATUS_COLORS.finished;
    if (s.includes('running') || s.includes('started')) {
        if (lap > 0 && CONFIG.LAPS > 1) return LAP_COLORS[(lap - 1) % LAP_COLORS.length];
        return STATUS_COLORS.running;
    }
    return STATUS_COLORS.notstarted;
}

function updateStatus(message) {
    const statusPanel = document.getElementById('statusPanel');
    if (statusPanel) statusPanel.textContent = message;
}

function getLastCheckpoint(runner) {
    if (!runner.checkpoints) return null;

    const ktOrder = ['kt1', 'kt2', 'kt3', 'kt4', 'kt5', 'kt6', 'kt7'];
    let lastKtIdx = -1;  // индекс в ktOrder последней КТ с данными

    for (let i = 0; i < ktOrder.length; i++) {
        const data = runner.checkpoints[ktOrder[i]];
        if (data && data.time) lastKtIdx = i;
    }

    if (lastKtIdx < 0) return null;

    const cpIdx  = lastKtIdx + 1;  // индекс в eventCheckpoints (0=Старт)
    const cpName = eventCheckpoints[cpIdx]?.name ?? `КТ${lastKtIdx + 1}`;

    // Найти фактическую предыдущую КТ с данными (не обязательно i-1)
    let prevName = eventCheckpoints[0]?.name ?? 'Старт';
    for (let pi = lastKtIdx - 1; pi >= 0; pi--) {
        const prevData = runner.checkpoints[ktOrder[pi]];
        if (prevData && prevData.time) {
            prevName = eventCheckpoints[pi + 1]?.name ?? `КТ${pi + 1}`;
            break;
        }
    }

    const data = runner.checkpoints[ktOrder[lastKtIdx]];
    return {
        name:          cpName,
        prevName:      prevName,
        code:          ktOrder[lastKtIdx],
        cpIdx:         cpIdx,
        time:          data.time,
        pace:          data.pace,
        interval_pace: data.interval_pace,
    };
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

    return `${minutes}:${String(seconds).padStart(2, '0')} мин/км`;
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
        if (cfg.start_lat)    CONFIG.START_LAT     = cfg.start_lat;
        if (cfg.start_lon)    CONFIG.START_LON     = cfg.start_lon;
        if (cfg.event)        CONFIG.EVENT_NAME    = cfg.event;
        if (cfg.name)         CONFIG.EVENT_DB_NAME = cfg.name;
        if (cfg.year)         CONFIG.EVENT_YEAR    = cfg.year;
        if (cfg.storage_key)  CONFIG.STORAGE_KEY   = cfg.storage_key;

        // Выбрать дистанцию по умолчанию: ближайшую по дате к сегодня
        const trackedDistances = cfg.distances || [];
        let defaultDist = trackedDistances[0] || null;

        if (trackedDistances.length > 1) {
            const today = new Date().toISOString().slice(0, 10);
            const withDates = trackedDistances.filter(d => d.event_date);
            if (withDates.length > 0) {
                // Предпочитаем ближайшую будущую дату; если все прошли — берём самую последнюю
                const future = withDates.filter(d => d.event_date >= today);
                if (future.length > 0) {
                    defaultDist = future.sort((a, b) => a.event_date.localeCompare(b.event_date))[0];
                } else {
                    defaultDist = withDates.sort((a, b) => b.event_date.localeCompare(a.event_date))[0];
                }
            }
        }

        if (defaultDist) {
            if (defaultDist.gpx_file) CONFIG.GPX_FILE = '/' + defaultDist.gpx_file;
            CONFIG.EVENT_ID = defaultDist.db_event_id ?? null;
            CONFIG.CURRENT_DISTANCE = defaultDist.distance || '';
            CONFIG.LAPS = defaultDist.laps ?? 1;
            eventCheckpoints = defaultDist.checkpoints || [];
        } else {
            // Fallback: одиночное событие без массива distances
            if (cfg.gpx_file) CONFIG.GPX_FILE = '/' + cfg.gpx_file;
            CONFIG.EVENT_ID = cfg.db_event_id ?? null;
        }

        console.log('📡 /api/current-event distances:', trackedDistances.length, trackedDistances.map(d => d.distance));

        // Показать switcher если отслеживаемых дистанций > 1
        if (trackedDistances.length > 1) {
            renderDistanceSwitcher(trackedDistances, defaultDist);
        }
    } catch (e) {
        console.error('Ошибка загрузки конфига события:', e);
    }

    loadSelectedFromStorage();
    await initMap();
    initLapLegend();
    await loadAllRunners();

    if (selectedRunnerIds.size > 0) {
        updateSelectedList();
        initializeSelectedRunnersMarkers();
    }

    setupSearch();
    await loadAnalytics();
    startAutoUpdate();
    startAnimationLoop();
    updateEventTitle();
    setInterval(loadAnalytics, 30000);

    updateStatus(`Трекер запущен (${CONFIG.EVENT_DB_NAME} ${CONFIG.EVENT_YEAR})`);
}


function updateEventTitle() {
    const h1 = document.getElementById('eventTitle');
    if (!h1) return;
    const name = CONFIG.EVENT_DB_NAME || CONFIG.EVENT_NAME || '';
    const year = CONFIG.EVENT_YEAR || '';
    const dist = CONFIG.CURRENT_DISTANCE ? `, ${CONFIG.CURRENT_DISTANCE}` : '';
    h1.textContent = `Трекер забега. «${name}» ${year}${dist}.`;
}


// ============================================
// ПЕРЕКЛЮЧЕНИЕ ДИСТАНЦИЙ
// ============================================

function renderDistanceSwitcher(distances, activeDist) {
    const container = document.getElementById('distanceSwitcher');
    if (!container) return;

    container.innerHTML = distances.map(d => `
        <button class="dist-btn${d === activeDist ? ' active' : ''}"
                data-event-id="${d.db_event_id ?? ''}"
                data-gpx="${d.gpx_file ? '/' + d.gpx_file : ''}"
                data-route-type="${d.route_type || 'loop'}"
                data-label="${d.distance}"
                data-laps="${d.laps ?? 1}"
                data-checkpoints="${encodeURIComponent(JSON.stringify(d.checkpoints || []))}">
            ${d.distance}
        </button>
    `).join('');
    container.style.display = 'flex';

    container.querySelectorAll('.dist-btn').forEach(btn => {
        btn.addEventListener('click', () => {
            if (btn.classList.contains('active')) return;
            const eventId = btn.dataset.eventId ? parseInt(btn.dataset.eventId) : null;
            const gpx = btn.dataset.gpx;
            const routeType = btn.dataset.routeType;
            const label = btn.dataset.label || '';
            const laps = parseInt(btn.dataset.laps) || 1;
            const checkpoints = JSON.parse(decodeURIComponent(btn.dataset.checkpoints || '%5B%5D'));
            container.querySelectorAll('.dist-btn').forEach(b => b.classList.remove('active'));
            btn.classList.add('active');
            switchDistance(eventId, gpx, routeType, label, laps, checkpoints);
        });
    });
}

async function switchDistance(eventId, gpxFile, routeType, label, laps = 1, checkpoints = []) {
    CONFIG.EVENT_ID = eventId;
    CONFIG.GPX_FILE = gpxFile;
    CONFIG.LAPS = laps;
    if (label) CONFIG.CURRENT_DISTANCE = label;
    eventCheckpoints = checkpoints;
    updateEventTitle();

    // Сбросить выбранных участников — они принадлежат другой дистанции
    selectedRunnerIds.clear();
    saveSelectedToStorage();
    updateSelectedList();

    // Очистить маркеры текущей дистанции
    Object.values(runnerMarkers).forEach(m => { if (map) map.removeLayer(m); });
    runnerMarkers = {};
    runnerAnimations = {};
    allRunners = [];

    updateStatus('Переключение дистанции...');

    await reloadRoute(gpxFile);
    initLapLegend();
    await loadAllRunners();
    await loadAnalytics();
}


// ============================================
// ЗАГРУЗКА ДАННЫХ ИЗ API
// ============================================

function _applyRunnerData(data) {
    if (data.server_time_unix) serverTimeUnix = data.server_time_unix;
    if (data.race_gun_unix_ms) raceGunUnixMs = data.race_gun_unix_ms;

    if (data.total_distance_km) {
        eventDistance = data.total_distance_km;
    } else if (data.results && data.results.length > 0) {
        eventDistance = parseFloat(data.results[0].distance) || 0;
    }

    allRunners = (data.results || []).map((runner) => {
        const kt1Data = runner.checkpoints?.kt1;
        let kt1Time = kt1Data?.time;

        if (kt1Time === 'undefined' || kt1Time === undefined || kt1Time === null || kt1Time === 'null') {
            kt1Time = null;
        }

        const calculatedGunPace = calculatePaceFromTime(runner.time_gun_finish, eventDistance || runner.event_distance);
        const calculatedCleanPace = calculatePaceFromTime(runner.time_clear_finish, eventDistance || runner.event_distance);

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
            lap:                  runner.lap ?? 1,
            last_kt_unix_ms:      runner.last_kt_unix_ms ?? null,
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

    updateStatus(`Загружено участников: ${allRunners.length}`);
}


async function loadAllRunners() {
    try {
        updateStatus('Загрузка участников...');

        const _t0 = performance.now();
        const _params = new URLSearchParams({ v: Date.now() });
        if (CONFIG.EVENT_ID != null) _params.set('event_id', CONFIG.EVENT_ID);
        else if (CONFIG.EVENT_DB_NAME) _params.set('event_name', CONFIG.EVENT_DB_NAME);
        else if (CONFIG.EVENT_NAME)    _params.set('event_name', CONFIG.EVENT_NAME);
        const response = await fetch(`${CONFIG.API_BASE}/event-results?${_params}`);
        const _fetchMs = performance.now() - _t0;

        if (!response.ok) throw new Error(`Ошибка загрузки: ${response.status}`);

        const data = await response.json();
        const _totalMs = performance.now() - _t0;
        console.debug(`[perf] /api/event-results fetch=${_fetchMs.toFixed(0)}ms parse=${(_totalMs - _fetchMs).toFixed(0)}ms total=${_totalMs.toFixed(0)}ms runners=${data.results?.length ?? 0}`);

        _applyRunnerData(data);

    } catch (error) {
        console.error('Ошибка при загрузке участников:', error);
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
        _analyticsResults = results;

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

        const analyticsH2 = document.querySelector('#analyticsPanel h2');
        if (analyticsH2) {
            const distStr = CONFIG.CURRENT_DISTANCE ? ` | ${CONFIG.CURRENT_DISTANCE}` : '';
            analyticsH2.textContent = `Общая аналитика по забегу${distStr}`;
        }

    } catch (error) {
        console.error('Ошибка загрузки аналитики:', error);
        const analyticsPanel = document.getElementById('analyticsContent');
        if (analyticsPanel) {
            analyticsPanel.innerHTML = `<p style="color: red;">Ошибка загрузки аналитики: ${error.message}</p>`;
        }
    }
}

function refreshAnalyticsFromMemory() {
    if (!allRunners.length) return;
    _analyticsResults = allRunners;
    const stats = {
        total:        allRunners.length,
        finished:     allRunners.filter(r => r.status === 'Finished').length,
        not_started:  allRunners.filter(r => r.status === 'Not started').length,
        running:      allRunners.filter(r => r.status === 'Running').length,
        withdrawn:    allRunners.filter(r => r.status === 'Withdrawn' || r.status === 'Disqualified').length,
        disqualified: 0,
        male:         allRunners.filter(r => r.sex === 'Мужчина').length,
        female:       allRunners.filter(r => r.sex === 'Женщина').length
    };
    const analyticsPanel = document.getElementById('analyticsContent');
    if (analyticsPanel) {
        analyticsPanel.innerHTML = renderAnalyticsHTML(stats, allRunners);
    }
}

window.setTopGender = function(gender) {
    topFinishersGender = gender;
    const el = document.getElementById('topFinishersTable');
    if (el) el.innerHTML = renderTopTableHTML(_analyticsResults, gender);
    document.querySelectorAll('.top-gender-btn').forEach(btn => {
        const labels = { all: 'Все', 'Мужчина': 'Мужчины', 'Женщина': 'Женщины' };
        btn.classList.toggle('active', btn.textContent === labels[gender]);
    });
};

function renderTopTableHTML(results, gender) {
    const statusField = results.length && results[0].race_status !== undefined ? 'race_status' : 'status';
    let filtered = results.filter(r => r[statusField] === 'Finished' && r.rank_absolute);
    if (gender !== 'all') filtered = filtered.filter(r => r.sex === gender);
    const rankField = gender !== 'all' ? 'rank_sex' : 'rank_absolute';
    filtered.sort((a, b) => (a[rankField] || 999) - (b[rankField] || 999));
    const top10 = filtered.slice(0, 10);

    const rows = top10.length
        ? top10.map(runner => {
            const paceStr = parseDuration(runner.finish_pace_avg_gun) || parseDuration(runner.finish_pace_avg);
            const pace = paceStr ? paceStr + ' мин/км' : '-';
            return `<tr style="border-bottom: 1px solid #eee;">
                <td style="padding: 8px; text-align: center;">${runner[rankField] || '—'}</td>
                <td style="padding: 8px; text-align: center;">${runner.start_number || '-'}</td>
                <td style="padding: 8px;"><strong>${runner.surname} ${runner.name}</strong></td>
                <td style="padding: 8px;">${KMUtils.normalizeCategory(runner.category) || '-'}</td>
                <td style="padding: 8px; font-family: monospace;">${parseDuration(runner.time_gun_finish) || '-'}</td>
                <td style="padding: 8px; font-family: monospace;">${pace}</td>
            </tr>`;
        }).join('')
        : '<tr><td colspan="6" style="padding: 10px; text-align: center;">Результатов нет</td></tr>';

    return `<table style="width: 100%; border-collapse: collapse; font-size: 13px;">
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
        <tbody>${rows}</tbody>
    </table>`;
}

function renderAnalyticsHTML(stats, results) {
    const evName = CONFIG.EVENT_DB_NAME || CONFIG.EVENT_NAME || 'Забег';
    const evYear = CONFIG.EVENT_YEAR || new Date().getFullYear();
    const distStr = (results.length > 0 && results[0].distance) ? ` (${results[0].distance})` : '';
    const totalSafe = stats.total || 1;
    const genderBtns = ['all', 'Мужчина', 'Женщина'].map(g => {
        const labels = { all: 'Все', 'Мужчина': 'Мужчины', 'Женщина': 'Женщины' };
        return `<button class="top-gender-btn${topFinishersGender === g ? ' active' : ''}" onclick="setTopGender('${g}')">${labels[g]}</button>`;
    }).join('');

    return `
        <div class="analytics-section">
            <h3>${evName} ${evYear}${distStr} — Общая статистика</h3>
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
            <h3>Распределение по полу</h3>
            <div class="gender-stats">
                <div class="gender-stat">
                    <div class="gender-title">Мужчины</div>
                    <div class="gender-count">${stats.male}</div>
                    <div class="gender-avg-time">${((stats.male / totalSafe) * 100).toFixed(1)}%</div>
                </div>
                <div class="gender-stat">
                    <div class="gender-title">Женщины</div>
                    <div class="gender-count">${stats.female}</div>
                    <div class="gender-avg-time">${((stats.female / totalSafe) * 100).toFixed(1)}%</div>
                </div>
            </div>
        </div>

        <div class="analytics-section">
            <div style="display: flex; align-items: center; gap: 12px; flex-wrap: wrap; margin-bottom: 12px;">
                <h3 style="margin: 0;">Топ-10 финишёров</h3>
                <div class="top-gender-tabs">${genderBtns}</div>
            </div>
            <div style="overflow-x: auto;" id="topFinishersTable">
                ${renderTopTableHTML(results, topFinishersGender)}
            </div>
        </div>
    `;
}


// ============================================
// АВТООБНОВЛЕНИЕ
// ============================================

function startAutoUpdate() {
    if (!CONFIG.EVENT_ID) {
        console.warn('[SSE] EVENT_ID не задан, автообновление отключено');
        return;
    }
    const source = new EventSource(`/api/sse/tracker?event_id=${CONFIG.EVENT_ID}`);
    let isProcessing = false;

    source.onmessage = async (e) => {
        updateSelectedList();
        const distLabel = CONFIG.CURRENT_DISTANCE ? ` | ${CONFIG.CURRENT_DISTANCE}` : '';
        updateStatus(`Обновлено ${new Date().toLocaleTimeString()} | ${CONFIG.EVENT_DB_NAME} ${CONFIG.EVENT_YEAR}${distLabel}`);

        if (isProcessing) return;
        isProcessing = true;
        try {
            const data = JSON.parse(e.data);
            _applyRunnerData(data);
            selectedRunnerIds.forEach(runnerId => {
                const runner = allRunners.find(r => String(r.id) === String(runnerId));
                if (runner) updateRunnerMarkerPosition(runner);
            });
            if (activeRunnerId) {
                const activeRunner = allRunners.find(r => String(r.id) === activeRunnerId);
                if (activeRunner) {
                    const content = document.getElementById('runner-panel-content');
                    if (content) content.innerHTML = buildPopupContent(activeRunner);
                }
            }
            // Обновляем аналитику не чаще раза в 10 сек
            const _now = Date.now();
            if (_now - _lastAnalyticsRefresh > 10000) {
                _lastAnalyticsRefresh = _now;
                refreshAnalyticsFromMemory();
            }
        } catch (err) {
            console.error('Ошибка SSE данных:', err);
        } finally {
            isProcessing = false;
        }
    };

    source.onerror = () => {
        updateStatus('SSE: переподключение...');
    };

    console.log(`[SSE] Трекер подключён: event_id=${CONFIG.EVENT_ID}`);
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
