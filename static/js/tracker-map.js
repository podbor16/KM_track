// tracker-map.js — карта, маршрут, маркеры, анимация

let checkpointMarkers = [];
const runnerTrailHistory = {};
let trailLastUpdateMs = 0;
let startMarkerIsFinish = false;

async function initMap() {
    map = L.map('map').setView([CONFIG.START_LAT, CONFIG.START_LON], 15);
    map.attributionControl.setPrefix('');

    L.tileLayer('https://{s}.basemaps.cartocdn.com/light_all/{z}/{x}/{y}{r}.png', {
        attribution: '© <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors © <a href="https://carto.com/attributions">CARTO</a>',
        subdomains: 'abcd',
        maxZoom: 19
    }).addTo(map);

    map.on('click', hideRunnerPanel);

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
                weight: 7,
                opacity: 0.95,
                smoothFactor: 1
            }).addTo(map);

            if (startMarker && map) map.removeLayer(startMarker);
            startMarkerIsFinish = false;
            startMarker = L.marker(routeCoordinates[0], {
                icon: L.divIcon({
                    className: 'start-marker',
                    html: makeStartFlagHtml('СТАРТ'),
                    iconSize: [60, 48],
                    iconAnchor: [30, 48]
                })
            }).addTo(map);
            drawCheckpointMarkers();

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
    Object.keys(runnerMarkers).forEach(runnerId => {
        if (map.hasLayer(runnerMarkers[runnerId])) map.removeLayer(runnerMarkers[runnerId]);
        clearRunnerTrail(runnerId);
    });
    runnerMarkers = {};
    runnerPositions = {};
    runnerAnimations = {};

    selectedRunnerIds.forEach(runnerId => {
        const runner = allRunners.find(r => String(r.id) === String(runnerId));
        if (runner) createRunnerMarker(runner);
    });
}

function makeStartFlagHtml(label) {
    return `<div style="display:flex;flex-direction:column;align-items:center;">
        <div style="background:#EE2D62;color:white;padding:4px 10px;border-radius:4px;font-weight:bold;font-size:11px;white-space:nowrap;box-shadow:0 2px 4px rgba(0,0,0,0.2);">${label}</div>
        <div style="width:2px;height:22px;background:#EE2D62;"></div>
    </div>`;
}

function buildMarkerIcon(runner) {
    const runnerId = String(runner.id);
    const color = getStatusColor(runner.status, runner.lap ?? 0);
    const fontSize = String(runner.start_number).length >= 3 ? '11px' : '13px';

    const anim = runnerAnimations[runnerId];
    const isActive = runnerId === activeRunnerId;
    const statusClass = anim?.status === 'running' ? 'running'
                      : anim?.status === 'finished' ? 'finished' : '';
    const activeClass = isActive ? 'runner-marker--active' : '';

    // Phase-sync: negative delay places animation at the correct point in the
    // global clock so icon rebuilds (every 1500 ms) don't reset the rhythm.
    const BREATHE_MS = 2200;
    const SEL_MS     = 2000;
    const now        = Date.now();
    const breatheDelay = -(now % BREATHE_MS);
    const trail1Delay  = breatheDelay + 150;  // trail follows circle by 150 ms
    const trail2Delay  = breatheDelay + 300;
    const selDelay     = -(now % SEL_MS);
    const circleDelay  = isActive ? selDelay : breatheDelay;

    let trailHtml = '';
    if (anim && anim.status === 'running' && anim.bearing != null) {
        const rad = anim.bearing * Math.PI / 180;
        const dx1 = -Math.sin(rad) * 26, dy1 = Math.cos(rad) * 26;
        const dx2 = -Math.sin(rad) * 44, dy2 = Math.cos(rad) * 44;
        trailHtml = `
            <div class="runner-trail-1" style="position:absolute;top:${26+dy1}px;left:${26+dx1}px;width:20px;height:20px;border-radius:50%;background:${color};opacity:0.55;border:2px solid white;box-shadow:0 1px 4px rgba(0,0,0,0.25);transform:translate(-50%,-50%);pointer-events:none;animation-delay:${trail1Delay}ms;"></div>
            <div class="runner-trail-2" style="position:absolute;top:${26+dy2}px;left:${26+dx2}px;width:13px;height:13px;border-radius:50%;background:${color};opacity:0.35;border:2px solid white;box-shadow:0 1px 3px rgba(0,0,0,0.2);transform:translate(-50%,-50%);pointer-events:none;animation-delay:${trail2Delay}ms;"></div>`;
    }

    return L.divIcon({
        className: ['runner-marker', `runner-${runnerId}`, statusClass, activeClass].filter(Boolean).join(' '),
        html: `<div style="position:relative;width:52px;height:52px;overflow:visible;">
            ${trailHtml}
            <div class="runner-circle" style="
                position:absolute;top:0;left:0;
                background:${color};color:white;
                width:52px;height:52px;border-radius:50%;
                display:flex;align-items:center;justify-content:center;
                font-weight:bold;font-size:${fontSize};
                border:2px solid white;box-shadow:0 2px 8px rgba(0,0,0,0.3);
                box-sizing:border-box;text-align:center;line-height:1;overflow:hidden;
                animation-delay:${circleDelay}ms;
            ">${runner.start_number}</div>
        </div>`,
        iconSize: [52, 52],
        iconAnchor: [26, 26],
        popupAnchor: [0, -28]
    });
}

