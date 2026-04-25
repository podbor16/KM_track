// legacy/static/analytics-results.js
// Javascript для страницы результатов забега
let allRunners = [];
let filteredRunners = [];
let sortState = { column: 'time', direction: 'asc' }; // Дефолт: по официальному времени
let currentEvent = 'night_run';
let currentYear = new Date().getFullYear();
let timeMode = 'gun'; // 'net' = чистое, 'gun' = официальное
let activeSegmentCode = null;
let segmentRankingsCache = {};  // { segmentCode: [rows] }
let activeSegmentEventId = null;

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
    'snow7_2026': 119
};

// Инициализация страницы — дефолт: активный забег + прошлый год
document.addEventListener('DOMContentLoaded', async function() {
    populateYearSelector();
    try {
        const cfg = await fetch('/api/current-event').then(r => r.json());
        currentEvent = cfg.event || 'night_run';
        currentYear  = (cfg.year || new Date().getFullYear()) - 1;
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

function setTimeMode(mode) {
    timeMode = mode;
    const btnNet = document.getElementById('btnNet');
    const btnGun = document.getElementById('btnGun');
    if (btnNet) btnNet.classList.toggle('active', mode === 'net');
    if (btnGun) btnGun.classList.toggle('active', mode === 'gun');
    const th = document.querySelector('#resultsTable thead tr th:nth-child(9)');
    if (th) th.textContent = mode === 'gun' ? 'Офиц. время' : 'Чистое время';
    if (activeSegmentCode !== null) {
        renderSegmentView(filteredRunners);
    } else {
        renderResultsTable(_sortArray(filteredRunners));
    }
}

// Функция обновления фонового изображения карточки события
function updateEventCardBackground() {
    const eventCard = document.getElementById('eventCard');
    const eventDisplayName = eventNameMap[currentEvent];
    const imageUrl = `/static/images/events/${encodeURIComponent(eventDisplayName)}.png`;
    eventCard.style.backgroundImage = `url('${imageUrl}')`;
}

// Функция загрузки данных
async function loadRunnersData() {
    console.log(`Загрузка данных для результатов: ${currentEvent} ${currentYear}`);
    allRunners = [];
    filteredRunners = [];
    document.getElementById('resultsTableBody').innerHTML = '';
    document.getElementById('resultsWrapper').style.display = 'none';
    showLoading(true);

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
        showLoading(false);
        document.getElementById('resultsWrapper').style.display = '';

        // Загружаем кнопки КТ для одиночного event_id
        if (eventIdOrIds !== undefined && !Array.isArray(eventIdOrIds)) {
            loadSegmentTabs(eventIdOrIds);
        }
    } catch (error) {
        console.error('❌ Ошибка загрузки данных:', error);
        showError('Ошибка загрузки данных: ' + error.message);
        showLoading(false);
        document.getElementById('resultsWrapper').style.display = '';
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
            
            // Место и ранк
            rank_absolute: runner.rank_absolute,
            rank_sex: runner.rank_sex,
            rank_category: runner.rank_category,
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
    return [...arr].sort((a, b) => {
        let valA, valB;
        switch (sortState.column) {
            case 'surname':
                valA = (a.surname || '').toLowerCase();
                valB = (b.surname || '').toLowerCase();
                break;
            case 'name':
                valA = (a.name || '').toLowerCase();
                valB = (b.name || '').toLowerCase();
                break;
            case 'birthdate':
                valA = a.birthdate ? new Date(a.birthdate).getFullYear() : 0;
                valB = b.birthdate ? new Date(b.birthdate).getFullYear() : 0;
                break;
            case 'event':
                valA = KMUtils.parseDistanceKm(a.event || a.distance);
                valB = KMUtils.parseDistanceKm(b.event || b.distance);
                break;
            case 'gender':
                valA = (a.gender || '').toLowerCase();
                valB = (b.gender || '').toLowerCase();
                break;
            case 'category':
                valA = KMUtils.categoryOrder(a.category);
                valB = KMUtils.categoryOrder(b.category);
                break;
            case 'status':
                valA = (a.status || '').toLowerCase();
                valB = (b.status || '').toLowerCase();
                break;
            case 'time': {
                // Статус-приоритет: finished=0, running=1, прочие=2, notstarted=3
                const pri = s => s === 'finished' ? 0 : s === 'running' ? 1 : s === 'notstarted' ? 3 : 2;
                const pa = pri(a.status), pb = pri(b.status);
                if (pa !== pb) return pa - pb; // статусный порядок фиксирован независимо от направления
                const fa = timeMode === 'gun' ? a.time_gun_finish : a.time_clear_finish;
                const fb = timeMode === 'gun' ? b.time_gun_finish : b.time_clear_finish;
                valA = KMUtils.parseTimeToSeconds(fa);
                valB = KMUtils.parseTimeToSeconds(fb);
                // Вторичная сортировка по фамилии при одинаковом времени (напр. все Not Started)
                if (valA === valB) return (a.surname || '').localeCompare(b.surname || '', 'ru');
                break;
            }
            case 'pace': {
                const p1 = calculatePace(a.time_clear_finish || a['times.official_:::finish:::'], a.distance || a.event);
                const p2 = calculatePace(b.time_clear_finish || b['times.official_:::finish:::'], b.distance || b.event);
                valA = p1 === '-' ? Infinity : parseFloat(p1);
                valB = p2 === '-' ? Infinity : parseFloat(p2);
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
    // Синхронизируем заголовок колонки времени
    const th = document.querySelector('#resultsTable thead tr th:nth-child(9)');
    if (th) th.textContent = timeMode === 'gun' ? 'Офиц. время' : 'Чистое время';
    
    runners.forEach((runner, index) => {
        const row = document.createElement('tr');
        
        // Год рождения
        let birthYear = '-';
        if (runner.birthdate) {
            const year = new Date(runner.birthdate).getFullYear();
            birthYear = year > 0 ? year : '-';
        }
        
        // Статус и время (поддерживаем оба формата)
        let status = '';
        let time = '';
        let statusClass = '';
        
        // Переводим статусы на русский
        let statusRu = runner.status || 'Неизвестно';
        if (runner.status === 'finished') statusRu = 'Финишировал';
        if (runner.status === 'running') statusRu = 'Бежит';
        if (runner.status === 'notstarted') statusRu = 'Не стартовал';
        if (runner.status === 'disqualified') statusRu = 'Нарушение';
        
        status = statusRu;
        statusClass = `status-${runner.status || 'unknown'}`;
        
        // Время финиша — зависит от режима тоггла
        const finishTime = timeMode === 'gun'
            ? (runner.time_gun_finish || runner.time_clear_finish)
            : (runner.time_clear_finish || runner['times.official_:::finish:::']);
        time = formatTime(finishTime);

        // Темп — зависит от режима тоггла; parseDuration конвертирует PT3M12S → "3:12"
        const rawPace = timeMode === 'gun'
            ? (runner.finish_pace_avg_gun || runner.finish_pace_avg)
            : (runner.finish_pace_avg_clean || runner.finish_pace_avg);
        const paceStr = KMUtils.parseDuration(rawPace);
        const pace = (paceStr && paceStr !== '#ЗНАЧ!') ? paceStr + ' мин/км' : '-';
        
        // Фамилия, имя, пол
        let firstName = runner.name || 'N/A';
        let lastName = runner.surname || 'N/A';
        let genderClass = '';
        let genderText = 'N/A';
        
        if (runner.gender) {
            // Теперь gender уже в правильном формате ("Мужчина"/"Женщина")
            if (runner.gender === 'Мужчина' || runner.gender === 'male') {
                genderText = 'Мужчина';
                genderClass = 'gender-male';
            } else if (runner.gender === 'Женщина' || runner.gender === 'female') {
                genderText = 'Женщина';
                genderClass = 'gender-female';
            } else {
                genderText = runner.gender;
                genderClass = '';
            }
        }
        
        // Дистанция и возрастная группа
        let distance = runner.event || runner.distance || '5 км';
        let category = runner.category || '';
        
        let rowHTML = `
            <td>${index + 1}</td>
            <td>${lastName}</td>
            <td>${firstName}</td>
            <td>${birthYear}</td>
            <td class="distance-col">${distance}</td>
            <td><span class="gender-tag ${genderClass}">${genderText}</span></td>
            <td>${category}</td>
            <td class="${statusClass} status-col">${status}</td>
            <td class="time-cell time-col">${time}</td>
            <td class="pace-cell pace-col">${pace}</td>
        `;
        
        row.innerHTML = rowHTML;
        
        // Добавляем обработчик клика и сохраняем runner.id (result_id)
        const resultId = runner.id || '';
        row.dataset.resultId = resultId;
        row.classList.add('runner-row');
        
        // Логируем для отладки
        if (resultId) {
            console.log(`✅ Строка ${index + 1} имеет result_id=${resultId}`);
        } else {
            console.warn(`⚠️ Строка ${index + 1} (${lastName} ${firstName}) не имеет result_id, runner объект:`, runner);
        }
        
        // Обработчик клика для открытия/закрытия сегментов
        row.addEventListener('click', function(e) {
            e.preventDefault();
            const rId = this.dataset.resultId;
            console.log(`🖱️ Клик по строке. resultId=${rId}`);
            if (rId) {
                toggleSegments(this, rId, `${lastName} ${firstName}`);
            } else {
                console.warn('⚠️ result_id не определён');
            }
        });
        
        tbody.appendChild(row);
    });
    
    console.log(`✅ Отрисовано ${runners.length} строк таблицы результатов`);
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
        'kt1': 'Разворот',
        'kt2': 'КТ2',
        'kt3': 'КT3',
        'kt4': 'КТ4',
        'kt5': 'КТ5',
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
        'kt1': '🔄',
        'kt2': '🏃',
        'kt3': '🏃',
        'kt4': '🏃',
        'kt5': '🏃',
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
 * Переключает видимость раскрывающейся области сегментов после строки
 */
async function toggleSegments(runnerRow, resultId, runnerName) {
    console.log(`📊 Переключение сегментов для result_id=${resultId}`);
    
    const tbody = runnerRow.parentElement;
    const nextRow = runnerRow.nextElementSibling;
    
    // Если уже есть открытая строка сегментов, закрываем все остальные
    const openSegmentsRows = tbody.querySelectorAll('.segments-row:not(.collapsed)');
    if (nextRow && nextRow.classList.contains('segments-row')) {
        // Это наш ряд, просто переключаем его
        if (nextRow.classList.contains('collapsed')) {
            nextRow.classList.remove('collapsed');
        } else {
            nextRow.classList.add('collapsed');
        }
    } else {
        // Закрываем все открытые ряды
        openSegmentsRows.forEach(row => {
            row.classList.add('collapsed');
        });
        
        // Если это была та же строка, просто закрываем и выходим
        if (nextRow && nextRow.classList.contains('segments-row') && nextRow.classList.contains('collapsed')) {
            return;
        }
        
        // Создаём новую строку с сегментами
        const newSegmentsRow = await createSegmentsRow(resultId, runnerName);
        runnerRow.insertAdjacentElement('afterend', newSegmentsRow);
    }
}

/**
 * Создаёт HTML строку с сегментами (диаграммами)
 */
async function createSegmentsRow(resultId, runnerName) {
    const row = document.createElement('tr');
    row.classList.add('segments-row');
    
    const cell = document.createElement('td');
    cell.colSpan = 10;
    
    const wrapper = document.createElement('div');
    wrapper.classList.add('segments-content-wrapper');
    
    // Показываем индикатор загрузки
    const loading = document.createElement('div');
    loading.classList.add('segments-loading');
    loading.textContent = 'Загрузка данных сегментов...';
    wrapper.appendChild(loading);
    
    cell.appendChild(wrapper);
    row.appendChild(cell);
    
    // Загружаем данные сегментов
    try {
        const response = await fetch(`/api/result-segments?result_id=${resultId}`);
        
        if (!response.ok) {
            throw new Error(`Ошибка сервера: ${response.status}`);
        }
        
        const segments = await response.json();
        console.log(`✅ Получено ${segments.length} сегментов для result_id=${resultId}`, segments);
        
        // Удаляем индикатор загрузки
        loading.remove();
        
        if (segments.length === 0) {
            const error = document.createElement('div');
            error.classList.add('segments-error');
            error.textContent = 'Данные сегментов не найдены';
            wrapper.appendChild(error);
            return row;
        }
        
        // Создаём сетку со статистикой сегментов
        const grid = document.createElement('div');
        grid.classList.add('segments-grid');
        
        segments.forEach((segment, index) => {
            const card = createSegmentCard(segment, segments, index);
            grid.appendChild(card);
        });
        
        wrapper.appendChild(grid);
        
    } catch (error) {
        console.error('❌ Ошибка загрузки сегментов:', error);
        loading.remove();
        const errorDiv = document.createElement('div');
        errorDiv.classList.add('segments-error');
        errorDiv.textContent = `Ошибка загрузки: ${error.message}`;
        wrapper.appendChild(errorDiv);
    }
    
    return row;
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

function createSegmentCard(segment, allSegments, segmentIndex) {
    const card = document.createElement('div');
    card.classList.add('segment-card');

    const segmentCode = segment.segment_code || '-';
    const useGun = timeMode === 'gun';
    const time = formatTime(useGun ? (segment.sg_time_gun || segment.sg_time_clear) : segment.sg_time_clear) || '-';
    const pace = formatSegmentPace(
        useGun ? (segment.sg_pace_avg_gun || segment.sg_pace_avg) : segment.sg_pace_avg
    );
    const rankAbsolute = useGun
        ? (segment.sg_rank_absolute_gun || segment.sg_rank_absolute || '-')
        : (segment.sg_rank_absolute || '-');
    const rankSex = useGun
        ? (segment.sg_rank_sex_gun || segment.sg_rank_sex || '-')
        : (segment.sg_rank_sex || '-');
    const rankCategory = useGun
        ? (segment.sg_rank_category_gun || segment.sg_rank_category || '-')
        : (segment.sg_rank_category || '-');

    const icon = getSegmentIcon(segmentCode);
    const name = formatSegmentName(segmentCode);
    const modeBadge = `<span class="segment-mode-badge">${useGun ? 'офиц.' : 'чист.'}</span>`;

    // Сравниваем с предыдущим сегментом
    let paceComparison = '';
    if (segmentIndex > 0) {
        const prevSegment = allSegments[segmentIndex - 1];
        const prevPace = formatSegmentPace(
            useGun ? (prevSegment.sg_pace_avg_gun || prevSegment.sg_pace_avg) : prevSegment.sg_pace_avg
        );
        const comparison = compareSegments(pace, prevPace);
        if (comparison) {
            const color = comparison.improved ? '#27ae60' : '#e74c3c';
            paceComparison = `
                <div class="pace-comparison" style="color: ${color};">
                    ${comparison.direction} ${comparison.percent}%
                </div>
            `;
        }
    }
    
    // Цвета для медалей
    const colorAbsolute = getRankColor(rankAbsolute);
    const colorSex = getRankColor(rankSex);
    const colorCategory = getRankColor(rankCategory);
    
    card.innerHTML = `
        <div class="segment-card-title">
            <span class="segment-icon">${icon}</span>
            <span>${name}</span>
            ${modeBadge}
        </div>
        
        <div class="segment-info-row">
            <span class="segment-distance">📏 2,5 км</span>
        </div>
        
        <div class="segment-stat">
            <span class="segment-stat-label">⏱️ Время</span>
            <span class="segment-time">${time}</span>
        </div>
        
        <div class="segment-stat">
            <div>
                <span class="segment-stat-label">🏃 Темп</span>
                <span class="segment-stat-value">${pace}</span>
            </div>
            ${paceComparison}
        </div>
        
        <div class="segment-stat">
            <span class="segment-stat-label">🏆 В абсолюте</span>
            <div class="rank-container">
                <div class="segment-rank" style="background-color: ${colorAbsolute};"> ${rankAbsolute}</div>
                <div class="segment-rank-label">место</div>
            </div>
        </div>
        
        <div class="segment-stat">
            <span class="segment-stat-label">♀♂ По полу</span>
            <div class="rank-container">
                <div class="segment-rank" style="width: 28px; height: 28px; font-size: 12px; background-color: ${colorSex};"> ${rankSex}</div>
                <div class="segment-rank-label">место</div>
            </div>
        </div>
        
        <div class="segment-stat">
            <span class="segment-stat-label">🎂 По категории</span>
            <div class="rank-container">
                <div class="segment-rank" style="width: 28px; height: 28px; font-size: 12px; background-color: ${colorCategory};"> ${rankCategory}</div>
                <div class="segment-rank-label">место</div>
            </div>
        </div>
    `;
    
    return card;
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
            console.error('❌ renderSegmentView fetch:', e);
            document.getElementById('segmentModeBody').innerHTML =
                `<tr><td colspan="11" style="text-align:center;color:#888;">Ошибка загрузки данных</td></tr>`;
            return;
        }
    }
    const allRows = segmentRankingsCache[code];

    // Фильтрация по filteredRunners через start_number
    const filteredNums = new Set(runners.map(r => String(r.start_number || r.bib || '')));
    const useGun = timeMode === 'gun';

    const visible = allRows
        .filter(r => filteredNums.size === 0 || filteredNums.has(String(r.start_number)))
        .sort((a, b) => {
            const ta = a[useGun ? 'sg_time_gun' : 'sg_time_clear'] || '';
            const tb = b[useGun ? 'sg_time_gun' : 'sg_time_clear'] || '';
            return ta.localeCompare(tb);
        });

    // Заголовок таблицы
    document.getElementById('segmentModeHead').innerHTML = `<tr>
        <th>#</th><th>№</th><th>Фамилия</th><th>Имя</th>
        <th>Пол</th><th>Кат.</th>
        <th>${useGun ? 'Офиц. время' : 'Чистое время'}</th>
        <th>Темп</th><th>М.общ.</th><th>М.пол</th><th>М.кат.</th>
    </tr>`;

    const tbody = document.getElementById('segmentModeBody');
    tbody.innerHTML = '';

    if (!visible.length) {
        tbody.innerHTML = `<tr><td colspan="11" style="text-align:center;color:#888;">Нет данных для выбранных фильтров</td></tr>`;
        return;
    }

    visible.forEach((row, idx) => {
        const rawTime = useGun ? (row.sg_time_gun || row.sg_time_clear) : row.sg_time_clear;
        const pace = useGun ? (row.sg_pace_avg_gun || row.sg_pace_avg || '-') : (row.sg_pace_avg || '-');
        const tr = document.createElement('tr');
        tr.className = 'runner-row';
        if (row.result_id) tr.dataset.resultId = row.result_id;
        tr.innerHTML = `
            <td>${idx + 1}</td>
            <td>${row.start_number || '-'}</td>
            <td>${row.surname || ''}</td>
            <td>${row.name || ''}</td>
            <td>${row.sex || '-'}</td>
            <td>${row.category || '-'}</td>
            <td>${formatTime(rawTime) || '-'}</td>
            <td>${pace}</td>
            <td>${row.sg_rank_absolute || '-'}</td>
            <td>${row.sg_rank_sex || '-'}</td>
            <td>${row.sg_rank_category || '-'}</td>
        `;
        if (row.result_id) {
            const runnerName = `${row.surname || ''} ${row.name || ''}`.trim();
            tr.addEventListener('click', function() {
                toggleSegments(this, row.result_id, runnerName);
            });
        }
        tbody.appendChild(tr);
    });
}
