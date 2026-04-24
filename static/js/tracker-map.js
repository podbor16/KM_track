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

            map.fitBounds(routeLayer.getBounds(), { padding: [50, 50] });
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
    const color = getStatusColor(runner.status);
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
                ${runner.category ? `<div><strong>Категория:</strong> ${runner.category}</div>` : ''}
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
        const lastCPTime = lastCP ? parseDuration(lastCP.time) : '-';
        const lastCPPace = lastCP ? parseDuration(lastCP.pace) : '-';

        let predictedFinish = '-';
        if (lastCP && lastCP.pace) {
            const paceSeconds = durationToSeconds(lastCP.pace);
            if (paceSeconds > 0 && eventDistance > 0) {
                const predictedSeconds = (eventDistance * 1000) / (1000 / paceSeconds);
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

    marker.bindPopup(buildPopupContent(runner), { minWidth: 200 });
    marker.on('click', e => e.target.openPopup());
    marker.on('popupopen',  () => activePopups.set(runnerId, true));
    marker.on('popupclose', () => activePopups.delete(runnerId));

    runnerMarkers[runnerId] = marker;
}

function calculateCurrentDistanceKm(runner) {
    const rId = String(runner.id);
    const elapsedSinceApiH = (Date.now() - serverTimeUnix) / 3_600_000;
    const speed = (runner.speed > 0) ? runner.speed : 10.0;

    const apiExtrapolated = Math.max(0, (runner.current_distance || 0) + speed * elapsedSinceApiH);

    let storedMax = _loadMaxDist(rId);
    const serverDist = runner.current_distance || 0;
    if (storedMax > 0 && serverDist > 0 && storedMax > serverDist * 1.1) {
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
        const distKm = calculateCurrentDistanceKm(runner);
        targetProgressPercent = Math.min(100, distKm / totalDistKm * 100);
    }

    const maxIndex = Math.max(0, routeCoordinates.length - 1);
    const targetIndex = Math.min(maxIndex, Math.round(maxIndex * targetProgressPercent / 100));

    if (!runnerAnimations[runnerId]) {
        runnerAnimations[runnerId] = {
            currentIndex: targetIndex,
            targetIndex: targetIndex,
            startTime: Date.now(),
            animationDuration: shouldTeleport ? 0 : CONFIG.UPDATE_INTERVAL
        };
    } else {
        const now = Date.now();
        const anim = runnerAnimations[runnerId];

        if (shouldTeleport) {
            anim.currentIndex = targetIndex;
            anim.targetIndex = targetIndex;
        } else {
            const elapsed = Math.max(0, now - anim.startTime);
            const progress = anim.animationDuration > 0 ? Math.min(1, elapsed / anim.animationDuration) : 1;
            const currentIndex = anim.currentIndex + (anim.targetIndex - anim.currentIndex) * progress;
            anim.currentIndex = currentIndex;
            anim.targetIndex = targetIndex;
        }

        anim.startTime = now;
        anim.animationDuration = shouldTeleport ? 0 : CONFIG.UPDATE_INTERVAL;
    }

    marker.setIcon(buildMarkerIcon(runner));

    if (marker.getPopup()) {
        marker.getPopup().setContent(buildPopupContent(runner));
    }
}

function animateRunnerFrame() {
    const now = Date.now();

    Object.entries(runnerAnimations).forEach(([runnerId, anim]) => {
        const marker = runnerMarkers[runnerId];
        if (!marker || !routeCoordinates.length) return;

        const elapsed = now - anim.startTime;
        const progress = Math.min(1, elapsed / anim.animationDuration);

        const currentIndex = anim.currentIndex + (anim.targetIndex - anim.currentIndex) * progress;

        const floorIndex = Math.floor(currentIndex);
        const ceilIndex = Math.ceil(currentIndex);
        const fracIndex = currentIndex - floorIndex;

        let position;
        if (floorIndex === ceilIndex) {
            position = routeCoordinates[floorIndex];
        } else {
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

        if (progress >= 1) {
            anim.currentIndex = anim.targetIndex;
            anim.startTime = now;
        }
    });

    animationFrameId = requestAnimationFrame(animateRunnerFrame);
}

function startAnimationLoop() {
    if (!animationFrameId) {
        animateRunnerFrame();
    }
}