function getKtRanks(runner, ktCode) {
    const passed = allRunners.filter(r => {
        const cp = r.checkpoints?.[ktCode];
        return cp && cp.time;
    });
    if (passed.length === 0) return null;

    const toSec = r => durationToSeconds(r.checkpoints[ktCode].time);
    const sorted = [...passed].sort((a, b) => toSec(a) - toSec(b));
    const myId = String(runner.id);

    const absPos  = sorted.findIndex(r => String(r.id) === myId) + 1;
    const sexList = sorted.filter(r => r.sex === runner.sex);
    const sexPos  = sexList.findIndex(r => String(r.id) === myId) + 1;
    const catList = sorted.filter(r => r.category === runner.category);
    const catPos  = catList.findIndex(r => String(r.id) === myId) + 1;

    return {
        absolute: absPos  > 0 ? `${absPos} / ${sorted.length}`  : null,
        sex:      sexPos  > 0 ? `${sexPos} / ${sexList.length}`  : null,
        category: catPos  > 0 ? `${catPos} / ${catList.length}`  : null,
    };
}

function escHtml(s) {
    return String(s ?? '').replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;');
}

function buildPopupContent(runner) {
    const status = (runner.status || '').toLowerCase();
    const isRunning = status === 'running' || status === 'started' || status === 'на трассе';
    const isFinished = status === 'finished' || status === 'финишировал' || status.startsWith('finish');

    // Circle badge — same color as map marker
    const circleColor = getStatusColor(runner.status, runner.lap ?? 0);
    const numLen = String(runner.start_number).length;
    const numFontSize = numLen >= 4 ? '10px' : numLen >= 3 ? '11px' : '13px';

    // Start time string
    let startTimeStr = '';
    if (raceGunUnixMs != null) {
        const offset = runner.time_clear_start_s ?? 0;
        const startUnix = raceGunUnixMs + offset * 1000;
        startTimeStr = new Date(startUnix).toLocaleTimeString('ru-RU', {
            hour: '2-digit', minute: '2-digit', second: '2-digit'
        });
    }

    const pillLabel = isFinished ? 'Финишировал' : isRunning ? 'Бежит' : 'Не стартовал';
    const pillClass = isFinished ? 'card-c__pill card-c__pill--finished' : 'card-c__pill';
    const subParts = [
        runner.category ? KMUtils.normalizeCategory(runner.category) : null,
        startTimeStr ? `Старт ${startTimeStr}` : null
    ].filter(Boolean);

    const topHTML = `
        <div class="card-c__top">
            <div class="card-c__circle" style="background:${circleColor};font-size:${numFontSize}">
                ${escHtml(runner.start_number)}
            </div>
            <div class="card-c__title">
                <div class="card-c__name">${escHtml(runner.full_name)}</div>
                ${subParts.length ? `<div class="card-c__sub">${escHtml(subParts.join(' · '))}</div>` : ''}
            </div>
            <div class="${pillClass}">${pillLabel}</div>
        </div>`;

    // ── Not started ──────────────────────────────────
    if (!isRunning && !isFinished) {
        return `<div class="card-c">${topHTML}</div>`;
    }

    // ── Finished ─────────────────────────────────────
    if (isFinished) {
        const finishPaceGun   = runner.finish_pace_avg_gun   || '-';
        const finishPaceClean = runner.finish_pace_avg_clean || runner.finish_pace_avg_gun || '-';
        const clearTime = runner.time_clear_finish || '';
        const gunTime   = runner.time_gun_finish   || '';
        const timesEqual = gunTime && clearTime && gunTime === clearTime;

        // Строка: Офиц. время | Дист. | Темп (gun) | Чист. время
        const statsHTML = `
            <div class="card-c__stats-grid card-c__stats-grid--4">
                <div class="card-c__stat">
                    <div class="card-c__stat-val card-c__stat-val--primary">${escHtml(gunTime || '-')}</div>
                    <div class="card-c__stat-lbl">Офиц. время</div>
                </div>
                <div class="card-c__stat">
                    <div class="card-c__stat-val card-c__stat-val--blue">${escHtml(timesEqual ? clearTime : (clearTime || gunTime || '-'))}</div>
                    <div class="card-c__stat-lbl">Чист. время</div>
                </div>
                <div class="card-c__stat">
                    <div class="card-c__stat-val">${escHtml(finishPaceGun)}</div>
                    <div class="card-c__stat-lbl">Темп</div>
                </div>
                <div class="card-c__stat">
                    <div class="card-c__stat-val">${eventDistance > 0 ? eventDistance : '-'}<span class="unit"> км</span></div>
                    <div class="card-c__stat-lbl">Дистанция</div>
                </div>
            </div>`;

        // Ранги — всегда показываем для финишировавших
        const fmtR = v => v ? `#${v}` : '—';
        const sexPrefix = runner.sex === 'Мужчина' ? 'М' : runner.sex === 'Женщина' ? 'Ж' : '';
        const rankSexStr = runner.rank_sex ? `${sexPrefix} #${runner.rank_sex}` : '—';

        const ranksHTML = `
            <div class="card-c__ranks-col">
                <div class="card-c__ranks-row">
                    <div class="card-c__rank">
                        <div class="card-c__rank-val">${fmtR(runner.rank_absolute)}</div>
                        <div class="card-c__rank-lbl">Место абс.</div>
                    </div>
                    <div class="card-c__rank">
                        <div class="card-c__rank-val">${rankSexStr}</div>
                        <div class="card-c__rank-lbl">По полу</div>
                    </div>
                    <div class="card-c__rank">
                        <div class="card-c__rank-val">${fmtR(runner.rank_category)}</div>
                        <div class="card-c__rank-lbl">По кат.</div>
                    </div>
                </div>
            </div>`;

        // КТ-время если есть
        const kt1 = runner.checkpoints?.kt1;
        const kt1Time = kt1?.time ? parseDuration(kt1.time) : null;
        const kt1Pace = kt1?.pace ? parseDuration(kt1.pace) : null;
        const ktHTML = kt1Time ? `
            <div class="card-c__kt-row">
                <span class="card-c__kt-label">КТ 1</span>
                <span class="card-c__kt-val">${escHtml(kt1Time)}</span>
                ${kt1Pace ? `<span class="card-c__kt-pace">${escHtml(kt1Pace)} мин/км</span>` : ''}
            </div>` : '';

        return `<div class="card-c">${topHTML}${statsHTML}${ranksHTML}${ktHTML}</div>`;
    }

    // ── Running ──────────────────────────────────────
    const lastCP = getLastCheckpoint(runner);
    const pace = runner.current_pace || '-';
    const distCurrent = runner.current_distance != null ? Number(runner.current_distance).toFixed(1) : '?';
    const distTotal = eventDistance > 0 ? Number(eventDistance).toFixed(1) : '?';
    const rankAbs = runner.rank_absolute || '-';

    // 4th desktop stat: KT time
    let ktTimeShort = '-';
    let ktDesktopLbl = 'Время КТ';
    if (lastCP) {
        ktTimeShort = parseDuration(lastCP.time);
        ktDesktopLbl = `Время ${lastCP.name}`;
    }

    const statsHTML = `
        <div class="card-c__stats-grid">
            <div class="card-c__stat">
                <div class="card-c__stat-val">${pace}</div>
                <div class="card-c__stat-lbl">Темп</div>
            </div>
            <div class="card-c__stat">
                <div class="card-c__stat-val" id="panel-stat-dist">${distCurrent}<span class="unit">/${distTotal}</span></div>
                <div class="card-c__stat-lbl">км</div>
            </div>
            <div class="card-c__stat">
                <div class="card-c__stat-val">${rankAbs}</div>
                <div class="card-c__stat-lbl">Место</div>
            </div>
            <div class="card-c__stat card-c__stat--desktop-only">
                <div class="card-c__stat-val">${ktTimeShort}</div>
                <div class="card-c__stat-lbl">${escHtml(ktDesktopLbl)}</div>
            </div>
        </div>`;

    // KT block
    let ktBlockHTML = '';
    if (lastCP) {
        const ktDist = eventCheckpoints[lastCP.cpIdx]?.distance_km ?? 0;
        const ktSecs = durationToSeconds(lastCP.time);
        let ktPaceStr = '';
        if (ktSecs > 0 && ktDist > 0) {
            const spk = ktSecs / ktDist;
            ktPaceStr = `${Math.floor(spk / 60)}:${String(Math.round(spk % 60)).padStart(2, '0')} мин/км`;
        }
        ktBlockHTML = `
            <div class="card-c__kt-block">
                <div class="card-c__kt-left">
                    <div class="card-c__kt-label">Последняя КТ</div>
                    <div class="card-c__kt-name">${escHtml(lastCP.name)}${ktDist > 0 ? ` · ${ktDist} км` : ''}</div>
                </div>
                <div class="card-c__kt-right">
                    <div class="card-c__kt-time">${parseDuration(lastCP.time)}</div>
                    ${ktPaceStr ? `<div class="card-c__kt-pace">${ktPaceStr}</div>` : ''}
                </div>
            </div>`;
    }

    // Ranks on last KT
    let ranksHTML = '';
    if (lastCP) {
        const ranks = getKtRanks(runner, lastCP.code);
        if (ranks) {
            ranksHTML = `
                <div class="card-c__ranks-col">
                    <div class="card-c__ranks-row">
                        <div class="card-c__rank">
                            <div class="card-c__rank-val">${ranks.absolute ?? '-'}</div>
                            <div class="card-c__rank-lbl">Абсолют</div>
                        </div>
                        <div class="card-c__rank">
                            <div class="card-c__rank-val">${ranks.sex ?? '-'}</div>
                            <div class="card-c__rank-lbl">Пол</div>
                        </div>
                        <div class="card-c__rank">
                            <div class="card-c__rank-val">${ranks.category ?? '-'}</div>
                            <div class="card-c__rank-lbl">Катег.</div>
                        </div>
                    </div>
                </div>`;
        }
    }

    // ETA
    let etaHTML = '';
    const hasStarted = isRunning;
    let finishEtaMs = null;
    if (hasStarted && lastCP && eventDistance > 0) {
        const ktSecs = durationToSeconds(lastCP.time);
        const ktDist = eventCheckpoints[lastCP.cpIdx]?.distance_km ?? 0;
        if (ktDist > 0 && ktSecs > 0) {
            const remaining_km = eventDistance - ktDist;
            if (remaining_km > 0) {
                const secsPerKm = ktSecs / ktDist;
                const baseMs = runner.last_kt_unix_ms || serverTimeUnix;
                finishEtaMs = baseMs + remaining_km * secsPerKm * 1000;
            }
        }
    } else if (hasStarted && runner.speed > 0 && eventDistance > 0 && raceGunUnixMs) {
        const startUnixMs = raceGunUnixMs + (runner.time_clear_start_s ?? 0) * 1000;
        finishEtaMs = startUnixMs + (eventDistance / runner.speed) * 3_600_000;
    }

    if (finishEtaMs) {
        const astroStr = new Date(finishEtaMs).toLocaleTimeString('ru-RU', {
            hour: '2-digit', minute: '2-digit', second: '2-digit'
        });
        let resultStr = '';
        if (raceGunUnixMs) {
            const res_s = Math.round((finishEtaMs - raceGunUnixMs) / 1000);
            if (res_s > 0) {
                const rh = Math.floor(res_s / 3600);
                const rm = Math.floor((res_s % 3600) / 60);
                const rs = res_s % 60;
                resultStr = rh > 0
                    ? `${rh}:${String(rm).padStart(2,'0')}:${String(rs).padStart(2,'0')}`
                    : `${rm}:${String(rs).padStart(2,'0')}`;
            }
        }
        etaHTML = `
            <div class="card-c__eta" style="grid-column:1/-1">
                <div class="card-c__eta-lbl">Прогноз финиша</div>
                <div class="card-c__eta-vals">
                    <div class="card-c__eta-val">${resultStr || astroStr}</div>
                    ${resultStr ? `<div class="card-c__eta-time">финиш в ${astroStr}</div>` : ''}
                </div>
            </div>`;
    }

    return `<div class="card-c">${topHTML}${statsHTML}<div class="card-c__body">${ktBlockHTML}${ranksHTML}${etaHTML}</div></div>`;
}

