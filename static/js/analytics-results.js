// legacy/static/analytics-results.js
// Javascript для страницы результатов забега
let allRunners = [];
let filteredRunners = [];
let sortState = { column: 'time_gun', direction: 'asc' }; // Дефолт: по официальному времени
let currentEvent = 'night_run';
let currentYear = new Date().getFullYear();
const timeMode = 'gun'; // фиксировано для сегментных функций
let activeSegmentCode = null;
let segmentRankingsCache = {};  // { segmentCode: [rows] }
let activeSegmentEventId = null;
const runnerDataMap = new Map(); // resultId → runner object

const eventNameMap = KMUtils.EVENT_NAMES;
const eventColorMap = KMUtils.EVENT_COLORS;

// Маппинг событие + год на event_id в БД
const eventYearToIdMap = {
    'night_run_2025': 67,
    'night_run_2026': 104,
    'vesna_2025': 71,
    'vesna_2026': 106,
    'colorrun_2025': 75,
    'colorrun_2026': 108,
    'girlseven_2025': 79,
    'girlseven_2026': 110,
    'kids_2025': 83,
    'kids_2026': 113,
    'zhara_2025': [89, 91, 93],       // три дистанции
    'zhara_2026': [115, 116, 117],    // три дистанции
    'xtrailrun_2025': 95,
    'xtrailrun_2026': 117,
    'snow7_2025': 99,
    'snow7_2026': 119,
    'pervomay_2026': [142, 143]  // 5 км (142), 21.1 км (143)
};

// Инициализация страницы — дефолт: активный забег + прошлый год
document.addEventListener('DOMContentLoaded', async function() {
    populateYearSelector();
    try {
        const cfg = await fetch('/api/current-event').then(r => r.json());
        currentEvent = cfg.event || 'night_run';
        const cfgYear = cfg.year || new Date().getFullYear();
        // Показывать текущий год если для него есть данные, иначе прошлый
        currentYear = eventYearToIdMap[`${currentEvent}_${cfgYear}`] !== undefined
            ? cfgYear
            : cfgYear - 1;
    } catch {
        currentEvent = 'night_run';
        currentYear  = new Date().getFullYear() - 1;
    }
    document.getElementById('eventResultsSelector').value = currentEvent;
    document.getElementById('yearResultsSelector').value  = currentYear;
    updateEventThemeColor();
    updateEventCardBackground();
    updatePageTitle();
    loadRunnersData();

    new SSEClient('/api/sse/notify', {
        results_updated: (msg) => {
            const eventIds = eventYearToIdMap[`${currentEvent}_${currentYear}`];
            const ids = Array.isArray(eventIds) ? eventIds : [eventIds];
            if (!msg.event_id || ids.includes(msg.event_id)) loadRunnersData(true);
        }
    });
});

// Функция обновления цвета темы в зависимости от события
function updateEventThemeColor() {
    const color = eventColorMap[currentEvent] || '#EE2D62';
    document.documentElement.style.setProperty('--primary-color', color);
}

// Функция для заполнения селектора годов
function populateYearSelector() {
    const yearSelector = document.getElementById('yearResultsSelector');
    const currentYear = new Date().getFullYear();
    
    // Добавляем годы от текущего до 2020
    for (let year = currentYear; year >= 2020; year--) {
        const option = document.createElement('option');
        option.value = year;
        option.textContent = year;
        yearSelector.appendChild(option);
    }
    
    // Устанавливаем текущий год по умолчанию
    yearSelector.value = currentYear;
}

// Функция переключения события и года
async function switchEventResults() {
    currentEvent = document.getElementById('eventResultsSelector').value;
    currentYear = parseInt(document.getElementById('yearResultsSelector').value);

    // Обновляем цвет темы
    updateEventThemeColor();

    // Меняем фоновую картинку карточки события
    updateEventCardBackground();

    // Обновляем заголовок страницы
    updatePageTitle();

    // Перезагружаем данные
    loadRunnersData();
}

function updatePageTitle() {
    const title = document.getElementById('pageTitle');
    if (!title) return;
    const name = eventNameMap[currentEvent] || currentEvent;
    const distSel = document.getElementById('distanceFilter');
    const dist = distSel && distSel.value ? `, ${distSel.value}` : '';
    title.innerHTML = `Результаты<br><span class="page-title-event">${name} ${currentYear}${dist}</span>`;
}

// Функция обновления фонового изображения карточки события
function updateEventCardBackground() {
    const eventCard = document.getElementById('eventCard');
    const eventDisplayName = eventNameMap[currentEvent] || '';
    const imageUrl = eventDisplayName ? `/static/images/events/${encodeURIComponent(eventDisplayName)}.png` : '';
    eventCard.style.backgroundImage = `url('${imageUrl}')`;
}

