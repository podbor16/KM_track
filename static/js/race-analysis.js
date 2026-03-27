// race-analysis.js - Логика для страницы Анализ забегов

document.addEventListener('DOMContentLoaded', function() {
    initializeRaceCards();
    initializeModal();
});

/**
 * Инициализирует модальное окно
 */
function initializeModal() {
    const modal = document.getElementById('race-modal');
    const closeBtn = document.querySelector('.race-modal-close');
    const backdrop = document.querySelector('.race-modal-backdrop');

    // Закрытие по кнопке "X"
    closeBtn.addEventListener('click', closeModal);

    // Закрытие по клику на backdrop
    backdrop.addEventListener('click', closeModal);

    // Предотвращение закрытия при клике в контейнер модали
    document.querySelector('.race-modal-container').addEventListener('click', function(e) {
        e.stopPropagation();
    });
}

/**
 * Закрывает модальное окно
 */
function closeModal() {
    const modal = document.getElementById('race-modal');
    modal.classList.remove('active');
}

/**
 * Открывает модальное окно с информацией о забеге
 * @param {string} raceName - Название забега
 */
function openRaceModal(raceName) {
    const modal = document.getElementById('race-modal');
    const title = document.querySelector('.race-modal-title');
    const body = document.querySelector('.race-modal-body');

    title.textContent = raceName;
    
    // Показываем загрузку
    body.innerHTML = '<div style="text-align: center; padding: 20px;"><p>Загрузка данных о забеге...</p></div>';
    
    // Загружаем данные из API БД
    loadRaceStats(raceName)
        .then(stats => {
            displayRaceModal(stats, raceName);
        })
        .catch(error => {
            console.error('Ошибка при загрузке статистики забега:', error);
            body.innerHTML = `
                <div class="race-info">
                    <p>${getRaceDescription(raceName)}</p>
                    <p style="margin-top: 20px; color: #666;">К сожалению, детальная статистика забега недоступна.</p>
                    <p style="margin: 10px 0; font-size: 13px; color: #999;">Убедитесь, что данные загружены в базу данных.</p>
                </div>
            `;
        });

    modal.classList.add('active');
    
    // Закрытие модали клавишей Escape
    document.addEventListener('keydown', handleEscapeKey);
}

/**
 * Получает event_name для API запроса по названию забега
 * @param {string} raceName - Название забега
 * @returns {string|null} - Event name для API или null
 */
function getRaceEventName(raceName) {
    const raceEventMap = {
        'Ночной забег': '7 km',      // Ночной забег на 7 км
        'Весна': '21 km',             // Весенний полумарафон
        'Красочный забег': '5 km',    // Красочный забег на 5 км
        'Женская Семерка': '7 km',    // Женская семерка на 7 км
        'Жара': '21 km',              // Летний полумарафон на 21 км
        'Детский Забег': '1 km',      // Детский забег на 1 км
        'Х Трейл': '7 km',            // Трейл на 7 км
        'Снежная семерка': '7 km'     // Зимний забег на 7 км
    };
    
    return raceEventMap[raceName] || null;
}

/**
 * Загружает статистику забега из API БД
 * @param {string} raceName - Название забега в БД (например, "Ночной забег")
 * @returns {Promise} - Promise с данными статистики
 */
async function loadRaceStats(raceName) {
    try {
        // Сначала пробуем загрузить данные из БД
        const response = await fetch(`/api/race-stats-db?race_name=${encodeURIComponent(raceName)}`);
        
        if (response.ok) {
            return await response.json();
        }
        
        // Если ошибка 404, возвращаем пустой объект
        if (response.status === 404) {
            throw new Error("Нет данных в БД");
        }
        
        throw new Error(`Ошибка при загрузке: ${response.status}`);
    } catch (error) {
        logger.error("Ошибка при загрузке из БД, используем fallback:", error);
        
        // Fallback: пытаемся загрузить из race_data.json используя event_name
        const eventName = getRaceEventName(raceName);
        if (eventName) {
            const fallbackResponse = await fetch(`/api/race-stats?event_name=${encodeURIComponent(eventName)}`);
            if (fallbackResponse.ok) {
                const data = await fallbackResponse.json();
                // Преобразуем в формат, совместимый с displayRaceModal
                return {
                    race_name: raceName,
                    race_distance: data.distance || 'N/A',
                    years_data: [],
                    best_result: data.best_result?.runner || null,
                    average_paces: data.average_pace || {},
                    gender_stats: data.statistics || {}
                };
            }
        }
        
        throw error;
    }
}