function showRunnerPanel(runner) {
    // Reset z-index of previous active marker
    if (activeRunnerId && runnerMarkers[activeRunnerId]) {
        runnerMarkers[activeRunnerId].setZIndexOffset(0);
    }

    const panel = document.getElementById('runner-panel');
    const content = document.getElementById('runner-panel-content');
    content.innerHTML = buildPopupContent(runner);

    // Apply desktop layout modifier
    const card = content.querySelector('.card-c');
    if (card) {
        card.classList.toggle('card-c--desktop', window.innerWidth >= 640);
    }

    panel.classList.remove('runner-panel--hidden');
    activeRunnerId = String(runner.id);
    updateSelectedList();

    // Elevate selected marker
    const marker = runnerMarkers[activeRunnerId];
    if (marker) marker.setZIndexOffset(1000);
}

function showRunnerPanelById(runnerId) {
    const runner = allRunners.find(r => String(r.id) === String(runnerId));
    if (runner) showRunnerPanel(runner);
}

function hideRunnerPanel() {
    if (activeRunnerId && runnerMarkers[activeRunnerId]) {
        runnerMarkers[activeRunnerId].setZIndexOffset(0);
    }
    document.getElementById('runner-panel').classList.add('runner-panel--hidden');
    activeRunnerId = null;
    updateSelectedList();
}