// Функция загрузки данных
async function loadRunnersData(silent = false) {
    console.log(`Загрузка данных для результатов: ${currentEvent} ${currentYear}`);
    if (!silent) {
        allRunners = [];
        filteredRunners = [];
        document.getElementById('resultsTableBody').innerHTML = '';
        document.getElementById('resultsWrapper').style.display = 'none';
        showLoading(true);
    }

    try {
        let rawData = [];
        
        // Получаем event_id из маппинга события+года
        const mapKey = `${currentEvent}_${currentYear}`;
        const eventIdOrIds = eventYearToIdMap[mapKey];
        
        if (eventIdOrIds !== undefined) {
            // Загружаем из БД через API с правильным event_id
            console.log('📊 Загрузка результатов из БД через API');
            
            // Если это массив дистанций (для Жары), загружаем все вместе
            const eventIds = Array.isArray(eventIdOrIds) ? eventIdOrIds : [eventIdOrIds];
            
            for (const eventId of eventIds) {
                const response = await fetch(`/api/event-results?event_id=${eventId}`);
                
                if (!response.ok) {
                    throw new Error(`Ошибка загрузки результатов для event_id=${eventId}`);
                }
                
                const data = await response.json();
                console.log(`✅ Загружено из БД (event_id=${eventId}):`, data.results ? data.results.length : 0, 'участников');
                rawData = rawData.concat(data.results || []);
            }
        } else {
            // Для неизвестных комбинаций загружаем из legacy API
            const eventName = eventNameMap[currentEvent] || 'Ночной забег';
            const apiUrl = `/api/race-results?event_name=${encodeURIComponent(eventName)}&year=${currentYear}`;
            console.log('Запрос к ' + apiUrl);
            
            const response = await fetch(apiUrl);
            console.log('Ответ от /api/race-results получен, статус:', response.status);
            const data = await response.json();
            
            rawData = Array.isArray(data) ? data : (data.runners || data.data || data.results || []);
        }
        
        console.log('rawData:', rawData.length, 'элементов');
        
        // Нормализуем данные в единый формат
        allRunners = normalizeRunnerData(rawData);
        
        console.log('allRunners после нормализации:', allRunners.length);
        if (allRunners.length > 0) {
            console.log('Пример первого элемента:', allRunners[0]);
        }
        
        // Заполняем фильтры
        populateAgeGroups(allRunners);
        populateDistances(allRunners);
        
        applyFilters();
        if (!silent) {
            showLoading(false);
            document.getElementById('resultsWrapper').style.display = '';
        }

        // Загружаем кнопки КТ для одиночного event_id
        if (!silent && eventIdOrIds !== undefined && !Array.isArray(eventIdOrIds)) {
            loadSegmentTabs(eventIdOrIds);
        }
    } catch (error) {
        if (!silent) {
            console.error('❌ Ошибка загрузки данных:', error);
            showError('Ошибка загрузки данных: ' + error.message);
            showLoading(false);
            document.getElementById('resultsWrapper').style.display = '';
        } else {
            console.warn('⚠️ Фоновое обновление результатов не удалось:', error.message);
        }
    }
}

// Функция нормализации данных из разных источников
function normalizeRunnerData(runners) {
    if (!Array.isArray(runners)) {
        console.warn('⚠️ Ожидается массив, получено:', typeof runners);
        return [];
    }
    
    return runners.map(runner => {
        // Если это уже нормализованные данные, возвращаем как есть
        if (runner.status !== undefined && runner.gender !== undefined) {
            return runner;
        }
        
        // Нормализуем данные из БД
        return {
            // ID результата (важно для загрузки сегментов!)
            id: runner.id || runner.client_id || '',
            
            // Основная информация
            surname: runner.surname || '',
            name: runner.name || '',
            full_name: runner.full_name || `${runner.surname || ''} ${runner.name || ''}`,
            birthdate: runner.birthday || runner.birthdate || '',
            gender: convertSexToGender(runner.sex),  // Будет "Мужчина" или "Женщина"
            sex: runner.sex,
            category: KMUtils.normalizeCategory(runner.category || ''),

            // Статус и результаты
            status: convertRaceStatus(runner.race_status),
            race_status: runner.race_status,

            // Время и темп
            'times.official_:::finish:::': runner.time_clear_finish,
            time_clear_finish: runner.time_clear_finish,
            time_gun_finish: runner.time_gun_finish,
            finish_pace_avg: runner.finish_pace_avg,
            finish_pace_avg_gun: runner.finish_pace_avg_gun,
            finish_pace_avg_clean: runner.finish_pace_avg_clean,
            
            // Место и ранк (официальное время)
            rank_absolute: runner.rank_absolute,
            rank_sex: runner.rank_sex,
            rank_category: runner.rank_category,
            // Место по чистому времени
            rank_absolute_clean: runner.rank_absolute_clean,
            rank_sex_clean: runner.rank_sex_clean,
            rank_category_clean: runner.rank_category_clean,
            start_number: runner.start_number,
            
            // Дистанция и событие - используем distance_from_event из БД если есть
            event: runner.event || runner.distance_from_event || 'Ночной забег',
            distance: runner.distance || runner.distance_from_event || '5 км',
            
            // Дополнительные поля
            checkpoints: runner.checkpoints || {}
        };
    });
}

// Конвертируем пол из БД в формат приложения (сохраняем на русском)
function convertSexToGender(sex) {
    if (!sex) return '';
    const lowerSex = sex.toLowerCase();
    if (lowerSex.includes('муж') || lowerSex === 'male' || lowerSex === 'm') return 'Мужчина';
    if (lowerSex.includes('жен') || lowerSex === 'female' || lowerSex === 'f') return 'Женщина';
    return sex;  // Возвращаем исходное значение если не распознали
}

// Конвертируем статус из БД в формат приложения
function convertRaceStatus(raceStatus) {
    if (!raceStatus) return 'notstarted';
    const lowerStatus = raceStatus.toLowerCase();
    
    if (lowerStatus.includes('finish')) return 'finished';
    if (lowerStatus.includes('not start') || lowerStatus === 'not started') return 'notstarted';
    if (lowerStatus.includes('running') || lowerStatus.includes('started')) return 'running';
    if (lowerStatus.includes('withdraw')) return 'disqualified';
    if (lowerStatus.includes('disqualif')) return 'disqualified';
    
    return 'notstarted';
}


