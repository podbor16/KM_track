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

// Цвета для статусов
const STATUS_COLORS = {
    'notstarted': '#9E9E9E',
    'started': '#4CAF50',
    'running': '#4CAF50',
    'finished': '#F44336'
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
        const response = await fetch(`${CONFIG.API_BASE}/route?event=${CONFIG.EVENT_NAME}`);
        
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
            color: '#FF6B35',
            weight: 5,
            opacity: 0.8,
            smoothFactor: 1
        }).addTo(map);
        
        const startPoint = data.coordinates[0];
        L.marker(startPoint, {
            icon: L.divIcon({
                className: 'start-marker',
                html: '<div style="background: #4CAF50; color: white; padding: 5px 10px; border-radius: 5px; font-weight: bold;">СТАРТ/ФИНИШ</div>',
                iconSize: [100, 30]
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
        const response = await fetch(`${CONFIG.API_BASE}/runners?event=${CONFIG.EVENT_NAME}`);
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
        const response = await fetch(`${CONFIG.API_BASE}/runners?event=${CONFIG.EVENT_NAME}`);
        const runners = await response.json();
        
        const stats = {
            total: runners.length,
            on_track: runners.filter(r => ['started', 'running'].includes(r.status)).length,
            finished: runners.filter(r => r.status === 'finished').length,
            not_started: runners.filter(r => r.status === 'notstarted').length
        };
        
        const statsPanel = document.getElementById('statsPanel');
        if (statsPanel) {
            statsPanel.innerHTML = `
                <div class="stat-box">
                    <div class="stat-value">${stats.total}</div>
                    <div class="stat-label">Всего участников</div>
                </div>
                <div class="stat-box">
                    <div class="stat-value">${stats.on_track}</div>
                    <div class="stat-label">На трассе</div>
                </div>
                <div class="stat-box">
                    <div class="stat-value">${stats.finished}</div>
                    <div class="stat-label">Финишировали</div>
                </div>
                <div class="stat-box">
                    <div class="stat-value">${stats.not_started}</div>
                    <div class="stat-label">Не стартовали</div>
                </div>
            `;
        }
    } catch (error) {
        console.error('Ошибка загрузки статистики:', error);
    }
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

function updateRunnerMarkers(runners) {
    Object.values(runnerMarkers).forEach(marker => {
        if (marker) map.removeLayer(marker);
    });
    runnerMarkers = {};
    
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
        
        const marker = L.marker(
            [runner.position.lat, runner.position.lng],
            { icon }
        ).addTo(map);
        
        const popupContent = createPopupContent(runner);
        marker.bindPopup(popupContent);
        
        runnerMarkers[runner.id] = marker;
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
        const response = await fetch(`${CONFIG.API_BASE}/search-runners?q=${encodeURIComponent(query)}&event=${CONFIG.EVENT_NAME}`);
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
// ИНИЦИАЛИЗАЦИЯ
// ============================================

document.addEventListener('DOMContentLoaded', init);