/**
 * Отображает данные забега в модальном окне
 * @param {Object} stats - Статистика забега
 * @param {string} raceName - Название забега
 */
function displayRaceModal(stats, raceName) {
    const body = document.querySelector('.race-modal-body');
    const description = getRaceDescription(raceName);
    
    // Извлекаем данные из статистики
    const bestResult = stats.best_result ? {
        name: `${stats.best_result.surname || ''} ${stats.best_result.name || ''}`.trim(),
        time: stats.best_result.time || 'N/A',
        pace: stats.best_result.pace || 'N/A'
    } : null;
    
    const avgPaces = stats.average_paces || {};
    const yearsData = stats.years_data || [];
    
    // Строим HTML модального окна
    let modalHTML = `
        <div class="race-details">
            <!-- Основная информация о забеге -->
            <div class="race-info-section">
                <h3 class="section-title">Информация о забеге</h3>
                <div class="info-row">
                    <span class="info-label">Название:</span>
                    <span class="info-value">${raceName}</span>
                </div>
                <div class="info-row">
                    <span class="info-label">Дистанция:</span>
                    <span class="info-value">${stats.race_distance || 'N/A'}</span>
                </div>
                <div class="info-row">
                    <span class="info-label">Описание:</span>
                    <span class="info-value">${description}</span>
                </div>
            </div>
    `;
    
    // Статистика последних результатов (если есть)
    if (yearsData && yearsData.length > 0) {
        const latestYear = yearsData[0]; // Первый элемент - самый свежий год
        
        modalHTML += `
            <div class="race-stats-section">
                <h3 class="section-title">Статистика (${latestYear.year})</h3>
                <div class="stats-grid">
                    <div class="stat-item">
                        <div class="stat-label">Всего участников</div>
                        <div class="stat-value">${latestYear.total_runners || 0}</div>
                    </div>
                    <div class="stat-item">
                        <div class="stat-label">Финишировали</div>
                        <div class="stat-value">${latestYear.finished_runners || 0}</div>
                    </div>
                    <div class="stat-item">
                        <div class="stat-label">Мужчин</div>
                        <div class="stat-value">${latestYear.male_count || 0}</div>
                    </div>
                    <div class="stat-item">
                        <div class="stat-label">Женщин</div>
                        <div class="stat-value">${latestYear.female_count || 0}</div>
                    </div>
                </div>
            </div>
        `;
    }
    
    // Лучший результат
    if (bestResult && bestResult.name) {
        modalHTML += `
            <div class="race-best-section">
                <h3 class="section-title">Лучший результат</h3>
                <div class="best-result">
                    <div class="best-runner-name">${bestResult.name}</div>
                    <div class="best-result-metrics">
                        <div class="metric">
                            <span class="metric-label">Время:</span>
                            <span class="metric-value">${bestResult.time}</span>
                        </div>
                        <div class="metric">
                            <span class="metric-label">Темп:</span>
                            <span class="metric-value">${bestResult.pace}</span>
                        </div>
                    </div>
                </div>
            </div>
        `;
    }
    
    // Средние темпы
    modalHTML += `
        <div class="race-pace-section">
            <h3 class="section-title">Средний темп участников</h3>
            <div class="pace-grid">
                <div class="pace-item">
                    <div class="pace-label">Общий средний темп</div>
                    <div class="pace-value">${avgPaces.all || 'N/A'}</div>
                </div>
                <div class="pace-item">
                    <div class="pace-label">Мужчины</div>
                    <div class="pace-value">${avgPaces.male || 'N/A'}</div>
                </div>
                <div class="pace-item">
                    <div class="pace-label">Женщины</div>
                    <div class="pace-value">${avgPaces.female || 'N/A'}</div>
                </div>
            </div>
        </div>
    `;
    
    // График участников по годам (если есть данные)
    if (yearsData && yearsData.length > 0) {
        modalHTML += `
            <div class="race-chart-section">
                <h3 class="section-title">Количество участников по годам</h3>
                <div class="race-chart-container">
                    <canvas id="raceChart"></canvas>
                </div>
            </div>
        `;
    }
    
    modalHTML += `
        </div> <!-- race-details -->
    `;
    
    body.innerHTML = modalHTML;
    
    // Отображаем график если есть данные
    if (yearsData && yearsData.length > 0) {
        displayRaceChart(yearsData);
    }
}