// Заполняем опции возрастных групп
function populateAgeGroups(runners) {
    const ageGroupSelect = document.getElementById('ageGroupFilter');
    const genderFilter = document.getElementById('genderFilter').value; // Получаем выбранный пол
    const savedValue = ageGroupSelect.value;
    const ageGroups = new Set();
    
    runners.forEach(runner => {
        // Для результатов используем 'category'
        if (runner.category) {
            ageGroups.add(runner.category);
        } else if (runner.age_group) {
            ageGroups.add(runner.age_group);
        } else if (runner['Возрастная категория']) {
            ageGroups.add(runner['Возрастная категория']);
        }
    });
    
    // Очищаем текущие опции
    ageGroupSelect.innerHTML = '';
    
    // Добавляем опцию "Все" первой
    const allOption = document.createElement('option');
    allOption.value = '';
    allOption.textContent = 'Все';
    ageGroupSelect.appendChild(allOption);
    
    // Фильтруем группы по выбранному полу
    let filteredGroups = Array.from(ageGroups);
    
    if (genderFilter === 'Мужчина') {
        // Показываем только мужские группы
        filteredGroups = filteredGroups.filter(group => group.startsWith('мужчины'));
    } else if (genderFilter === 'Женщина') {
        // Показываем только женские группы
        filteredGroups = filteredGroups.filter(group => group.startsWith('женщины'));
    }
    
    // Сортируем группы в правильном порядке
    const sortedGroups = filteredGroups.sort((a, b) => {
        // Если пол не выбран - женские группы в начало, потом мужские
        if (!genderFilter) {
            const aIsFemale = a.startsWith('женщины');
            const bIsFemale = b.startsWith('женщины');
            
            if (aIsFemale && !bIsFemale) return -1;
            if (!aIsFemale && bIsFemale) return 1;
        }
        
        // Определяем порядок возрастов для правильной сортировки
        const ageOrder = {
            'до 49 лет': 1,
            '50-59 лет': 2,
            '60-64 года': 3,
            '65-69 лет': 4,
            '70-74 года': 5,
            '75 лет и старше': 6,
            '65 лет и старше': 6  // для женщин после 65
        };
        
        // Извлекаем возрастной диапазон из названия группы
        let aAgeKey = '';
        let bAgeKey = '';
        
        for (let key in ageOrder) {
            if (a.includes(key)) aAgeKey = key;
            if (b.includes(key)) bAgeKey = key;
        }
        
        const aOrder = ageOrder[aAgeKey] || 99;
        const bOrder = ageOrder[bAgeKey] || 99;
        
        return aOrder - bOrder;
    });
    
    sortedGroups.forEach(group => {
        const option = document.createElement('option');
        option.value = group;
        option.textContent = group;
        ageGroupSelect.appendChild(option);
    });
    
    // Восстанавливаем сохраненное значение, если оно еще доступно
    if (savedValue && Array.from(ageGroupSelect.options).some(opt => opt.value === savedValue)) {
        ageGroupSelect.value = savedValue;
    } else {
        // Если выбранное значение больше не доступно, выбираем "Все"
        ageGroupSelect.value = '';
    }
}

// Заполняем опции дистанций
function populateDistances(runners) {
    const distanceSelect = document.getElementById('distanceFilter');
    const savedValue = distanceSelect.value; // Сохраняем текущее выбранное значение
    const distances = new Set();
    
    runners.forEach(runner => {
        let distance = null;
        // Проверяем возможные названия полей для дистанции
        if (runner.event) {
            distance = runner.event;
        } else if (runner.distance) {
            distance = runner.distance;
        }
        if (distance) {
            distances.add(distance);
        }
    });
    
    // Очищаем текущие опции
    distanceSelect.innerHTML = '';
    
    // Добавляем опцию "Все" первой
    const allOption = document.createElement('option');
    allOption.value = '';
    allOption.textContent = 'Все';
    distanceSelect.appendChild(allOption);
    
    // Сортируем дистанции по возрастанию
    const sortedDistances = Array.from(distances).sort((a, b) => {
        // Извлекаем числовое значение для сортировки
        const numA = parseInt(a) || 0;
        const numB = parseInt(b) || 0;
        if (numA !== numB) {
            return numA - numB;
        }
        // Если числа одинаковые, сортируем по строке
        return a.localeCompare(b, 'ru');
    });
    
    sortedDistances.forEach(distance => {
        const option = document.createElement('option');
        option.value = distance;
        option.textContent = distance;
        distanceSelect.appendChild(option);
    });
    
    // Восстанавливаем сохраненное значение
    if (savedValue) {
        distanceSelect.value = savedValue;
    }
}

// Обработчик изменения пола - обновляет доступные возрастные группы
function onGenderChange() {
    // Пересчитываем доступные возрастные группы в зависимости от выбранного пола
    populateAgeGroups(allRunners);
    // Затем применяем все фильтры
    applyFilters();
}

// Применяем фильтры к данным
function applyFilters() {
    const genderFilter = document.getElementById('genderFilter').value;
    const ageGroupFilter = document.getElementById('ageGroupFilter').value;
    const distanceFilter = document.getElementById('distanceFilter').value;
    const surnameSearch = document.getElementById('surnameSearch').value.toLowerCase().trim();
    
    console.log('Применение фильтров:', { genderFilter, ageGroupFilter, distanceFilter, surnameSearch, totalRunners: allRunners.length });
    
    filteredRunners = allRunners.filter(runner => {
        // Фильтр по фамилии - поиск с начала фамилии
        if (surnameSearch !== '') {
            const runnerSurname = (runner.surname || '').toLowerCase();
            if (!runnerSurname.startsWith(surnameSearch)) {
                return false;
            }
        }
        
        // Ключевые данные для работы
        let runnerGender = (runner.gender || '').trim();
        
        // Фильтр по полу
        if (genderFilter !== '' && runnerGender !== genderFilter) {
            return false;
        }
        
        // Фильтр по возрастной группе
        let runnerCategory = runner.category || runner.age_group || '';
        
        if (ageGroupFilter !== '' && runnerCategory !== ageGroupFilter) {
            return false;
        }
        
        // Фильтр по дистанции
        let runnerDistance = runner.event || '';
        
        if (distanceFilter !== '' && runnerDistance !== distanceFilter) {
            return false;
        }
        
        return true;
    });
    
    console.log(`Результат фильтрации: ${filteredRunners.length} из ${allRunners.length} участников`);
    
    // Заполняем фильтры со ВСЕМИ данными (чтобы опции не исчезали)
    populateAgeGroups(allRunners);
    populateDistances(allRunners);
    
    if (activeSegmentCode !== null) {
        document.getElementById('resultsWrapper').style.display = 'none';
        document.getElementById('segmentModeWrapper').style.display = '';
        renderSegmentView(filteredRunners);
    } else {
        document.getElementById('segmentModeWrapper').style.display = 'none';
        document.getElementById('resultsWrapper').style.display = '';
        renderResultsTable(_sortArray(filteredRunners));
    }

    // Обновляем заголовок (дистанция могла смениться)
    updatePageTitle();
}

