// legacy/static/tracker.js
/**
 * Основная логика трекера забега
 * Используется в tracker.html
 */

// Конфигурация
const CONFIG = {
    API_BASE: '/api',  // Используем относительный путь для FastAPI
    UPDATE_INTERVAL: 2000,  // 2 секунды для плавного обновления позиций
    MAX_SELECTED: 5,
    EVENT_NAME: 'night_run',  // Будет переопределено в HTML
    STORAGE_KEY: 'selected_runners',  // Ключ для localStorage
    TOTAL_RACE_KM: 5.0  // Общая дистанция забега в км
};

// Глобальные переменные
let map = null;
let routeLayer = null;
let runnerMarkers = {};
let runnerAnimators = {}; // Хранит animator'ы для плавной анимации маркеров
let selectedRunnerIds = new Set();
let allRunners = [];
let isUpdating = false;
let routeType = 'loop';
let activePopups = new Map(); // Хранит активные всплывающие окна
let routeCoordinates = []; // Сохраняем координаты маршрута для animations

// Цвета для статусов
const STATUS_COLORS = {
    'notstarted': '#9E9E9E',
    'started': '#EE2D62',
    'running': '#EE2D62',
    'finished': '#1a1a1a'
};

// ============================================
// КЛАСС ДЛЯ ПЛАВНОЙ АНИМАЦИИ МАРКЕРА
// ============================================

/**
 * Класс для интерполяции позиции маркера между обновлениями API
 * Обеспечивает плавное движение маркера по маршруту вместо скачков
 */
class RunnerMarkerAnimator {
    constructor(marker, routeCoordinates) {
        this.marker = marker;
        this.routeCoordinates = routeCoordinates;
        
        // Текущая позиция маркера на маршруте (0-100%)
        this.currentProgress = 0;
        
        // Целевая позиция маркера на маршруте (0-100%)
        this.targetProgress = 0;
        
        // Время начала последней анимации (для плавного перехода)
        this.animationStartTime = null;
        this.animationDuration = CONFIG.UPDATE_INTERVAL * 0.8; // 80% времени между обновлениями
        
        // Флаг направления: true = forward (0->100%), false = backward (100->0%)
        this.isForward = true;
        
        // requestAnimationFrame ID для отмены анимации
        this.animationFrameId = null;
    }
    
    /**
     * Обновить целевую позицию маркера на основе пройденной дистанции
     */
    updateTarget(currentDistanceKm, totalDistanceKm) {
        if (totalDistanceKm <= 0) {
            this.targetProgress = 0;
            return;
        }
        
        // Вычисляем прогресс (0-100%)
        this.targetProgress = (currentDistanceKm / totalDistanceKm) * 100;
        
        // Ограничиваем в диапазоне 0-100%
        this.targetProgress = Math.max(0, Math.min(100, this.targetProgress));
        
        // Запускаем анимацию к новой позиции
        this.startAnimation();
    }
    
    /**
     * Начать анимацию движения маркера от текущей к целевой позиции
     */
    startAnimation() {
        if (this.animationFrameId) {
            cancelAnimationFrame(this.animationFrameId);
        }
        
        this.animationStartTime = performance.now();
        this.animateFrame();
    }
    
    /**
     * Callback для requestAnimationFrame - интерполирует позицию
     */
    animateFrame = () => {
        if (!this.animationStartTime) return;
        
        const elapsed = performance.now() - this.animationStartTime;
        const progress = Math.min(elapsed / this.animationDuration, 1); // 0 to 1
        
        // Linear interpolation между текущей и целевой позицией
        const previousProgress = this.currentProgress;
        this.currentProgress = previousProgress + (this.targetProgress - previousProgress) * progress;
        
        // Ограничиваем прогресс в диапазоне 0-100
        this.currentProgress = Math.max(0, Math.min(100, this.currentProgress));
        
        // Обновляем позицию маркера
        this.updateMarkerPosition();
        
        // Продолжаем анимацию, если не достигли цели (99% вместо 100% для плавного завершения)
        if (progress < 0.99) {
            this.animationFrameId = requestAnimationFrame(this.animateFrame);
        } else {
            // Убеждаемся, что маркер точно на целевой позиции
            this.currentProgress = this.targetProgress;
            this.updateMarkerPosition();
            this.animationFrameId = null;
        }
    }
    
    /**
     * Обновить позицию маркера на карте на основе currentProgress
     */
    updateMarkerPosition() {
        if (!this.routeCoordinates || this.routeCoordinates.length === 0) {
            return;
        }
        
        const maxIndex = this.routeCoordinates.length - 1;
        
        // Вычисляем индекс в массиве координат
        let positionIndex;
        if (this.isForward) {
            // Движение вперед (0% -> 100%)
            positionIndex = Math.round(maxIndex * this.currentProgress / 100);
        } else {
            // Движение назад (100% -> 0%)
            positionIndex = Math.round(maxIndex * (100 - this.currentProgress) / 100);
        }
        
        // Ограничиваем индекс в диапазоне 0-maxIndex
        positionIndex = Math.max(0, Math.min(maxIndex, positionIndex));
        
        const coordinate = this.routeCoordinates[positionIndex];
        if (coordinate && coordinate.length === 2) {
            this.marker.setLatLng([coordinate[0], coordinate[1]]);
        }
    }
    