function createRunnerMarker(runner) {
    const runnerId = String(runner.id);

    if (runnerMarkers[runnerId]) {
        updateRunnerMarkerPosition(runner);
        return;
    }

    const initialPosition = routeCoordinates[0] || [CONFIG.START_LAT, CONFIG.START_LON];
    const marker = L.marker(initialPosition, { icon: buildMarkerIcon(runner) }).addTo(map);

    marker.on('click', () => showRunnerPanel(runner));

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
        const newSpeed = runner.speed > 0 ? runner.speed : 10.0;
        anim.color  = getStatusColor(runner.status, runner.lap ?? 0);

        // --- плавная коррекция позиции (lerp) при изменении данных ---
        const nowMs = Date.now();
        const isNewKt = runner.last_kt_unix_ms && (runner.last_kt_unix_ms !== anim.lastKtUnixMs);

        if (runner.last_kt_unix_ms && !isNewKt && anim.baseDist != null) {
            // Та же КТ, изменились speed или данные — рассчитываем отклонение
            const elH = (nowMs - (anim.baseTimeMs || nowMs)) / 3_600_000;
            const phys = Math.min(eventDistance || 5, Math.max(
                anim.baseDist || 0, (anim.baseDist || 0) + (anim.speed || 10) * elH
            ));
            let currentRender = phys;
            if (anim.correctionStartMs && (nowMs - anim.correctionStartMs) < (anim.correctionDurationMs || 1500)) {
                const ct = Math.min(1, (nowMs - anim.correctionStartMs) / (anim.correctionDurationMs || 1500));
                const ce = ct < 0.5 ? 2*ct*ct : -1+(4-2*ct)*ct;
                currentRender = phys + (anim.renderCorrection || 0) * (1 - ce);
            }
            const newPhysDist = (runner.current_distance || 0)
                + newSpeed * (nowMs - runner.last_kt_unix_ms) / 3_600_000;
            const delta = currentRender - newPhysDist;
            if (delta > 0.03) {
                // Рендер впереди истины — мгновенный snap (не рисуем движение назад)
                anim.renderCorrection = 0;
                anim.correctionStartMs = null;
            } else if (delta < -0.03) {
                // Рендер позади истины — плавный catch-up за 1.5 сек
                anim.renderCorrection = delta;
                anim.correctionStartMs = nowMs;
                anim.correctionDurationMs = 1500;
            }
        } else {
            // Новая КТ или первое обновление — мгновенный snap
            anim.renderCorrection = 0;
            anim.correctionStartMs = null;
        }
        anim.lastKtUnixMs = runner.last_kt_unix_ms;
        anim.speed = newSpeed;

        if (runner.last_kt_unix_ms) {
            anim.baseDist   = runner.current_distance || 0;
            anim.baseTimeMs = runner.last_kt_unix_ms;
        } else {
            const startOffsetMs = (runner.time_clear_start_s ?? 0) * 1000;
            anim.baseDist   = 0;
            anim.baseTimeMs = raceGunUnixMs ? raceGunUnixMs + startOffsetMs : serverTimeUnix;
        }
    }

    marker.setIcon(buildMarkerIcon(runner));
    const popup = marker.getPopup();
    if (popup) popup.setContent(buildPopupContent(runner));
}