/**
 * Отображает график количества участников по годам
 * @param {Array} yearsData - Массив данных по годам
 */
function displayRaceChart(yearsData) {
    try {
        const ctx = document.getElementById('raceChart');
        
        if (!ctx) {
            console.error('Chart canvas element not found');
            return;
        }
        
        // Подготавливаем данные для графика
        const years = yearsData.map(y => y.year);
        const totalRunners = yearsData.map(y => y.total_runners);
        const finishedRunners = yearsData.map(y => y.finished_runners);
        const maleCount = yearsData.map(y => y.male_count);
        const femaleCount = yearsData.map(y => y.female_count);
        
        // Уничтожаем старший график если он существует
        if (window.raceChartInstance) {
            window.raceChartInstance.destroy();
        }
        
        // Создаем новый график
        window.raceChartInstance = new Chart(ctx, {
            type: 'line',
            data: {
                labels: years,
                datasets: [
                    {
                        label: 'Всего участников',
                        data: totalRunners,
                        borderColor: '#EE2D62',
                        backgroundColor: 'rgba(238, 45, 98, 0.1)',
                        tension: 0.4,
                        fill: true,
                        pointRadius: 6,
                        pointHoverRadius: 8,
                        pointBackgroundColor: '#EE2D62',
                        pointBorderColor: '#fff',
                        pointBorderWidth: 2
                    },
                    {
                        label: 'Финишировали',
                        data: finishedRunners,
                        borderColor: '#059C43',
                        backgroundColor: 'rgba(5, 156, 67, 0.1)',
                        tension: 0.4,
                        fill: false,
                        pointRadius: 6,
                        pointHoverRadius: 8,
                        pointBackgroundColor: '#059C43',
                        pointBorderColor: '#fff',
                        pointBorderWidth: 2
                    },
                    {
                        label: 'Мужчины',
                        data: maleCount,
                        borderColor: '#562872',
                        backgroundColor: 'rgba(86, 40, 114, 0.1)',
                        tension: 0.4,
                        fill: false,
                        pointRadius: 5,
                        pointHoverRadius: 7,
                        pointBackgroundColor: '#562872',
                        pointBorderColor: '#fff',
                        pointBorderWidth: 2
                    },
                    {
                        label: 'Женщины',
                        data: femaleCount,
                        borderColor: '#00BFDF',
                        backgroundColor: 'rgba(0, 191, 223, 0.1)',
                        tension: 0.4,
                        fill: false,
                        pointRadius: 5,
                        pointHoverRadius: 7,
                        pointBackgroundColor: '#00BFDF',
                        pointBorderColor: '#fff',
                        pointBorderWidth: 2
                    }
                ]
            },
            options: {
                responsive: true,
                maintainAspectRatio: false,
                plugins: {
                    legend: {
                        display: true,
                        position: 'top',
                        labels: {
                            font: {
                                size: 13,
                                weight: '500'
                            },
                            color: '#333',
                            padding: 15,
                            usePointStyle: true
                        }
                    },
                    tooltip: {
                        backgroundColor: 'rgba(0, 0, 0, 0.8)',
                        padding: 12,
                        titleFont: { size: 14, weight: 'bold' },
                        bodyFont: { size: 13 },
                        borderColor: '#ddd',
                        borderWidth: 1,
                        displayColors: true,
                        corners: 4
                    }
                },
                scales: {
                    y: {
                        beginAtZero: true,
                        max: Math.max(...totalRunners) * 1.1,
                        ticks: {
                            font: { size: 12 },
                            color: '#666',
                            stepSize: Math.ceil(Math.max(...totalRunners) / 5)
                        },
                        grid: {
                            color: 'rgba(0, 0, 0, 0.05)',
                            drawBorder: false
                        }
                    },
                    x: {
                        ticks: {
                            font: { size: 12 },
                            color: '#666'
                        },
                        grid: {
                            display: false
                        }
                    }
                }
            }
        });
        
    } catch (error) {
        console.error('Error displaying chart:', error);
    }
}