    /**
     * Изменить направление движения маркера (для разворотов на kt1, kt2 и т.д.)
     */
    changeDirection() {
        this.isForward = !this.isForward;
        console.log(`🔄 Маркер изменил направление: ${this.isForward ? 'вперед' : 'назад'}`);
    }
    
    /**
     * Получить текущий прогресс маркера (0-100%)
     */
    getProgress() {
        return this.currentProgress;
    }
    
    /**
     * Очистить ресурсы
     */
    dispose() {
        if (this.animationFrameId) {
            cancelAnimationFrame(this.animationFrameId);
            this.animationFrameId = null;
        }
    }
}

// ============================================
// РАБОТА С LOCALSTORAGE
// ============================================

function saveSelectedToStorage() {
    try {
        const selectedArray = Array.from(selectedRunnerIds);
        localStorage.setItem(CONFIG.STORAGE_KEY, JSON.stringify(selectedArray));
        console.log('💾 Сохранено в localStorage:', selectedArray);
    } catch (error) {
        console.error('Ошибка сохранения в localStorage:', error);
    }
}

function loadSelectedFromStorage() {
    try {
        const stored = localStorage.getItem(CONFIG.STORAGE_KEY);
        if (stored) {
            const selectedArray = JSON.parse(stored);
            selectedRunnerIds = new Set(selectedArray);
            console.log('📂 Загружено из localStorage:', selectedArray);
            return selectedArray;
        }
    } catch (error) {
        console.error('Ошибка загрузки из localStorage:', error);
    }
    return [];
}

function clearSelectedStorage() {
    try {
        localStorage.removeItem(CONFIG.STORAGE_KEY);
        console.log('🗑️ localStorage очищен');
    } catch (error) {
        console.error('Ошибка очистки localStorage:', error);
    }
}

// ============================================
// ИНИЦИАЛИЗАЦИЯ
// ============================================

async function init() {
    console.log('🚀 Инициализация трекера для события:', CONFIG.EVENT_NAME);
    
    loadSelectedFromStorage();
    await initMap();
    await loadAllRunners();
    await loadStats();
    
    if (selectedRunnerIds.size > 0) {
        updateSelectedList();
        updateSelectedRunnersMarkers();
    }
    
    setupSearch();
    startAutoUpdate();
    loadAnalytics(); // Загружаем аналитику после инициализации
    updateStatus('Трекер запущен');
}

// ============================================
// РАБОТА С КАРТОЙ
// ============================================

async function initMap() {
    map = L.map('map').setView([56.0075, 92.7246], 15);
    map.attributionControl.setPrefix('');
    
    L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', {
        attribution: '© OpenStreetMap'
    }).addTo(map);
    
    await loadRouteFromAPI();
}

async function loadRouteFromAPI() {
    try {
        updateStatus('Загрузка маршрута...');
        const timestamp = new Date().getTime(); // Cache-busting
        const response = await fetch(`${CONFIG.API_BASE}/route?event=${CONFIG.EVENT_NAME}&v=${timestamp}`);
        
        if (!response.ok) {
            throw new Error('Ошибка загрузки маршрута');
        }
        
        const data = await response.json();
        routeType = data.route_type || 'loop';
        
        // Сохраняем координаты маршрута для использования в анимации маркеров
        routeCoordinates = data.coordinates || [];
        
        console.log(`📍 Загружен маршрут: ${data.event_name}`);
        console.log(`📏 Тип маршрута: ${routeType}`);
        console.log(`📍 Координаты маршрута: ${routeCoordinates.length} точек`);
        
        if (routeLayer) {
            map.removeLayer(routeLayer);
        }
        
        routeLayer = L.polyline(routeCoordinates, {
            color: '#EE2D62',
            weight: 5,
            opacity: 0.8,
            smoothFactor: 1
        }).addTo(map);
        
        const startPoint = routeCoordinates[0];
        L.marker(startPoint, {
            icon: L.divIcon({
                className: 'start-marker',
                html: '<div style="background: #EE2D62; color: white; padding: 5px 10px; border-radius: 5px; font-weight: bold;">СТАРТ/ФИНИШ</div>',
                iconSize: [100, 30],
                iconAnchor: [100, 5],
                popupAnchor: [50, 0]
            })
        }).addTo(map);
        
        map.fitBounds(routeLayer.getBounds());
        updateStatus('Маршрут загружен');
        
    } catch (error) {
        console.error('Ошибка загрузки маршрута:', error);
        updateStatus('Ошибка загрузки маршрута');
    }
}

function centerMap() {
    if (routeLayer) {
        map.fitBounds(routeLayer.getBounds());
    }
}

// ============================================
// РАБОТА С УЧАСТНИКАМИ
// ============================================

async function loadAllRunners() {
    try {
        const timestamp = new Date().getTime(); // Cache-busting
        const response = await fetch(`${CONFIG.API_BASE}/runners?event=${CONFIG.EVENT_NAME}&v=${timestamp}`);
        const data = await response.json();
        // API возвращает RunnersListResponse со структурой { runners, total, ... }
        allRunners = Array.isArray(data) ? data : (data.runners || []);
        console.log(`Загружено участников: ${allRunners.length}`);
        updateSelectedRunnersMarkers();
    } catch (error) {
        console.error('Ошибка загрузки участников:', error);
        updateStatus('Ошибка загрузки данных');
    }
}

