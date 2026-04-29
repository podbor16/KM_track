// tracker-map.js — карта, маршрут, маркеры, анимация

async function initMap() {
    map = L.map('map').setView([CONFIG.START_LAT, CONFIG.START_LON], 15);
    map.attributionControl.setPrefix('');

    L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', {
        attribution: '© OpenStreetMap contributors'
    }).addTo(map);

    await loadRouteFromAPI();
}

async function loadRouteFromAPI() {
    try {
        updateStatus('Загрузка GPX маршрута...');

        const gpxPath = CONFIG.GPX_FILE;
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

            if (startMarker && map) map.removeLayer(startMarker);
            startMarker = L.marker(routeCoordinates[0], {
                icon: L.divIcon({
                    className: 'start-marker',
                    html: '<div style="background: #EE2D62; color: white; padding: 8px 12px; border-radius: 5px; font-weight: bold; text-align: center;">🏁 СТАРТ</div>',
                    iconSize: [100, 35],
                    iconAnchor: [50, 35]
                })
            }).addTo(map);

            const routeBounds = routeLayer.getBounds();
            map.fitBounds(routeBounds, { padding: [10, 10] });

            const maxBounds = routeBounds.pad(0.5);
            map.setMaxBounds(maxBounds);
            map.setMinZoom(map.getBoundsZoom(maxBounds));
        }

        updateStatus('✅ Маршрут загружен');

    } catch (error) {
        console.error('❌ Ошибка загрузки GPX:', error);
        updateStatus('❌ Ошибка: не удалось загрузить GPX маршрут');
        alert(`Ошибка загрузки маршрута: ${error.message}`);
    }
}


async function reloadRoute(gpxPath) {
    if (routeLayer && map) {
        map.removeLayer(routeLayer);
        routeLayer = null;
        routeCoordinates = [];
    }
    if (gpxPath) {
        CONFIG.GPX_FILE = gpxPath;
        await loadRouteFromAPI();
    }
}


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
    const color = getStatusColor(runner.status, runner.lap ?? 0);
    const runnerId = String(runner.id);
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

    let startClockHTML = '';
    if (raceGunUnixMs != null && runner.time_clear_start_s != null) {
        const startUnix = raceGunUnixMs + runner.time_clear_start_s * 1000;
        const startTime = new Date(startUnix).toLocaleTimeString('ru-RU', { hour: '2-digit', minute: '2-digit', second: '2-digit' });
        startClockHTML = `<div><strong>Время старта:</strong> ${startTime}</div>`;
    }

    const baseHTML = `
        <div style="font-size: 12px; min-width: 220px; text-align: left;">
            <div style="text-align: center; margin-bottom: 8px;">
                <div><strong>№${runner.start_number}</strong></div>
                <div><strong>${runner.full_name}</strong></div>
            </div>
            <div style="border-top: 1px solid #ddd; padding-top: 8px; margin-bottom: 8px;">
                ${runner.category ? `<div><strong>Категория:</strong> ${KMUtils.normalizeCategory(runner.category)}</div>` : ''}
                ${startClockHTML}
            </div>
    `;

    let contentHTML = '';

    if (status.includes('finish')) {
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
        const lastCP = getLastCheckpoint(runner);
        const ktLabel  = lastCP?.name ?? '-';
        const segLabel = lastCP ? `${lastCP.prevName} → ${lastCP.name}` : '-';
        const lastCPTime = lastCP ? parseDuration(lastCP.time) : '-';

        // Интервальный темп последнего участка (не кумулятивный)
        const lastSegPace = lastCP?.interval_pace || lastCP?.pace || '-';

        // Прогноз финиша: оставшаяся дистанция / текущая скорость → время прихода
        let finishEta = '-';
        if (runner.speed > 0 && eventDistance > 0) {
            const remaining_km = eventDistance - (runner.current_distance || 0);
            if (remaining_km > 0) {
                const remaining_secs = remaining_km / runner.speed * 3600;
                const finish_unix_ms = serverTimeUnix + remaining_secs * 1000;
                finishEta = new Date(finish_unix_ms).toLocaleTimeString('ru-RU', {
                    hour: '2-digit', minute: '2-digit', second: '2-digit'
                });
            } else {
                finishEta = 'Финишировал';
            }
        }

        // Прогноз из категории/личного рекорда — только когда нет КТ-данных
        let forecastRow = '';
        if (runner.pace_source && lastCP === null) {
            const paceLabel = runner.pace_source === 'personal' && runner.prev_year
                ? `Прогноз (личный ${runner.prev_year})`
                : runner.pace_source === 'category' && runner.prev_year
                    ? `Прогноз (ср. кат. ${runner.prev_year})`
                    : 'Текущий темп';
            forecastRow = runner.current_pace
                ? `<div><strong>${paceLabel}:</strong> ${runner.current_pace} мин/км</div>`
                : '';
        }

        contentHTML = `
            <div style="border-top: 1px solid #ddd; padding-top: 8px;">
                <div><strong>Статус:</strong> ${getStatusText(runner.status)}</div>
                <div><strong>Последняя КТ:</strong> ${ktLabel}</div>
                <div><strong>Время на ${ktLabel}:</strong> ${lastCPTime}</div>
                <div><strong>Темп участка ${segLabel}:</strong> ${lastSegPace} мин/км</div>
                ${forecastRow}
                <div><strong>Место:</strong> ${runner.rank_absolute || '-'}</div>
                <div style="border-top: 1px solid #eee; margin-top: 6px; padding-top: 6px;">
                    <div><strong>Прогноз финиша:</strong> ${finishEta}</div>
                </div>
            </div>
        `;
    } else {
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

    const initialPosition = routeCoordinates[0] || [CONFIG.START_LAT, CONFIG.START_LON];
    const marker = L.marker(initialPosition, { icon: buildMarkerIcon(runner) }).addTo(map);

    marker.bindPopup(buildPopupContent(runner), { minWidth: 200, autopan: false });
    marker.on('click', e => e.target.openPopup());
    marker.on('popupopen',  () => activePopups.set(runnerId, true));
    marker.on('popupclose', () => activePopups.delete(runnerId));

    runnerMarkers[runnerId] = marker;
    updateRunnerMarkerPosition(runner);  // инициализировать anim сразу
}

