// tracker.js - Основная логика трекера
(function() {
    'use strict';

    // Конфигурация
    const CONFIG = {
        API_BASE: 'https://ваш-сервер.com', // Заменить на реальный URL
        UPDATE_INTERVAL: 10000,
        MAX_SELECTED: 5
    };

    // Глобальные переменные
    let map = null;
    let routeLayer = null;
    let runnerMarkers = {};
    let selectedRunnerIds = new Set();
    let allRunnersCache = [];

    // Инициализация
    function init() {
        console.log('🚀 Инициализация трекера Снежной семерки');

        // Инициализация карты
        map = L.map('map').setView([56.03266, 92.95386], 15);

        L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', {
            attribution: '© OpenStreetMap contributors'
        }).addTo(map);

        // Загрузка маршрута и данных
        loadRoute();
        loadStats();
        loadSelectedRunners();
        startAutoUpdate();

        // Настройка поиска
        setupSearch();
    }

    // Загрузка маршрута
    async function loadRoute() {
        try {
            const response = await fetch(`${CONFIG.API_BASE}/api/route`);
            const routeData = await response.json();

            if (routeLayer) {
                map.removeLayer(routeLayer);
            }

            // Отрисовка маршрута
            routeLayer = L.polyline(routeData.coordinates, {
                color: '#2196F3',
                weight: 4,
                opacity: 0.7
            }).addTo(map);

            // Центрируем карту на маршруте
            map.fitBounds(routeLayer.getBounds(), { padding: [50, 50] });

        } catch (error) {
            console.error('❌ Ошибка загрузки маршрута:', error);
        }
    }

    // Загрузка статистики
    async function loadStats() {
        try {
            const response = await fetch(`${CONFIG.API_BASE}/api/stats`);
            const stats = await response.json();

            document.getElementById('statsPanel').innerHTML = `
                <div class="stat-box">
                    <div class="stat-value">${stats.total}</div>
                    <div>Всего участников</div>
                </div>
                <div class="stat-box">
                    <div class="stat-value">${stats.on_track}</div>
                    <div>На трассе</div>
                </div>
                <div class="stat-box">
                    <div class="stat-value">${stats.finished}</div>
                    <div>Финишировали</div>
                </div>
                <div class="stat-box">
                    <div class="stat-value">${stats.not_started}</div>
                    <div>Не стартовали</div>
                </div>
            `;

        } catch (error) {
            console.error('❌ Ошибка загрузки статистики:', error);
        }
    }

    // Поиск участников
    async function searchRunners() {
        const query = document.getElementById('searchInput').value.trim();
        if (!query) return;

        try {
            const response = await fetch(
                `${CONFIG.API_BASE}/api/search-runners?q=${encodeURIComponent(query)}`
            );
            const results = await response.json();

            const resultsDiv = document.getElementById('searchResults');
            resultsDiv.style.display = 'block';

            if (results.length === 0) {
                resultsDiv.innerHTML = '<p>Участники не найдены</p>';
                return;
            }

            let html = '<div style="background: white; border: 1px solid #ddd; border-radius: 4px; margin-top: 5px; max-height: 200px; overflow-y: auto;">';

            results.forEach(runner => {
                const isSelected = selectedRunnerIds.has(String(runner.id));
                const selectBtn = isSelected
                    ? '<button disabled style="background: #ccc">Выбран</button>'
                    : `<button onclick="selectRunner('${runner.id}')" ${selectedRunnerIds.size >= CONFIG.MAX_SELECTED ? 'disabled' : ''}>Выбрать</button>`;

                html += `
                    <div class="runner-item">
                        <div>
                            <strong>№${runner.dorsal}</strong> - ${runner.full_name}
                            <br><small>${runner.category} • ${runner.status}</small>
                        </div>
                        ${selectBtn}
                    </div>
                `;
            });

            html += '</div>';
            resultsDiv.innerHTML = html;

        } catch (error) {
            console.error('❌ Ошибка поиска:', error);
        }
    }

    // Выбор участника
    async function selectRunner(runnerId) {
        if (selectedRunnerIds.size >= CONFIG.MAX_SELECTED) {
            alert(`Максимум можно выбрать ${CONFIG.MAX_SELECTED} участников`);
            return;
        }

        try {
            const response = await fetch(`${CONFIG.API_BASE}/api/select-runner`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ runner_id: runnerId })
            });

            const result = await response.json();

            if (result.success) {
                selectedRunnerIds.add(String(runnerId));
                updateSelectedList();
                loadSelectedRunners();
            }

        } catch (error) {
            console.error('❌ Ошибка выбора участника:', error);
        }
    }

    // Загрузка выбранных участников
    async function loadSelectedRunners() {
        try {
            const response = await fetch(`${CONFIG.API_BASE}/api/selected-runners`);
            const runners = await response.json();

            // Обновление списка
            updateSelectedList();

            // Обновление маркеров на карте
            updateRunnerMarkers(runners);

        } catch (error) {
            console.error('❌ Ошибка загрузки выбранных участников:', error);
        }
    }

    // Обновление маркеров на карте
    function updateRunnerMarkers(runners) {
        // Удаляем старые маркеры
        Object.values(runnerMarkers).forEach(marker => {
            map.removeLayer(marker);
        });
        runnerMarkers = {};

        // Добавляем новые маркеры
        runners.forEach(runner => {
            if (runner.position) {
                const marker = L.marker([runner.position.lat, runner.position.lng])
                    .bindPopup(`
                        <b>№${runner.dorsal} - ${runner.full_name}</b><br>
                        Статус: ${runner.status}<br>
                        Дистанция: ${runner.current_distance} км<br>
                        Темп: ${runner.pace} мин/км
                    `)
                    .addTo(map);

                runnerMarkers[runner.id] = marker;
            }
        });
    }

    // Обновление списка выбранных участников
    function updateSelectedList() {
        const selectedList = document.getElementById('selectedList');
        const countSpan = document.getElementById('selectedCount');

        if (selectedRunnerIds.size === 0) {
            selectedList.innerHTML = '<p>Нет выбранных участников</p>';
        } else {
            // Можно добавить отображение имен выбранных участников
        }
    }

    // Автообновление
    function startAutoUpdate() {
        setInterval(() => {
            if (selectedRunnerIds.size > 0) {
                loadSelectedRunners();
            }
            loadStats();
        }, CONFIG.UPDATE_INTERVAL);
    }

    // Настройка поиска
    function setupSearch() {
        const searchInput = document.getElementById('searchInput');
        let searchTimeout;

        searchInput.addEventListener('input', function() {
            clearTimeout(searchTimeout);
            searchTimeout = setTimeout(searchRunners, 300);
        });
    }

    // Глобальные функции для HTML
    window.searchRunners = searchRunners;
    window.selectRunner = selectRunner;
    window.clearSelection = function() {
        selectedRunnerIds.clear();
        updateSelectedList();
        Object.values(runnerMarkers).forEach(marker => {
            map.removeLayer(marker);
        });
        runnerMarkers = {};
    };

    // Запуск при загрузке
    document.addEventListener('DOMContentLoaded', init);

})();