async function loadStats() {
    try {
        const timestamp = new Date().getTime(); // Cache-busting
        const response = await fetch(`${CONFIG.API_BASE}/runners?event=${CONFIG.EVENT_NAME}&v=${timestamp}`);
        const data = await response.json();
        const runners = Array.isArray(data) ? data : (data.runners || []);
        
        const stats = {
            total: runners.length,
            on_track: runners.filter(r => ['started', 'running'].includes(r.status)).length,
            finished: runners.filter(r => r.status === 'finished').length,
            not_started: runners.filter(r => r.status === 'notstarted').length
        };
        
        const totalRunnersElement = document.getElementById('total-runners-value');
        if (totalRunnersElement) {
            totalRunnersElement.textContent = stats.total;
        }
        
        const notStartedElement = document.getElementById('not-started-value');
        if (notStartedElement) {
            notStartedElement.textContent = stats.not_started;
        }
        
        const onTrackElement = document.getElementById('on-track-value');
        if (onTrackElement) {
            onTrackElement.textContent = stats.on_track;
        }
        
        const finishedElement = document.getElementById('finished-value');
        if (finishedElement) {
            finishedElement.textContent = stats.finished;
        }
    } catch (error) {
        console.error('Ошибка загрузки статистики:', error);
    }
}

async function loadAnalytics() {
    try {
        const timestamp = new Date().getTime();
        const analyticsResponse = await fetch(`${CONFIG.API_BASE}/analytics?v=${timestamp}`);
        const analyticsData = await analyticsResponse.json();
        
        const statsResponse = await fetch(`${CONFIG.API_BASE}/runners?event=${CONFIG.EVENT_NAME}&v=${timestamp}`);
        const data = await statsResponse.json();
        const runners = Array.isArray(data) ? data : (data.runners || []);
        
        const stats = {
            total: runners.length,
            on_track: runners.filter(r => ['started', 'running'].includes(r.status)).length,
            finished: runners.filter(r => r.status === 'finished').length,
            not_started: runners.filter(r => r.status === 'notstarted').length
        };
        
        const analyticsPanel = document.getElementById('analyticsContent');
        if (analyticsPanel) {
            analyticsPanel.innerHTML = renderAnalyticsHTML(analyticsData);
            
            document.getElementById('total-runners-value').textContent = stats.total;
            document.getElementById('not-started-value').textContent = stats.not_started;
            document.getElementById('on-track-value').textContent = stats.on_track;
            document.getElementById('finished-value').textContent = stats.finished;
        }
    } catch (error) {
        console.error('Ошибка загрузки аналитики:', error);
        const analyticsPanel = document.getElementById('analyticsContent');
        if (analyticsPanel) {
            analyticsPanel.innerHTML = `<p>Ошибка загрузки аналитических данных: ${error.message}</p>`;
        }
    }
}

function renderAnalyticsHTML(data) {
    if (!data || data.error) {
        return `<p>Ошибка: ${data?.error || 'Нет данных для отображения'}</p>`;
    }
    
    const generalStatsHTML = `
        <div class="analytics-section">
            <h3>📈 Общая статистика участников</h3>
            <div class="stats-grid">
                <div class="stat-card">
                    <div class="stat-card-value" id="total-runners-value">0</div>
                    <div class="stat-card-label">Всего участников</div>
                </div>
                <div class="stat-card">
                    <div class="stat-card-value" id="not-started-value">0</div>
                    <div class="stat-card-label">Не стартовали</div>
                </div>
                <div class="stat-card">
                    <div class="stat-card-value" id="on-track-value">0</div>
                    <div class="stat-card-label">На трассе</div>
                </div>
                <div class="stat-card">
                    <div class="stat-card-value" id="finished-value">0</div>
                    <div class="stat-card-label">Финишировали</div>
                </div>
            </div>
        </div>
    `;
    
    const genderStatsHTML = `
        <div class="analytics-section">
            <h3>👥 Статистика по полу</h3>
            <div class="gender-stats">
                <div class="gender-stat">
                    <div class="gender-title">Мужчины</div>
                    <div class="gender-count">${data.gender_stats.male_count}</div>
                    <div class="gender-avg-time">Среднее время: ${data.gender_stats.male_avg_time}</div>
                </div>
                <div class="gender-stat">
                    <div class="gender-title">Женщины</div>
                    <div class="gender-count">${data.gender_stats.female_count}</div>
                    <div class="gender-avg-time">Среднее время: ${data.gender_stats.female_avg_time}</div>
                </div>
            </div>
        </div>
    `;
    
    const topFinishersHTML = `
        <div class="analytics-section">
            <h3>🏆 Топ-3 финишёров</h3>
            <div class="top-finishers">
                <div>
                    <h4>Общий зачёт</h4>
                    ${renderTopFinishers(data.top_finishers.overall, 'overall')}
                </div>
                <div>
                    <h4>Мужчины</h4>
                    ${renderTopFinishers(data.top_finishers.male, 'male')}
                </div>
                <div>
                    <h4>Женщины</h4>
                    ${renderTopFinishers(data.top_finishers.female, 'female')}
                </div>
            </div>
        </div>
    `;
    
    return generalStatsHTML + genderStatsHTML + topFinishersHTML;
}