function updateRunnerMarkerPosition(runner) {
    const runnerId = String(runner.id);
    const marker = runnerMarkers[runnerId];
    if (!marker || !routeCoordinates.length) return;

    const s = (runner.status || '').toLowerCase();

    if (!runnerAnimations[runnerId]) runnerAnimations[runnerId] = {};
    const anim = runnerAnimations[runnerId];

    if (s.includes('notstart') || s === 'not started') {
        anim.status = 'notstarted';
    } else if (s.includes('finish')) {
        anim.status = 'finished';
    } else {
        anim.status = 'running';
        anim.baseDist   = runner.current_distance || 0;
        anim.speed      = runner.speed > 0 ? runner.speed : 10.0;
        // Если есть время последней КТ — анимируем от неё; иначе от выстрела или serverTime
        anim.baseTimeMs = runner.last_kt_unix_ms ?? raceGunUnixMs ?? serverTimeUnix;
    }

    marker.setIcon(buildMarkerIcon(runner));
    const popup = marker.getPopup();
    if (popup) popup.setContent(buildPopupContent(runner));
}

function animateRunnerFrame() {
    const now = Date.now();
    const totalDistKm = eventDistance || 5.0;
    const maxIdx = Math.max(0, routeCoordinates.length - 1);
    // Если время выстрела ещё не наступило — все маркеры стоят на старте
    const raceStarted = !raceGunUnixMs || now >= raceGunUnixMs;

    Object.entries(runnerAnimations).forEach(([runnerId, anim]) => {
        const marker = runnerMarkers[runnerId];
        if (!marker || !routeCoordinates.length) return;

        let distKm = 0;
        if (raceStarted && anim.status === 'finished') {
            distKm = totalDistKm;
        } else if (raceStarted && anim.status === 'running') {
            const elapsedH = (now - (anim.baseTimeMs || now)) / 3_600_000;
            // Math.max: если КТ ещё в будущем (elapsedH < 0) — маркер стоит на baseDist
            distKm = Math.min(totalDistKm, Math.max(anim.baseDist || 0, (anim.baseDist || 0) + (anim.speed || 10) * elapsedH));
        }
        // notstarted или race not started: distKm = 0

        const coord = getCoordForDist(distKm, totalDistKm, maxIdx);
        if (coord) marker.setLatLng(coord);
    });

    animationFrameId = requestAnimationFrame(animateRunnerFrame);
}

function getCoordForDist(distKm, totalDistKm, maxIdx) {
    // Снапп к точным координатам КТ если маркер близко к ней (≤50м)
    for (const cp of eventCheckpoints) {
        if (Math.abs(distKm - cp.distance_km) <= 0.05) {
            return [cp.lat, cp.lon];
        }
    }
    const idx = Math.min(maxIdx, Math.round(maxIdx * distKm / totalDistKm));
    return routeCoordinates[idx];
}

function startAnimationLoop() {
    if (!animationFrameId) {
        animateRunnerFrame();
    }
}

function centerMap() {
    if (routeLayer && map) {
        map.fitBounds(routeLayer.getBounds(), { padding: [10, 10] });
    }
}

let _lapLegendControl = null;

function initLapLegend() {
    if (CONFIG.LAPS <= 1 || !map) return;

    if (_lapLegendControl) {
        map.removeControl(_lapLegendControl);
        _lapLegendControl = null;
    }

    _lapLegendControl = L.control({ position: 'bottomleft' });
    _lapLegendControl.onAdd = () => {
        const div = L.DomUtil.create('div', 'lap-legend');
        div.innerHTML = LAP_COLORS.slice(0, CONFIG.LAPS).map((color, i) =>
            `<span><span class="lap-dot" style="background:${color}"></span>Круг ${i + 1}</span>`
        ).join('');
        return div;
    };
    _lapLegendControl.addTo(map);
}