const formatTime = KMUtils.formatTime.bind(KMUtils);
const calculatePace = KMUtils.calculatePace.bind(KMUtils);

// Применяет текущий sortState к массиву, возвращает отсортированную копию
function _sortArray(arr) {
    if (!sortState.column) return arr;
    const pri = s => s === 'finished' ? 0 : s === 'running' ? 1 : s === 'notstarted' ? 3 : 2;
    return [...arr].sort((a, b) => {
        let valA, valB;
        switch (sortState.column) {
            case 'rank':
                valA = a.rank_absolute || 9999;
                valB = b.rank_absolute || 9999;
                break;
            case 'bib':
                valA = parseInt(a.start_number) || 9999;
                valB = parseInt(b.start_number) || 9999;
                break;
            case 'name':
                valA = (`${a.surname || ''} ${a.name || ''}`).toLowerCase();
                valB = (`${b.surname || ''} ${b.name || ''}`).toLowerCase();
                break;
            case 'time_gun': {
                const pa = pri(a.status), pb = pri(b.status);
                if (pa !== pb) return pa - pb;
                valA = KMUtils.parseTimeToSeconds(a.time_gun_finish);
                valB = KMUtils.parseTimeToSeconds(b.time_gun_finish);
                if (valA === valB) return (a.surname || '').localeCompare(b.surname || '', 'ru');
                break;
            }
            case 'time_net': {
                const pa = pri(a.status), pb = pri(b.status);
                if (pa !== pb) return pa - pb;
                valA = KMUtils.parseTimeToSeconds(a.time_clear_finish);
                valB = KMUtils.parseTimeToSeconds(b.time_clear_finish);
                if (valA === valB) return (a.surname || '').localeCompare(b.surname || '', 'ru');
                break;
            }
            default:
                return 0;
        }
        if (valA < valB) return sortState.direction === 'asc' ? -1 : 1;
        if (valA > valB) return sortState.direction === 'asc' ? 1 : -1;
        return 0;
    });
}

// Функция сортировки таблицы
function sortTable(columnName) {
    sortState.direction = sortState.column === columnName
        ? (sortState.direction === 'asc' ? 'desc' : 'asc')
        : 'asc';
    sortState.column = columnName;
    renderResultsTable(_sortArray(filteredRunners));
}

// Отрисовываем таблицу результатов
function renderResultsTable(runners) {
    const tbody = document.getElementById('resultsTableBody');
    tbody.innerHTML = '';

    runners.forEach((runner, index) => {
        const row = document.createElement('tr');

        const rankAbs = runner.rank_absolute;
        const rankClass = rankAbs === 1 ? 'rank-gold' : rankAbs === 2 ? 'rank-silver' : rankAbs === 3 ? 'rank-bronze' : '';
        const rankDisplay = rankAbs ? `<span class="rank-abs ${rankClass}">${rankAbs}</span>` : '—';

        const fullName = `${runner.surname || ''} ${runner.name || ''}`.trim() || 'N/A';
        const timeGun = formatTime(runner.time_gun_finish) || '—';
        const timeNet = formatTime(runner.time_clear_finish) || '—';

        row.innerHTML = `
            <td class="rank-col">${rankDisplay}</td>
            <td>${runner.start_number || ''}</td>
            <td>${fullName}</td>
            <td class="time-cell">${timeGun}</td>
            <td class="time-cell">${timeNet}</td>
        `;

        const resultId = String(runner.id || '');
        row.dataset.resultId = resultId;
        row.classList.add('runner-row');

        if (resultId) {
            runnerDataMap.set(resultId, runner);
            row.addEventListener('click', function() {
                openDetailPanel(this, resultId);
            });
        }

        tbody.appendChild(row);
    });
}

// Показываем индикатор загрузки
function showLoading(show) {
    document.getElementById('loadingIndicator').style.display = show ? 'block' : 'none';
    document.getElementById('errorIndicator').style.display = 'none';
}

// Показываем ошибку
function showError(message) {
    document.getElementById('errorIndicator').textContent = message;
    document.getElementById('errorIndicator').style.display = 'block';
}

// ============================================================
// ФУНКЦИИ ДЛЯ РАБОТЫ С РАСКРЫВАЮЩЕЙСЯ ОБЛАСТЬЮ СЕГМЕНТОВ
// ============================================================

/**
 * Переименование кода сегмента в читаемый формат
 */
function formatSegmentName(code) {
    if (!code) return '-';
    
    const names = {
        'start': 'Старт',
        'kt1': 'КТ1',
        'kt2': 'КТ2',
        'kt3': 'КТ3',
        'kt4': 'КТ4',
        'kt5': 'КТ5',
        'kt6': 'КТ6',
        'kt7': 'КТ7',
        'finish': 'Финиш'
    };
    
    // Парсим код типа "start-kt1" или "kt1-finish"
    const parts = code.split('-');
    return parts.map(part => names[part] || part).join(' → ');
}