function renderTopFinishers(finishers, category) {
    if (!finishers || finishers.length === 0) {
        return '<p>Нет данных</p>';
    }
    
    let html = '';
    finishers.slice(0, 3).forEach((runner, index) => {
        let medalClass = '';
        if (index === 0) medalClass = 'gold';
        else if (index === 1) medalClass = 'silver';
        else if (index === 2) medalClass = 'bronze';
        
        html += `
            <div class="finisher-item ${medalClass}">
                <div class="finisher-place">${index + 1}</div>
                <div class="finisher-name">${runner.name} ${runner.surname}</div>
                <div class="finisher-time">${runner.time_str}</div>
            </div>
        `;
    });
    
    return html;
}

// ============================================
// МАРКЕРЫ НА КАРТЕ
// ============================================

function updateSelectedRunnersMarkers() {
    const selectedRunners = allRunners.filter(runner => {
        const runnerId = String(runner.id || runner.bib || runner.dorsal);
        return selectedRunnerIds.has(runnerId);
    });
    updateRunnerMarkers(selectedRunners);
}

function updateRunnerMarkers(runners) {
    const openPopups = new Map();
    for (const [id, marker] of Object.entries(runnerMarkers)) {
        if (marker._popup && marker._popup.isOpen && marker._popup.isOpen()) {
            openPopups.set(id, true);
        }
    }
    
    const runnerIds = new Set(runners.map(runner => runner.id));
    for (const [id, marker] of Object.entries(runnerMarkers)) {
        if (!runnerIds.has(Number(id))) {
            if (marker._popup && marker._popup.isOpen && marker._popup.isOpen()) {
                marker.closePopup();
            }
            
            // Очищаем animator при удалении маркера
            if (runnerAnimators[id]) {
                runnerAnimators[id].dispose();
                delete runnerAnimators[id];
            }
            
            map.removeLayer(marker);
            delete runnerMarkers[id];
            activePopups.delete(id);
        }
    }
    
    runners.forEach(runner => {
        if (!runner.position || !runner.position.lat || !runner.position.lng) {
            return;
        }
        
        const color = STATUS_COLORS[runner.status] || '#2196F3';
        let pulseAnimation = '';
        
        if (runner.speed && runner.speed > 12) {
            pulseAnimation = 'animation: pulse 1.5s infinite;';
        } else if (runner.speed && runner.speed < 8) {
            pulseAnimation = 'animation: slow-pulse 2s infinite;';
        }
        
        const icon = L.divIcon({
            className: `runner-marker moving-marker`,
            html: `
                <div style="
                    background: ${color};
                    width: 32px;
                    height: 32px;
                    border-radius: 50%;
                    display: flex;
                    align-items: center;
                    justify-content: center;
                    color: white;
                    font-weight: bold;
                    font-size: 14px;
                    border: 3px solid white;
                    box-shadow: 0 2px 4px rgba(0,0,0,0.3);
                    ${pulseAnimation}
                ">
                    ${runner.dorsal || runner.id}
                </div>
            `,
            iconSize: [38, 38],
            iconAnchor: [19, 19]
        });
        
        let marker = runnerMarkers[runner.id];
        
        if (marker) {
            // Маркер уже существует - обновляем позицию через animator
            marker.setIcon(icon);
            const popupContent = createPopupContent(runner);
            marker.getPopup().setContent(popupContent);
            
            // Обновляем animator для плавной анимации
            if (runnerAnimators[runner.id] && routeCoordinates.length > 0) {
                const totalDistance = runner.total_distance || CONFIG.TOTAL_RACE_KM || 5.0;
                runnerAnimators[runner.id].updateTarget(runner.current_distance || 0, totalDistance);
            }
        } else {
            // Создаём новый маркер
            marker = L.marker(
                [runner.position.lat, runner.position.lng],
                { icon }
            ).addTo(map);
            
            const popupContent = createPopupContent(runner);
            marker.bindPopup(popupContent, {
                closeOnClick: false,
                autoClose: false,
                closeButton: true
            });
            
            marker.on('popupopen', function(e) {
                activePopups.set(runner.id, e.popup);
                // Загружаем информацию о сегменте когда popup открывается (div уже в DOM)
                if (runner.status === 'running' || runner.status === 'started') {
                    loadAndDisplaySegmentInfo(runner.id);
                }
            });
            
            marker.on('popupclose', function(e) {
                activePopups.delete(runner.id);
            });
            
            runnerMarkers[runner.id] = marker;
            
            // Создаём animator для новой плавной анимации
            if (routeCoordinates.length > 0) {
                const animator = new RunnerMarkerAnimator(marker, routeCoordinates);
                runnerAnimators[runner.id] = animator;
                
                // Инициализируем начальную позицию
                const totalDistance = runner.total_distance || CONFIG.TOTAL_RACE_KM || 5.0;
                animator.updateTarget(runner.current_distance || 0, totalDistance);
            }
        }
        
        if (openPopups.has(String(runner.id))) {
            marker.openPopup();
        }
    });
}

