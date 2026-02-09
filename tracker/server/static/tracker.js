// server/static/tracker.js
/**
 * Основная логика трекера забега
 * Используется в rosneft.html и snow7.html
 */

// Конфигурация
const CONFIG = {
    API_BASE: 'http://localhost:5000/api',
    UPDATE_INTERVAL: 2000,  // 2 секунды для плавного обновления позиций
    MAX_SELECTED: 5,
    EVENT_NAME: 'rosneft',  // Будет переопределено в HTML
    STORAGE_KEY: 'selected_runners'  // Ключ для localStorage
};

// Глобальные переменные
let map = null;
let routeLayer = null;
let runnerMarkers = {};
let selectedRunnerIds = new Set();
let allRunners = [];
let isUpdating = false;
let routeType = 'loop';
let activePopups = new Map(); // Хранит активные всплывающие окна

// Цвета для статусов
const STATUS_COLORS = {
    'notstarted': '#9E9E9E',
    'started': '#EE2D62',
    'running': '#EE2D62',
    'finished': '#1a1a1a'
};

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
    
    // Очищаем localStorage других событий
    const otherEvents = ['rosneft', 'snow7'].filter(e => e !== CONFIG.EVENT_NAME);
    otherEvents.forEach(event => {
        const key = `${event}_selected_runners`;
        if (localStorage.getItem(key)) {
            console.log(`🗑️ Очищаю данные ${event} из localStorage`);
            localStorage.removeItem(key);
        }
    });
    
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
        
        console.log(`📍 Загружен маршрут: ${data.event_name}`);
        console.log(`📏 Тип маршрута: ${routeType}`);
        
        if (routeLayer) {
            map.removeLayer(routeLayer);
        }
        
        routeLayer = L.polyline(data.coordinates, {
            color: '#EE2D62',
            weight: 5,
            opacity: 0.8,
            smoothFactor: 1
        }).addTo(map);
        
        const startPoint = data.coordinates[0];
        L.marker(startPoint, {
            icon: L.divIcon({
                className: 'start-marker',
                html: '<div style="background: #EE2D62; color: white; padding: 5px 10px; border-radius: 5px; font-weight: bold;">СТАРТ/ФИНИШ</div>',
                iconSize: [100, 30],
                iconAnchor: [100, 5],  // Якорь в правом центре - маркер будет слева от точки
                popupAnchor: [50, 0]    // Всплывающее окно центрировано относительно точки
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
        allRunners = await response.json();
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
        const runners = await response.json();
        
        const stats = {
            total: runners.length,
            on_track: runners.filter(r => ['started', 'running'].includes(r.status)).length,
            finished: runners.filter(r => r.status === 'finished').length,
            not_started: runners.filter(r => r.status === 'notstarted').length
        };
        
        // Обновляем значения в аналитическом блоке (который теперь содержит статистику)
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
        // Загружаем аналитику
        const timestamp = new Date().getTime(); // Cache-busting
        const analyticsResponse = await fetch(`${CONFIG.API_BASE}/analytics?v=${timestamp}`);
        const analyticsData = await analyticsResponse.json();
        
        // Загружаем статистику участников
        const statsResponse = await fetch(`${CONFIG.API_BASE}/runners?event=${CONFIG.EVENT_NAME}&v=${timestamp}`);
        const runners = await statsResponse.json();
        
        const stats = {
            total: runners.length,
            on_track: runners.filter(r => ['started', 'running'].includes(r.status)).length,
            finished: runners.filter(r => r.status === 'finished').length,
            not_started: runners.filter(r => r.status === 'notstarted').length
        };
        
        const analyticsPanel = document.getElementById('analyticsContent');
        if (analyticsPanel) {
            analyticsPanel.innerHTML = renderAnalyticsHTML(analyticsData);
            
            // Обновляем значения общей статистики
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
    
    // Общая статистика участников (перенесена из верхней части)
    // Загружаем данные напрямую из runners, так как они доступны в loadStats
    // Для этого нужно обновить функцию, чтобы она получала и статистику участников
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
    
    // Статистика по полу
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
    
    // Топ-3 финишёров
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
        if (index === 0) {
            medalClass = 'gold';  // Золото для первого места
        } else if (index === 1) {
            medalClass = 'silver';  // Серебро для второго места
        } else if (index === 2) {
            medalClass = 'bronze';  // Бронза для третьего места
        }
        
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
    const selectedRunners = allRunners.filter(runner =>
        selectedRunnerIds.has(String(runner.id))
    );
    updateRunnerMarkers(selectedRunners);
}

// Функция для принудительного закрытия всех всплывающих окон
function closeAllPopupsForRefresh() {
    // Сохраняем список активных popup'ов перед закрытием
    const currentlyOpen = new Map(activePopups);
    
    // Закрываем все открытые всплывающие окна
    for (const [id, popup] of currentlyOpen) {
        const marker = runnerMarkers[id];
        if (marker && marker._popup) {
            marker.closePopup();
        }
    }
    
    // Очищаем карту активных popup'ов
    activePopups.clear();
}

function updateRunnerMarkers(runners) {
    // Сохраняем состояние открытых всплывающих окон перед обновлением
    const openPopups = new Map();
    for (const [id, marker] of Object.entries(runnerMarkers)) {
        if (marker._popup && marker._popup.isOpen && marker._popup.isOpen()) {
            openPopups.set(id, true);
        }
    }
    
    // Удаляем маркеры, которых больше нет в списке runners
    const runnerIds = new Set(runners.map(runner => runner.id));
    for (const [id, marker] of Object.entries(runnerMarkers)) {
        if (!runnerIds.has(Number(id))) {
            // Закрываем всплывающее окно, если оно было открыто
            if (marker._popup && marker._popup.isOpen && marker._popup.isOpen()) {
                marker.closePopup();
            }
            map.removeLayer(marker);
            delete runnerMarkers[id];
            
            // Удаляем из activePopups, если был там
            activePopups.delete(id);
        }
    }
    
    // Обновляем существующие маркеры или создаем новые
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
            // Обновляем позицию существующего маркера
            marker.setLatLng([runner.position.lat, runner.position.lng]);
            
            // Обновляем иконку
            marker.setIcon(icon);
            
            // Обновляем содержимое всплывающего окна
            const popupContent = createPopupContent(runner);
            marker.getPopup().setContent(popupContent);
        } else {
            // Создаем новый маркер с всплывающим окном
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
            
            // Добавляем обработчики событий для отслеживания состояния всплывающего окна
            marker.on('popupopen', function(e) {
                activePopups.set(runner.id, e.popup);
            });
            
            marker.on('popupclose', function(e) {
                activePopups.delete(runner.id);
            });
            
            runnerMarkers[runner.id] = marker;
        }
        
        // Если всплывающее окно было открыто ранее, открываем его снова
        if (openPopups.has(String(runner.id))) {
            marker.openPopup();
        }
    });
}

function createPopupContent(runner) {
    return `
        <div style="min-width: 200px;">
            <div style="font-weight: bold; font-size: 16px; margin-bottom: 5px;">
                №${runner.dorsal || runner.id} - ${runner.full_name || 'Участник'}
            </div>
            <div style="font-size: 14px; margin-bottom: 10px;">
                <div><strong>Категория:</strong> ${runner.category || 'N/A'}</div>
                <div><strong>Статус:</strong> ${getStatusText(runner.status)}</div>
                <div><strong>Дистанция:</strong> ${runner.current_distance?.toFixed(1) || 0} км</div>
                <div><strong>Скорость:</strong> ${runner.speed?.toFixed(1) || '--'} км/ч</div>
            </div>
            <div style="font-size: 12px; color: #666;">
                Обновлено: ${runner.last_update ? new Date(runner.last_update).toLocaleTimeString() : 'N/A'}
            </div>
        </div>
    `;
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
        const timestamp = new Date().getTime(); // Cache-busting
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
    console.log(`⏱️ Автообновление запущено для события: ${CONFIG.EVENT_NAME}`);
    setInterval(async () => {
        if (isUpdating) return;
        
        isUpdating = true;
        try {
            await loadAllRunners();
            await loadStats();
            await loadAnalytics(); // Обновляем аналитику вместе с другими данными
            updateStatus('Обновлено ' + new Date().toLocaleTimeString());
        } catch (error) {
            console.error('Ошибка автообновления:', error);
            updateStatus('Ошибка обновления');
        } finally {
            isUpdating = false;
        }
    }, CONFIG.UPDATE_INTERVAL);
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

// ============================================
// УПРАВЛЕНИЕ ВСПЛЫВАЮЩИМИ ОКНАМИ
// ============================================

function closeAllPopups() {
    // Закрываем все активные всплывающие окна
    for (const [id, popup] of activePopups) {
        const marker = runnerMarkers[id];
        if (marker && marker._popup) {
            marker.closePopup();
        }
    }
    activePopups.clear();
}

// ============================================
// ИНИЦИАЛИЗАЦИЯ
// ============================================

// Инициализация будет вызвана из HTML после установки CONFIG.EVENT_NAME