/**
 * Получает иконку для сегмента
 */
function getSegmentIcon(code) {
    const icons = {
        'start': '🏁',
        'kt1': '🏃',
        'kt2': '🏃',
        'kt3': '🏃',
        'kt4': '🏃',
        'kt5': '🏃',
        'kt6': '🏃',
        'kt7': '🏃',
        'finish': '🎯'
    };
    
    const mainPart = code.split('-')[0];
    return icons[mainPart] || '⚡';
}

/**
 * Получает цвет позиции (для фона кружка)
 */
function getRankColor(rank) {
    if (!rank || rank === '-') return 'var(--primary-color)';
    
    const rankNum = parseInt(rank);
    switch(rankNum) {
        case 1: return '#FFD700'; // золото
        case 2: return '#C0C0C0'; // серебро
        case 3: return '#CD7F32'; // бронза
        default: return 'var(--primary-color)';
    }
}

/**
 * Сравнивает темп между двумя сегментами
 * Возвращает объект с направлением и процентом изменения
 */
function compareSegments(currentPace, previousPace) {
    if (!currentPace || !previousPace || currentPace === '-' || previousPace === '-') {
        return null;
    }
    
    // Парсим темп (формат "08:38 мин/км" или "08:38")
    const parseMinutes = (paceStr) => {
        if (typeof paceStr !== 'string') return null;
        const match = paceStr.match(/(\d+):(\d+)/);
        if (!match) return null;
        return parseInt(match[1]) + parseInt(match[2]) / 60;
    };
    
    const current = parseMinutes(currentPace);
    const previous = parseMinutes(previousPace);
    
    if (current === null || previous === null) return null;
    
    const diff = current - previous; // отрицательное = улучшение
    const percent = Math.abs((diff / previous) * 100).toFixed(1);
    const isImproved = diff < 0;
    
    return {
        improved: isImproved,
        percent: percent,
        direction: isImproved ? '↓' : '↑'
    };
}

/**
 * Открывает/закрывает детальную панель под строкой участника
 */
async function openDetailPanel(runnerRow, resultId) {
    const existing = runnerRow.nextElementSibling;
    if (existing && existing.classList.contains('detail-panel-row')) {
        existing.remove();
        runnerRow.classList.remove('row-active');
        return;
    }
    // Закрываем все другие открытые панели
    document.querySelectorAll('.detail-panel-row').forEach(r => r.remove());
    document.querySelectorAll('.row-active').forEach(r => r.classList.remove('row-active'));
    runnerRow.classList.add('row-active');

    const runner = runnerDataMap.get(resultId);
    const panelRow = document.createElement('tr');
    panelRow.classList.add('detail-panel-row');
    const cell = document.createElement('td');
    cell.colSpan = 5;
    cell.innerHTML = buildDetailPanelHTML(runner);
    panelRow.appendChild(cell);
    runnerRow.insertAdjacentElement('afterend', panelRow);

    cell.querySelector('.detail-panel-close').addEventListener('click', e => {
        e.stopPropagation();
        panelRow.remove();
        runnerRow.classList.remove('row-active');
    });

    loadSegmentsIntoPanel(cell, resultId);
}

/**
 * Строит HTML детальной панели из данных участника
 */
function buildDetailPanelHTML(runner) {
    if (!runner) return '<div style="padding:16px;color:#aaa">Нет данных</div>';

    const fullName = `${runner.surname || ''} ${runner.name || ''}`.trim();
    const genderShort = runner.gender === 'Мужчина' ? 'М' : runner.gender === 'Женщина' ? 'Ж' : '';
    const category = runner.category || '';
    const distance = runner.event || runner.distance || '';
    let birthYear = '';
    if (runner.birthdate) {
        const y = new Date(runner.birthdate).getFullYear();
        if (y > 0) birthYear = y;
    }
    const metaParts = [distance, genderShort, birthYear ? `${birthYear} г.р.` : ''].filter(Boolean);

    const timeGun = formatTime(runner.time_gun_finish) || '—';
    const timeNet = formatTime(runner.time_clear_finish) || '—';
    const paceGunRaw = KMUtils.parseDuration(runner.finish_pace_avg_gun || runner.finish_pace_avg);
    const paceNetRaw = KMUtils.parseDuration(runner.finish_pace_avg_clean || runner.finish_pace_avg);
    const paceGun = (paceGunRaw && paceGunRaw !== '#ЗНАЧ!') ? paceGunRaw + ' мин/км' : '—';
    const paceNet = (paceNetRaw && paceNetRaw !== '#ЗНАЧ!') ? paceNetRaw + ' мин/км' : '—';

    const rankAbs = runner.rank_absolute || '—';
    const rankSex = runner.rank_sex ? `${genderShort} #${runner.rank_sex}` : '—';
    const rankCat = runner.rank_category ? `#${runner.rank_category}` : '—';
    const rankAbsClean = runner.rank_absolute_clean || '—';
    const rankSexClean = runner.rank_sex_clean ? `${genderShort} #${runner.rank_sex_clean}` : '—';
    const rankCatClean = runner.rank_category_clean ? `#${runner.rank_category_clean}` : '—';

    const statusMap = { finished: 'Финишировал', running: 'Бежит', notstarted: 'Не стартовал', disqualified: 'Нарушение' };
    const status = statusMap[runner.status] || runner.status || '—';

    return `
    <div class="detail-panel-header">
        <div>
            <div class="detail-panel-name">${fullName}</div>
            <div class="detail-panel-meta">${metaParts.join(' · ')} · ${status}</div>
        </div>
        <button class="detail-panel-close" title="Закрыть">&times;</button>
    </div>
    <div class="detail-stats-grid">
        <div class="detail-stat-block">
            <h4>Официальные результаты</h4>
            <div class="detail-stat-row"><span class="detail-stat-label">Место</span><span class="detail-stat-value">${rankAbs}</span></div>
            <div class="detail-stat-row"><span class="detail-stat-label">Место по полу</span><span class="detail-stat-value">${rankSex}</span></div>
            <div class="detail-stat-row"><span class="detail-stat-label">Место в категории</span><span class="detail-stat-value">${rankCat} ${category}</span></div>
            <div class="detail-stat-row"><span class="detail-stat-label">Время</span><span class="detail-stat-value">${timeGun}</span></div>
            <div class="detail-stat-row"><span class="detail-stat-label">Темп</span><span class="detail-stat-value">${paceGun}</span></div>
        </div>
        <div class="detail-stat-block">
            <h4>Чистые результаты</h4>
            <div class="detail-stat-row"><span class="detail-stat-label">Место</span><span class="detail-stat-value">${rankAbsClean}</span></div>
            <div class="detail-stat-row"><span class="detail-stat-label">Место по полу</span><span class="detail-stat-value">${rankSexClean}</span></div>
            <div class="detail-stat-row"><span class="detail-stat-label">Место в категории</span><span class="detail-stat-value">${rankCatClean} ${category}</span></div>
            <div class="detail-stat-row"><span class="detail-stat-label">Время</span><span class="detail-stat-value">${timeNet}</span></div>
            <div class="detail-stat-row"><span class="detail-stat-label">Темп</span><span class="detail-stat-value">${paceNet}</span></div>
        </div>
    </div>
    <div class="detail-segments-title">Время по контрольным точкам</div>
    <div class="detail-segments-loading segments-placeholder">Загрузка...</div>
    `;
}