function createPopupContent(runner) {
    // Для Running маркеров показываем дополнительную информацию о сегменте
    let additionalInfo = '';
    
    if (runner.status === 'running' || runner.status === 'started') {
        additionalInfo = `
            <div style="border-top: 1px solid #ddd; margin: 8px 0; padding-top: 8px;">
                <div style="font-weight: bold; color: #EE2D62; margin-bottom: 5px;">⚡ Текущий темп:</div>
                <div style="font-size: 16px; font-weight: bold; color: #2196F3;">
                    ${runner.pace ? (typeof runner.pace === 'string' && runner.pace.startsWith(':') ? '0' + runner.pace : runner.pace) : 'N/A'}
                </div>
            </div>
            <div id="segment-info-${runner.id}" style="border-top: 1px solid #ddd; margin: 8px 0; padding-top: 8px; font-size: 12px; min-height: 60px;">
                <div style="color: #999;">⏳ Загрузка информации о контрольных точках...</div>
            </div>
        `;
    }
    
    return `
        <div style="min-width: 270px;">
            <div style="font-weight: bold; font-size: 16px; margin-bottom: 5px;">
                №${runner.dorsal || runner.id} - ${runner.full_name || 'Участник'}
            </div>
            <div style="font-size: 14px; margin-bottom: 10px;">
                <div><strong>Категория:</strong> ${runner.category || 'N/A'}</div>
                <div><strong>Статус:</strong> ${getStatusText(runner.status)}</div>
                <div><strong>Дистанция:</strong> ${runner.current_distance?.toFixed(1) || 0} км</div>
                <div><strong>Скорость:</strong> ${runner.speed?.toFixed(1) || '--'} км/ч</div>
            </div>
            ${additionalInfo}
            <div style="font-size: 12px; color: #666; border-top: 1px solid #ddd; margin-top: 8px; padding-top: 8px;">
                Обновлено: ${runner.last_update ? new Date(runner.last_update).toLocaleTimeString() : 'N/A'}
            </div>
        </div>
    `;
}

/**
 * Загрузить информацию о последнем сегменте спортсмена и отобразить в popup
 */
async function loadAndDisplaySegmentInfo(runnerId) {
    try {
        let segmentDiv = document.getElementById(`segment-info-${runnerId}`);
        
        if (!segmentDiv) {
            console.log(`Div segment-info-${runnerId} не найден, popup может быть закрыт`);
            return;
        }
        
        const response = await fetch(
            `${CONFIG.API_BASE}/runner/${runnerId}/latest-segment?event=${CONFIG.EVENT_NAME}`
        );
        
        if (!response.ok) throw new Error(`API Error: ${response.status}`);
        
        const data = await response.json();
        console.log(`Сегмент для ${runnerId}:`, data);
        
        if (!data.success || !data.segments || data.segments.length === 0) {
            updateSegmentDisplay(runnerId, null);
            return;
        }
        
        const segment = data.segments[0];
        console.log(`Загружен сегмент для ${runnerId}:`, segment);
        updateSegmentDisplay(runnerId, segment);
    } catch (error) {
        console.warn(`Не удалось загрузить сегмент для спортсмена ${runnerId}:`, error);
        updateSegmentDisplay(runnerId, null);
    }
}

/**
 * Обновить отображение информации о сегменте в popup
 */
function updateSegmentDisplay(runnerId, segment) {
    const segmentDiv = document.getElementById(`segment-info-${runnerId}`);
    if (!segmentDiv) return;
    
    if (!segment) {
        segmentDiv.innerHTML = '<div style="color: #999;">Нет информации о контрольных точках</div>';
        return;
    }
    
    const segmentName = getSegmentName(segment.segment_code);
    const html = `
        <div style="background: #f5f5f5; padding: 8px; border-radius: 4px;">
            <div style="font-weight: bold; color: #333; margin-bottom: 4px;">
                📍 ${segmentName}
            </div>
            <div style="display: grid; grid-template-columns: 1fr 1fr; gap: 8px; font-size: 11px;">
                <div>
                    <span style="color: #666;">Время:</span><br>
                    <strong>${segment.sg_time_clear || 'N/A'}</strong>
                </div>
                <div>
                    <span style="color: #666;">Темп:</span><br>
                    <strong>${segment.sg_pace_avg || 'N/A'}</strong>
                </div>
                <div>
                    <span style="color: #666;">Место (абс):</span><br>
                    <strong>${segment.sg_rank_absolute || '-'}</strong>
                </div>
                <div>
                    <span style="color: #666;">Место (пол):</span><br>
                    <strong>${segment.sg_rank_sex || '-'}</strong>
                </div>
            </div>
            <div style="font-size: 11px; color: #666; margin-top: 4px;">
                Место в категории: <strong>${segment.sg_rank_category || '-'}</strong>
            </div>
        </div>
    `;
    
    segmentDiv.innerHTML = html;
}

/**
 * Получить человеческой формат названия сегмента
 */
function getSegmentName(segmentCode) {
    const names = {
        'start-kt1': '🏃 Start → KT1 (Разворот)',
        'kt1-finish': '🏁 KT1 → Finish (Финиш)',
        'kt1': '🔄 Контрольная точка 1',
        'kt2': '🔄 Контрольная точка 2',
        'start': '🏁 Старт',
        'finish': '🏁 Финиш'
    };
    return names[segmentCode] || `📍 ${segmentCode}`;
}