function animateRunnerFrame() {
    const now = Date.now();
    if (now - trailLastUpdateMs > 1500) {
        trailLastUpdateMs = now;
        updateTrails();
    }

    // Переключаем СТАРТ → ФИНИШ после выстрела
    const raceNowStarted = !!(raceGunUnixMs && now >= raceGunUnixMs);
    if (raceNowStarted !== startMarkerIsFinish && startMarker && routeCoordinates.length) {
        startMarkerIsFinish = raceNowStarted;
        const label = raceNowStarted ? 'ФИНИШ' : 'СТАРТ';
        const coord = raceNowStarted
            ? routeCoordinates[routeCoordinates.length - 1]
            : routeCoordinates[0];
        startMarker.setLatLng(coord);
        startMarker.setIcon(L.divIcon({
            className: 'start-marker',
            html: makeStartFlagHtml(label),
            iconSize: [60, 48],
            iconAnchor: [30, 48]
        }));
    }

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
            const physDist = Math.min(totalDistKm, Math.max(anim.baseDist || 0, (anim.baseDist || 0) + (anim.speed || 10) * elapsedH));
            if (anim.correctionStartMs && (now - anim.correctionStartMs) < (anim.correctionDurationMs || 1500)) {
                const t = (now - anim.correctionStartMs) / (anim.correctionDurationMs || 1500);
                const eased = t < 0.5 ? 2*t*t : -1+(4-2*t)*t;
                distKm = physDist + (anim.renderCorrection || 0) * (1 - eased);
            } else {
                anim.correctionStartMs = null;
                anim.renderCorrection = 0;
                distKm = physDist;
            }
        }
        // notstarted или race not started: distKm = 0

        const coord = getCoordForDist(distKm, totalDistKm, maxIdx);
        if (coord) marker.setLatLng(coord);

        if (runnerId === activeRunnerId && anim.status === 'running') {
            const distEl = document.getElementById('panel-stat-dist');
            if (distEl) distEl.firstChild.textContent = distKm.toFixed(1);
        }
    });

    animationFrameId = requestAnimationFrame(animateRunnerFrame);
}