/**
 * Загружает сегменты и вставляет таблицу вместо заглушки
 */
async function loadSegmentsIntoPanel(cell, resultId) {
    const placeholder = cell.querySelector('.segments-placeholder');
    try {
        const resp = await fetch(`/api/result-segments?result_id=${resultId}`);
        if (!resp.ok) throw new Error(`Ошибка сервера: ${resp.status}`);
        const segments = await resp.json();
        if (placeholder) placeholder.remove();
        if (!segments.length) {
            cell.insertAdjacentHTML('beforeend', '<div style="color:#aaa;font-size:13px;padding:8px 0">Данные КТ не найдены</div>');
            return;
        }
        cell.appendChild(createSegmentsTable(segments));
    } catch (e) {
        if (placeholder) placeholder.textContent = `Ошибка загрузки КТ: ${e.message}`;
    }
}

/**
 * Создаёт карточку с диаграммой для одного сегмента
 */
function formatSegmentPace(paceStr) {
    if (!paceStr || paceStr === '-') return '-';
    // PT format: PT5M46S → "5:46 мин/км"
    if (typeof paceStr === 'string' && paceStr.startsWith('PT')) {
        const m = paceStr.match(/PT(?:(\d+)H)?(?:(\d+)M)?(?:(\d+(?:\.\d+)?)S)?/);
        if (m) {
            const min = (parseInt(m[1] || 0) * 60) + parseInt(m[2] || 0);
            const sec = Math.floor(parseFloat(m[3] || 0));
            return `${min}:${sec.toString().padStart(2, '0')} мин/км`;
        }
    }
    // HH:MM:SS format: 00:05:46 → "5:46 мин/км"
    const parts = paceStr.split(':');
    if (parts.length === 3) {
        const min = parseInt(parts[0]) * 60 + parseInt(parts[1]);
        const sec = parseInt(parts[2]);
        return `${min}:${sec.toString().padStart(2, '0')} мин/км`;
    }
    return paceStr;
}

function calcSegmentDistanceKm(timeStr, paceStr) {
    if (!timeStr || !paceStr || timeStr === '-' || paceStr === '-') return null;
    const tParts = timeStr.split(':');
    if (tParts.length !== 3) return null;
    const timeSec = parseInt(tParts[0]) * 3600 + parseInt(tParts[1]) * 60 + parseInt(tParts[2]);
    const paceMatch = paceStr.match(/(\d+):(\d+)/);
    if (!paceMatch) return null;
    const paceSec = parseInt(paceMatch[1]) * 60 + parseInt(paceMatch[2]);
    if (paceSec === 0) return null;
    return Math.round(timeSec / paceSec * 10) / 10;
}

/**
 * Разбирает сегментный код "start-kt1" → {from: 'start', to: 'kt1'}
 */
function parseSegmentCode(code) {
    const idx = code.lastIndexOf('-');
    return { from: code.slice(0, idx), to: code.slice(idx + 1) };
}

/**
 * Строит карту { 'start': 0, 'kt1': 3.0, 'kt2': 5.3, ..., 'finish': 21.1 }
 * из сегментов с from='start'. Вычисляет to_km = time_sec / pace_sec_per_km.
 * Если данных нет — ключ отсутствует.
 */
function buildKmMap(segments) {
    const map = { start: 0 };
    for (const seg of segments) {
        const { from, to } = parseSegmentCode(seg.segment_code);
        if (from !== 'start') continue;
        const timeStr = seg.sg_time_clear || seg.sg_time_gun;
        const paceStr = seg.sg_pace_avg || seg.sg_pace_avg_gun;
        if (!timeStr || !paceStr) continue;

        // "HH:MM:SS" → seconds
        const tParts = timeStr.split(':').map(Number);
        const timeSec = tParts[0] * 3600 + tParts[1] * 60 + tParts[2];

        // "M:SS" → seconds/km
        const pParts = paceStr.split(':').map(Number);
        const paceSec = pParts[0] * 60 + pParts[1];

        if (paceSec > 0) {
            map[to] = Math.round((timeSec / paceSec) * 10) / 10;
        }
    }
    return map;
}