/**
 * Вспомогательная функция для преобразования темпа в км/ч
 * (копия из pace_calculator.py логики)
 */
function parse_pace_to_kmh_helper(paceStr) {
    if (!paceStr || paceStr.toLowerCase() === 'null' || paceStr.trim() === '') {
        return 10.0;
    }
    
    // Парсим формат "7:22" или "7'22"
    const match = paceStr.match(/(\d+)[:'](\d+)/);
    if (match) {
        const minutes = parseInt(match[1]);
        const seconds = parseInt(match[2]);
        
        const totalSecondsPerKm = minutes * 60 + seconds;
        if (totalSecondsPerKm === 0) {
            return 10.0;
        }
        
        // Скорость (км/ч) = 3600 сек/час / секунды на км
        const speedKmh = 3600.0 / totalSecondsPerKm;
        return parseFloat(speedKmh.toFixed(2));
    }
    
    return 10.0;
}

// ============================================
// ВЫБОР УЧАСТНИКОВ
// ============================================

function updateSelectedList() {
    const selectedList = document.getElementById('selectedList');
    const selectedCount = document.getElementById('selectedCount');
    const limitWarning = document.getElementById('selection-limit-warning');
    
    const selectedRunners = allRunners.filter(runner =>
        selectedRunnerIds.has(String(runner.id))
    );
    
    const currentCount = selectedRunners.length;
    if (selectedCount) selectedCount.textContent = currentCount;
    
    if (limitWarning) {
        limitWarning.style.display = currentCount >= CONFIG.MAX_SELECTED ? 'block' : 'none';
    }
    
    const clearBtn = document.querySelector('.control-btn.secondary');
    if (clearBtn) clearBtn.disabled = currentCount === 0;
    
    if (currentCount === 0) {
        selectedList.innerHTML = '<div class="empty-selection">Нет выбранных участников</div>';
        return;
    }
    
    let html = '';
    selectedRunners.forEach(runner => {
        const statusClass = runner.status === 'finished' ? 'finished' :
                           runner.status === 'started' ? 'started' : 'not-started';
        
        html += `
            <div class="selected-runner">
                <div class="runner-info">
                    <div class="runner-number">№${runner.dorsal}</div>
                    <div class="runner-name">${runner.full_name}</div>
                    <div class="runner-category">${runner.category} • <span class="${statusClass}">${getStatusText(runner.status)}</span></div>
                </div>
                <button class="remove-btn" onclick="deselectRunner('${runner.id}')">✕</button>
            </div>
        `;
    });
    
    selectedList.innerHTML = html;
    updateSelectedRunnersMarkers();
}

async function selectRunner(runnerId) {
    if (selectedRunnerIds.size >= CONFIG.MAX_SELECTED) {
        alert(`Максимум можно выбрать ${CONFIG.MAX_SELECTED} участников`);
        return;
    }
    
    if (selectedRunnerIds.has(runnerId)) {
        alert('Этот участник уже добавлен в отслеживаемые');
        return;
    }
    
    try {
        const response = await fetch(`${CONFIG.API_BASE}/select-runner`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ runner_id: runnerId })
        });
        
        const result = await response.json();
        
        if (result.success) {
            selectedRunnerIds.add(runnerId);
            saveSelectedToStorage();
            await loadAllRunners();
            updateSelectedList();
            updateStatus(`Участник №${runnerId} добавлен в отслеживаемые`);
        } else {
            alert(result.error || 'Ошибка добавления участника');
        }
    } catch (error) {
        console.error('Ошибка выбора участника:', error);
        alert('Ошибка связи с сервером');
    }
}

async function deselectRunner(runnerId) {
    try {
        const response = await fetch(`${CONFIG.API_BASE}/deselect-runner`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ runner_id: runnerId })
        });
        
        const result = await response.json();
        
        if (result.success) {
            selectedRunnerIds.delete(runnerId);
            saveSelectedToStorage();
            
            if (runnerMarkers[runnerId]) {
                map.removeLayer(runnerMarkers[runnerId]);
                delete runnerMarkers[runnerId];
            }
            
            await loadAllRunners();
            updateSelectedList();
            updateStatus(`Участник №${runnerId} удален из отслеживаемых`);
        }
    } catch (error) {
        console.error('Ошибка удаления участника:', error);
    }
}

async function clearSelection() {
    if (!confirm('Очистить всех выбранных участников?')) {
        return;
    }
    
    const runnerIds = Array.from(selectedRunnerIds);
    for (const runnerId of runnerIds) {
        await deselectRunner(runnerId);
    }
    
    clearSelectedStorage();
}

// ============================================
// ПОИСК
// ============================================