function getCoordForDist(distKm, totalDistKm, maxIdx) {
    for (const cp of eventCheckpoints) {
        if (Math.abs(distKm - cp.distance_km) <= 0.05) {
            return [cp.lat, cp.lon];
        }
    }
    const exactIdx = maxIdx * distKm / totalDistKm;
    const i0 = Math.min(maxIdx - 1, Math.floor(exactIdx));
    const i1 = i0 + 1;
    const t = exactIdx - i0;
    const p0 = routeCoordinates[i0];
    const p1 = routeCoordinates[i1];
    return [p0[0] + t * (p1[0] - p0[0]), p0[1] + t * (p1[1] - p0[1])];
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

function drawCheckpointMarkers() {
    checkpointMarkers.forEach(m => { if (map.hasLayer(m)) map.removeLayer(m); });
    checkpointMarkers = [];
    if (!eventCheckpoints || !eventCheckpoints.length) return;

    const totalDist = eventDistance || 5.0;

    eventCheckpoints.forEach(cp => {
        if (!cp.lat || !cp.lon) return;
        if (cp.distance_km <= 0 || cp.distance_km >= totalDist) return;

        const label = cp.distance_km % 1 === 0 ? String(cp.distance_km | 0) : String(cp.distance_km);

        const icon = L.divIcon({
            className: 'kt-marker',
            html: `<div style="
                background: #FF9500; color: white;
                width: 36px; height: 36px; border-radius: 50%;
                display: flex; flex-direction: column;
                align-items: center; justify-content: center;
                font-weight: 700; line-height: 1.1;
                border: 2px solid white;
                box-shadow: 0 2px 6px rgba(0,0,0,0.3);
                box-sizing: border-box;
            "><span style="font-size:11px">${label}</span><span style="font-size:8px">км</span></div>`,
            iconSize: [36, 36],
            iconAnchor: [18, 18]
        });

        const m = L.marker([cp.lat, cp.lon], { icon, interactive: false }).addTo(map);
        checkpointMarkers.push(m);
    });
}

function updateTrails() {
    Object.keys(runnerAnimations).forEach(runnerId => {
        const anim = runnerAnimations[runnerId];
        const marker = runnerMarkers[runnerId];
        if (!marker) return;

        const runner = allRunners.find(r => String(r.id) === runnerId);
        if (!runner) return;

        if (anim.status !== 'running') {
            if (anim.bearing != null) {
                anim.bearing = null;
                marker.setIcon(buildMarkerIcon(runner));
            }
            return;
        }

        const pos = marker.getLatLng();
        if (!runnerTrailHistory[runnerId]) runnerTrailHistory[runnerId] = [];
        const prev = runnerTrailHistory[runnerId][0];

        if (prev && (Math.abs(prev.lat - pos.lat) > 1e-6 || Math.abs(prev.lng - pos.lng) > 1e-6)) {
            const lat1 = prev.lat * Math.PI / 180;
            const lat2 = pos.lat * Math.PI / 180;
            const dLon = (pos.lng - prev.lng) * Math.PI / 180;
            const y = Math.sin(dLon) * Math.cos(lat2);
            const x = Math.cos(lat1) * Math.sin(lat2) - Math.sin(lat1) * Math.cos(lat2) * Math.cos(dLon);
            anim.bearing = (Math.atan2(y, x) * 180 / Math.PI + 360) % 360;
        }

        runnerTrailHistory[runnerId].unshift({ lat: pos.lat, lng: pos.lng });
        if (runnerTrailHistory[runnerId].length > 2) runnerTrailHistory[runnerId].length = 2;

        marker.setIcon(buildMarkerIcon(runner));
    });
}

function clearRunnerTrail(runnerId) {
    delete runnerTrailHistory[runnerId];
    if (runnerAnimations[runnerId]) runnerAnimations[runnerId].bearing = null;
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