/**
 * Линейная интерполяция зелёный→красный по ratio [0..1].
 * ratio=0 → #4caf50 (быстрый), ratio=1 → #ef5350 (медленный).
 */
function paceBarColor(ratio) {
    const r = Math.round(76  + ratio * (239 - 76));
    const g = Math.round(175 + ratio * (83  - 175));
    const b = 80;
    return `rgb(${r},${g},${b})`;
}

/**
 * Возвращает последовательные отрезки: start→kt1, kt1→kt2, ..., ktN→finish.
 * Только сегменты с данными (sg_time_clear или sg_time_gun не null).
 * Результат отсортирован по порядку маршрута.
 */
function filterConsecutiveSegments(segments) {
    const KT_ORDER = ['start', 'kt1', 'kt2', 'kt3', 'kt4', 'kt5', 'kt6', 'kt7', 'finish'];
    return segments.filter(seg => {
        const { from, to } = parseSegmentCode(seg.segment_code);
        const fi = KT_ORDER.indexOf(from);
        const ti = KT_ORDER.indexOf(to);
        const isConsecutive = fi >= 0 && ti === fi + 1;
        const hasData = seg.sg_time_clear || seg.sg_time_gun;
        return isConsecutive && hasData;
    }).sort((a, b) => {
        const ai = KT_ORDER.indexOf(parseSegmentCode(a.segment_code).from);
        const bi = KT_ORDER.indexOf(parseSegmentCode(b.segment_code).from);
        return ai - bi;
    });
}

/**
 * Возвращает сплиты от старта: start→kt1, start→kt2, ..., start→finish.
 * Только сегменты с данными. Отсортированы по to_km (по to в KT_ORDER).
 */
function filterSplitSegments(segments) {
    const KT_ORDER = ['start', 'kt1', 'kt2', 'kt3', 'kt4', 'kt5', 'kt6', 'kt7', 'finish'];
    return segments.filter(seg => {
        const { from } = parseSegmentCode(seg.segment_code);
        const hasData = seg.sg_time_clear || seg.sg_time_gun;
        return from === 'start' && hasData;
    }).sort((a, b) => {
        const ai = KT_ORDER.indexOf(parseSegmentCode(a.segment_code).to);
        const bi = KT_ORDER.indexOf(parseSegmentCode(b.segment_code).to);
        return ai - bi;
    });
}

function createSegmentsTable(segments) {
    const useGun = timeMode === 'gun';
    const modeLabel = useGun ? 'офиц.' : 'чист.';

    const table = document.createElement('table');
    table.classList.add('segments-table');

    table.innerHTML = `
        <colgroup>
            <col width="30%"/><col width="18%"/><col width="24%"/>
            <col width="9%"/><col width="9%"/><col width="9%"/>
        </colgroup>
        <thead>
            <tr>
                <th>Участок</th>
                <th>Время <span class="seg-mode-label">${modeLabel}</span></th>
                <th>Темп</th>
                <th title="Место абсолют">Абс.</th>
                <th title="Место по полу">Пол</th>
                <th title="Место в категории">Кат.</th>
            </tr>
        </thead>
    `;

    const tbody = document.createElement('tbody');
    segments.forEach((segment, i) => {
        const prevSegment = i > 0 ? segments[i - 1] : null;
        const code = segment.segment_code || '-';
        const time = formatTime(useGun ? (segment.sg_time_gun || segment.sg_time_clear) : segment.sg_time_clear) || '-';
        const pace = formatSegmentPace(useGun ? (segment.sg_pace_avg_gun || segment.sg_pace_avg) : segment.sg_pace_avg);
        const rankAbsolute = useGun ? (segment.sg_rank_absolute_gun || segment.sg_rank_absolute || '-') : (segment.sg_rank_absolute || '-');
        const rankSex = useGun ? (segment.sg_rank_sex_gun || segment.sg_rank_sex || '-') : (segment.sg_rank_sex || '-');
        const rankCategory = useGun ? (segment.sg_rank_category_gun || segment.sg_rank_category || '-') : (segment.sg_rank_category || '-');

        let paceHtml = pace;
        if (prevSegment) {
            const prevPace = formatSegmentPace(useGun ? (prevSegment.sg_pace_avg_gun || prevSegment.sg_pace_avg) : prevSegment.sg_pace_avg);
            const cmp = compareSegments(pace, prevPace);
            if (cmp) {
                const color = cmp.improved ? '#27ae60' : '#e74c3c';
                paceHtml += ` <span style="color:${color};font-size:0.85em">${cmp.direction}${cmp.percent}%</span>`;
            }
        }

        const rankBadge = (rank) => {
            const color = getRankColor(rank);
            return `<span class="seg-rank-badge" style="background:${color}">${rank}</span>`;
        };

        const tr = document.createElement('tr');
        tr.innerHTML = `
            <td class="seg-name">${formatSegmentName(code)}</td>
            <td class="seg-time">${time}</td>
            <td class="seg-pace">${paceHtml}</td>
            <td class="seg-rank">${rankBadge(rankAbsolute)}</td>
            <td class="seg-rank">${rankBadge(rankSex)}</td>
            <td class="seg-rank">${rankBadge(rankCategory)}</td>
        `;
        tbody.appendChild(tr);
    });

    table.appendChild(tbody);
    return table;
}

// === Результаты по участкам (КТ) ===