async function searchRunners() {
    const query = document.getElementById('searchInput').value.trim();
    const resultsDiv = document.getElementById('searchResults');
    
    if (!query) {
        resultsDiv.innerHTML = '';
        resultsDiv.style.display = 'none';
        return;
    }
    
    try {
        const timestamp = new Date().getTime();
        const response = await fetch(`${CONFIG.API_BASE}/search-runners?q=${encodeURIComponent(query)}&event=${CONFIG.EVENT_NAME}&v=${timestamp}`);
        const results = await response.json();
        
        if (results.length === 0) {
            resultsDiv.innerHTML = '<div class="runner-item">Участники не найдены</div>';
            resultsDiv.style.display = 'block';
            return;
        }
        
        let html = '';
        results.forEach(runner => {
            const isSelected = selectedRunnerIds.has(String(runner.id));
            const canSelect = !isSelected && selectedRunnerIds.size < CONFIG.MAX_SELECTED;
            
            html += `
                <div class="runner-item">
                    <div class="runner-info">
                        <div class="runner-number">№${runner.dorsal}</div>
                        <div class="runner-name">${runner.full_name}</div>
                        <div class="runner-category">${runner.category} • ${getStatusText(runner.status)}</div>
                    </div>
                    <button
                        class="select-btn ${isSelected ? 'selected' : ''}"
                        ${!canSelect ? 'disabled' : ''}
                        onclick="${canSelect ? `selectRunner('${runner.id}')` : ''}"
                    >
                        ${isSelected ? 'Выбран' : 'Выбрать'}
                    </button>
                </div>
            `;
        });
        
        resultsDiv.innerHTML = html;
        resultsDiv.style.display = 'block';
    } catch (error) {
        console.error('Ошибка поиска:', error);
        resultsDiv.innerHTML = '<div class="runner-item">Ошибка поиска</div>';
        resultsDiv.style.display = 'block';
    }
}

function setupSearch() {
    const searchInput = document.getElementById('searchInput');
    let searchTimeout;
    
    if (!searchInput) return;
    
    searchInput.addEventListener('input', function() {
        clearTimeout(searchTimeout);
        searchTimeout = setTimeout(searchRunners, 300);
    });
    
    document.addEventListener('click', function(event) {
        const resultsDiv = document.getElementById('searchResults');
        if (!searchInput.contains(event.target) && !resultsDiv.contains(event.target)) {
            resultsDiv.style.display = 'none';
        }
    });
}

// ============================================
// АВТООБНОВЛЕНИЕ
// ============================================

function startAutoUpdate() {
    console.log(`⏱️ Автообновление запущен для события: ${CONFIG.EVENT_NAME}`);
    setInterval(async () => {
        if (isUpdating) return;
        
        isUpdating = true;
        try {
            await loadAllRunners();
            await loadStats();
            await loadAnalytics();
            updateStatus('Обновлено ' + new Date().toLocaleTimeString());
        } catch (error) {
            console.error('Ошибка автообновления:', error);
            updateStatus('Ошибка обновления');
        } finally {
            isUpdating = false;
        }
    }, CONFIG.UPDATE_INTERVAL);
    
    // Запускаем отслеживание сегментов для каждого выбранного спортсмена
    startSegmentTracking();
}

// ============================================
// ОТСЛЕЖИВАНИЕ СЕГМЕНТОВ И КОРРЕКЦИЯ ТЕМПА
// ============================================

const SEGMENT_TRACKING = {
    POLLING_INTERVAL: 7000, // 7 секунд между опросами
    lastSeenSegments: {}, // Сохраняем последний ID сегмента для каждого спортсмена
    intervalId: null
};

/**
 * Запустить отслеживание прохождения контрольных точек (сегментов)
 * Используется для динамической корректировки темпа и смены направления маркера
 */
function startSegmentTracking() {
    if (SEGMENT_TRACKING.intervalId) {
        clearInterval(SEGMENT_TRACKING.intervalId);
    }
    
    SEGMENT_TRACKING.intervalId = setInterval(async () => {
        if (selectedRunnerIds.size === 0) return;
        
        // Проверяем новые сегменты для каждого выбранного спортсмена
        for (const runnerId of selectedRunnerIds) {
            try {
                await checkRunnerSegments(parseInt(runnerId));
            } catch (error) {
                console.error(`Ошибка при проверке сегментов для спортсмена ${runnerId}:`, error);
            }
        }
    }, SEGMENT_TRACKING.POLLING_INTERVAL);
    
    console.log(`📊 Отслеживание сегментов запущено (опрос каждые ${SEGMENT_TRACKING.POLLING_INTERVAL / 1000}с)`);
}

/**
 * Проверить наличие новых сегментов (контрольных точек) для спортсмена
 */
async function checkRunnerSegments(runnerId) {
    try {
        const response = await fetch(
            `${CONFIG.API_BASE}/runner/${runnerId}/latest-segment?event=${CONFIG.EVENT_NAME}`
        );
        
        if (!response.ok) return;
        
        const data = await response.json();
        if (!data.success || data.segments.length === 0) return;
        
        const latestSegment = data.segments[0];
        const segmentKey = `${runnerId}_${latestSegment.segment_code}`;
        
        // Проверяем, новый ли это сегмент
        if (SEGMENT_TRACKING.lastSeenSegments[segmentKey]) {
            return; // Уже обработали этот сегмент
        }
        
        // Отмечаем как обработанный
        SEGMENT_TRACKING.lastSeenSegments[segmentKey] = true;
        
        console.log(`✅ Спортсмен ${runnerId} прошел ${latestSegment.segment_code}:`);
        console.log(`   Темп: ${latestSegment.sg_pace_avg || 'N/A'}`);
        console.log(`   Место: ${latestSegment.sg_rank_category || 'N/A'} в категории`);
        
        // Обновляем маркер спортсмена
        onSegmentPassed(runnerId, latestSegment);
        
    } catch (error) {
        console.warn(`Не удалось получить сегменты для спортсмена ${runnerId}:`, error);
    }
}