/**
 * Обработчик клавиши Escape для закрытия модали
 */
function handleEscapeKey(e) {
    if (e.key === 'Escape') {
        closeModal();
        document.removeEventListener('keydown', handleEscapeKey);
    }
}

/**
 * Возвращает описание забега по названию
 * @param {string} raceName - Название забега
 * @returns {string} - Описание забега
 */
function getRaceDescription(raceName) {
    const descriptions = {
        'Ночной забег': 'Забег под звёздами на набережной',
        'Весна': 'Весенний полумарафон по живописным маршрутам',
        'Красочный забег': 'Яркий 5-километровый забег на острове Татышев',
        'Женская Семерка': '7-км забег для женщин-спортсменов',
        'Жара': 'Летний полумарафон на площади Мира в августе',
        'Детский Забег': '1-км забег для самых маленьких спортсменов',
        'Х Трейл': 'Трейл-забег по пересечённой местности',
        'Снежная семерка': '7-км зимний забег на острове Татышев в декабре'
    };
    
    return descriptions[raceName] || 'Информация о забеге';
}

/**
 * Инициализирует интерактивность карточек забегов
 */
function initializeRaceCards() {
    const raceCards = document.querySelectorAll('.race-card');
    
    raceCards.forEach((card, index) => {
        // Обработчик клика
        card.addEventListener('click', function() {
            handleRaceCardClick(this, index);
        });

        // Поддержка клавиатуры для доступности
        card.setAttribute('tabindex', '0');
        card.setAttribute('role', 'button');
        
        card.addEventListener('keydown', function(e) {
            if (e.key === 'Enter' || e.key === ' ') {
                e.preventDefault();
                handleRaceCardClick(this, index);
            }
        });

        // Визуальная обратная связь при фокусе
        card.addEventListener('focus', function() {
            this.style.outline = '2px solid #ee2d62';
            this.style.outlineOffset = '2px';
        });

        card.addEventListener('blur', function() {
            this.style.outline = 'none';
        });
    });
}

/**
 * Обработчик клика по карточке забега
 * @param {HTMLElement} card - Элемент карточки
 * @param {number} index - Индекс карточки (0-7)
 */
function handleRaceCardClick(card, index) {
    // Получаем название забега из data атрибута или из заголовка
    const raceName = card.dataset.raceName || card.querySelector('.race-card-title')?.textContent.trim();
    
    // Логирование для отладки
    console.log('Выбран забег:', raceName);
    
    // Открываем модальное окно для всех карточек
    if (raceName) {
        openRaceModal(raceName);
    }
}

/**
 * Функция для поиска забега по названию (может быть полезна в будущем)
 * @param {string} raceName - Название забега
 * @returns {HTMLElement|null} - Элемент карточки или null
 */
function findRaceCard(raceName) {
    const raceCards = document.querySelectorAll('.race-card');
    
    for (let card of raceCards) {
        const title = card.querySelector('.race-card-title')?.textContent.trim() || card.dataset.raceName;
        if (title.toLowerCase() === raceName.toLowerCase()) {
            return card;
        }
    }
    
    return null;
}