async function loadSegmentTabs(eventId) {
    try {
        const resp = await fetch(`/api/event-segment-codes?event_id=${eventId}`);
        if (!resp.ok) return;
        const { codes } = await resp.json();
        if (!codes || !codes.length) return;

        activeSegmentEventId = eventId;
        segmentRankingsCache = {};

        const container = document.getElementById('segmentTabsContainer');
        container.innerHTML = '';

        // Кнопка «Все результаты»
        const allBtn = document.createElement('button');
        allBtn.className = 'segment-tab-btn active';
        allBtn.textContent = 'Все результаты';
        allBtn.onclick = () => setActiveSegment(null, allBtn);
        container.appendChild(allBtn);

        codes.forEach(code => {
            const btn = document.createElement('button');
            btn.className = 'segment-tab-btn';
            btn.textContent = formatSegmentName(code);
            btn.dataset.code = code;
            btn.onclick = () => setActiveSegment(code, btn);
            container.appendChild(btn);
        });

        container.style.display = '';
    } catch (e) {
        console.error('❌ loadSegmentTabs:', e);
    }
}

function setActiveSegment(code, activeBtn) {
    activeSegmentCode = code;
    document.querySelectorAll('#segmentTabsContainer .segment-tab-btn')
        .forEach(b => b.classList.remove('active'));
    activeBtn.classList.add('active');
    applyFilters();
}

async function renderSegmentView(runners) {
    const code = activeSegmentCode;
    const eventId = activeSegmentEventId;

    if (!segmentRankingsCache[code]) {
        try {
            const resp = await fetch(`/api/event-segment-rankings?event_id=${eventId}&segment_code=${encodeURIComponent(code)}`);
            if (!resp.ok) throw new Error(resp.statusText);
            segmentRankingsCache[code] = await resp.json();
        } catch (e) {
            console.error('renderSegmentView fetch:', e);
            document.getElementById('segmentModeBody').innerHTML =
                `<tr><td colspan="10" style="text-align:center;color:#888;">Ошибка загрузки данных</td></tr>`;
            return;
        }
    }
    const allRows = segmentRankingsCache[code];

    // Lookup map: start_number → runner (для года рождения и дистанции)
    const runnerByBib = {};
    runners.forEach(r => {
        const bib = String(r.start_number || '');
        if (bib) runnerByBib[bib] = r;
    });

    // Фильтрация: исключаем пустые строки, чтобы Set пустого состояния имел size=0
    const validBibs = new Set(
        runners.map(r => String(r.start_number || '')).filter(n => n && n !== 'null' && n !== 'undefined')
    );
    const useGun = timeMode === 'gun';

    const visible = allRows
        .filter(r => validBibs.size === 0 || validBibs.has(String(r.start_number)))
        .sort((a, b) => {
            const ta = a[useGun ? 'sg_time_gun' : 'sg_time_clear'] || '';
            const tb = b[useGun ? 'sg_time_gun' : 'sg_time_clear'] || '';
            return ta.localeCompare(tb);
        });

    // Заголовок — 10 колонок как у основной таблицы
    document.getElementById('segmentModeHead').innerHTML = `<tr>
        <th>#</th>
        <th>Фамилия</th>
        <th>Имя</th>
        <th>Год рождения</th>
        <th>Дистанция</th>
        <th>Пол</th>
        <th>Возрастная группа</th>
        <th>Статус</th>
        <th>${useGun ? 'Офиц. время' : 'Чистое время'}</th>
        <th>Темп (мин/км)</th>
    </tr>`;

    const tbody = document.getElementById('segmentModeBody');
    tbody.innerHTML = '';

    if (!visible.length) {
        tbody.innerHTML = `<tr><td colspan="10" style="text-align:center;color:#888;">Нет данных для выбранных фильтров</td></tr>`;
        return;
    }

    visible.forEach((row, idx) => {
        const bib = String(row.start_number || '');
        const runner = runnerByBib[bib] || {};

        // Год рождения из основных данных
        let birthYear = '-';
        if (runner.birthdate) {
            const year = new Date(runner.birthdate).getFullYear();
            if (year > 0) birthYear = year;
        }

        // Дистанция из основных данных
        const distance = runner.event || runner.distance || '-';

        // Пол с тегом
        const sexVal = row.sex || runner.gender || '';
        let genderClass = '';
        let genderText = sexVal || 'N/A';
        if (sexVal === 'Мужчина' || sexVal === 'male') { genderClass = 'gender-male'; genderText = 'Мужчина'; }
        else if (sexVal === 'Женщина' || sexVal === 'female') { genderClass = 'gender-female'; genderText = 'Женщина'; }

        // Нормализуем категорию
        const category = KMUtils.normalizeCategory(row.category || '');

        const rawTime = useGun ? (row.sg_time_gun || row.sg_time_clear) : row.sg_time_clear;
        const rawPace = useGun ? (row.sg_pace_avg_gun || row.sg_pace_avg) : row.sg_pace_avg;
        const pace = rawPace ? formatSegmentPace(rawPace) : '-';

        const tr = document.createElement('tr');
        tr.className = 'runner-row';
        if (row.result_id) tr.dataset.resultId = row.result_id;
        tr.innerHTML = `
            <td>${row.start_number || idx + 1}</td>
            <td>${row.surname || ''}</td>
            <td>${row.name || ''}</td>
            <td>${birthYear}</td>
            <td class="distance-col">${distance}</td>
            <td><span class="gender-tag ${genderClass}">${genderText}</span></td>
            <td>${category}</td>
            <td class="status-finished status-col">Финишировал</td>
            <td class="time-cell time-col">${formatTime(rawTime) || '-'}</td>
            <td class="pace-cell pace-col">${pace}</td>
        `;
        if (row.result_id) {
            tr.addEventListener('click', function() {
                openDetailPanel(this, String(row.result_id));
            });
        }
        tbody.appendChild(tr);
    });
}