/**
 * Callback при прохождении спортсменом контрольной точки (сегмента)
 * Корректирует темп и меняет направление маркера при разворотах
 */
/**
 * Непрерывное обновление позиций маркеров на маршруте
 * Вызывается один раз при инициализации для периодического отслеживания спортсменов
 */
function startContinuousTracking() {
    console.log('Запущено непрерывное отслеживание позиций маркеров...');
    
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
            console.warn('Ошибка обновления позиций:', error);
        }
    }, CONFIG.UPDATE_INTERVAL);
}

/**
 * Callback при прохождении спортсменом контрольной точки (сегмента)
 * Корректирует темп и меняет направление маркера при разворотах
 * 
 * Поддерживаемые segment_code:
 * - "start-kt1": Спортсмен прошел от старта к разороту (kt1 на 50%)
 * - "kt1-finish": Спортсмен прошел от разворота к финишу
 */
function onSegmentPassed(runnerId, segment) {
    const animator = runnerAnimators[runnerId];
    if (!animator) {
        console.warn(`🚨 Animator для спортсмена ${runnerId} не найден`);
        return;
    }
    
    const segmentCode = segment.segment_code || '';
    const totalDistance = CONFIG.TOTAL_RACE_KM || 5.0;
    
    console.log(`📍 Спортсмен ${runnerId} прошел сегмент: ${segmentCode}`);
    console.log(`   Темп: ${segment.sg_pace_avg || 'N/A'}`);
    console.log(`   Место: ${segment.sg_rank_category || 'N/A'} в категории`);
    
    // Логика телепортации в зависимости от segment_code
    if (segmentCode === 'start-kt1') {
        // ТЕЛЕПОРТАЦИЯ К РАЗОРОТУ (KT1 = 50% дистанции)
        console.log(`🚀 Телепортация к KT1 (50% дистанции)`);
        
        // Телепортируем маркер к KT1
        const kt1Distance = totalDistance / 2; // 50% дистанции
        animator.updateTarget(kt1Distance, totalDistance);
        animator.currentProgress = 50; // Сразу перемещаем на 50%
        animator.updateMarkerPosition();
        
        // Меняем направление на "назад" для второго плеча
        animator.isForward = false;
        
        // Обновляем темп спортсмена в памяти для UI
        const runner = allRunners.find(r => Number(r.id) === runnerId);
        if (runner && segment.sg_pace_avg) {
            // Пересчитываем скорость на основе нового темпа
            runner.speed = parse_pace_to_kmh_helper(segment.sg_pace_avg);
            runner.pace = segment.sg_pace_avg;
            console.log(`📈 Обновленная скорость: ${runner.speed?.toFixed(2)} км/ч`);
        }
    }
    else if (segmentCode === 'kt1-finish') {
        // ТЕЛЕПОРТАЦИЯ К ФИНИШУ (100% дистанции)
        console.log(`🏁 Телепортация к ФИНИШУ (100% дистанции)`);
        
        // Телепортируем маркер к финишу
        animator.updateTarget(totalDistance, totalDistance);
        animator.currentProgress = 100; // Сразу перемещаем на 100%
        animator.updateMarkerPosition();
        
        // Обновляем темп спортсмена
        const runner = allRunners.find(r => Number(r.id) === runnerId);
        if (runner && segment.sg_pace_avg) {
            runner.speed = parse_pace_to_kmh_helper(segment.sg_pace_avg);
            runner.pace = segment.sg_pace_avg;
            console.log(`📈 Финальная скорость: ${runner.speed?.toFixed(2)} км/ч`);
        }
    }
    else if (segmentCode === 'kt1' || segmentCode === 'kt2' || segmentCode === 'kt3') {
        // Изменить направление для промежуточных контрольных точек
        animator.changeDirection();
        console.log(`🔄 Маркер изменил направление на ${segmentCode}`);
        
        // Обновляем темп спортсмена
        if (segment.sg_pace_avg) {
            const runner = allRunners.find(r => Number(r.id) === runnerId);
            if (runner) {
                runner.speed = parse_pace_to_kmh_helper(segment.sg_pace_avg);
                runner.pace = segment.sg_pace_avg;
            }
        }
    }
}

/**
 * Остановить отслеживание сегментов
 */
function stopSegmentTracking() {
    if (SEGMENT_TRACKING.intervalId) {
        clearInterval(SEGMENT_TRACKING.intervalId);
        SEGMENT_TRACKING.intervalId = null;
        console.log('🛑 Отслеживание сегментов остановлено');
    }
}

// ============================================
// ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ
// ============================================

function getStatusText(status) {
    const statusMap = {
        'notstarted': 'Не стартовал',
        'started': 'На трассе',
        'running': 'На трассе',
        'finished': 'Финишировал'
    };
    
    return statusMap[status] || status || 'Неизвестно';
}

function updateStatus(message) {
    const statusPanel = document.getElementById('statusPanel');
    if (statusPanel) statusPanel.textContent = message;
}

function closeAllPopups() {
    for (const [id, popup] of activePopups) {
        const marker = runnerMarkers[id];
        if (marker && marker._popup) {
            marker.closePopup();
        }
    }
    activePopups.clear();
}
