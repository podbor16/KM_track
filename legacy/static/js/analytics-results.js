// legacy/static/analytics-results.js
// Javascript для страницы результатов забега
let allRunners = [];
let filteredRunners = [];
let sortState = { column: null, direction: 'asc' }; // Отслеживание сортировки
let currentEvent = 'night_run';
let currentYear = new Date().getFullYear();

const eventNameMap = {
    'night_run': 'Ночной забег',
    'vesna': 'Весна',
    'colorrun': 'Красочный забег',
    'girlseven': 'Женская семерка',
    'zhara': 'Жара',
    'kids': 'Детский забег',
    'xtrailrun': 'Х Трейл',
    'snow7': 'Снежная семерка'
};

// Цвета для каждого события
const eventColorMap = {
    'night_run': '#1c2c55',
    'vesna': '#85c6e2',
    'colorrun': '#059C43',
    'girlseven': '#f072ab',
    'zhara': '#ee2d62',
    'kids': '#ee2d62',
    'xtrailrun': '#562872',
    'snow7': '#00BFDF'
};

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

// Инициализация страницы
document.addEventListener('DOMContentLoaded', function() {
    populateYearSelector();           // Сначала заполняем селектор годов
    restoreSavedPreferences();        // Потом восстанавливаем сохраненные значения
    updateEventThemeColor();          // Обновляем цвет темы
    loadRunnersData();                // Загружаем данные
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
    
    // Сохраняем выбор в localStorage
    localStorage.setItem('selectedEventResults', currentEvent);
    localStorage.setItem('selectedYearResults', currentYear);
    
    // Обновляем цвет темы
    updateEventThemeColor();
    
    // Меняем фоновую картинку карточки события
    updateEventCardBackground();
    
    // Перезагружаем данные
    loadRunnersData();
}

// Функция обновления фонового изображения карточки события
function updateEventCardBackground() {
    const eventCard = document.getElementById('eventCard');
    const eventDisplayName = eventNameMap[currentEvent];
    const imageUrl = `/legacy/static/images/events/${encodeURIComponent(eventDisplayName)}.png`;
    eventCard.style.backgroundImage = `url('${imageUrl}')`;
}

// Функция загрузки данных
async function loadRunnersData() {
    console.log(`Загрузка данных для результатов: ${currentEvent} ${currentYear}`);
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
    } catch (error) {
        console.error('❌ Ошибка загрузки данных:', error);
        showError('Ошибка загрузки данных: ' + error.message);
        showLoading(false);
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
            // Основная информация
            surname: runner.surname || '',
            name: runner.name || '',
            full_name: runner.full_name || `${runner.surname || ''} ${runner.name || ''}`,
            birthdate: runner.birthday || runner.birthdate || '',
            gender: convertSexToGender(runner.sex),  // Будет "Мужчина" или "Женщина"
            sex: runner.sex,
            category: runner.category || '',
            
            // Статус и результаты
            status: convertRaceStatus(runner.race_status),
            race_status: runner.race_status,
            
            // Время и темп
            'times.official_:::finish:::': runner.time_clear_finish,
            time_clear_finish: runner.time_clear_finish,
            finish_pace_avg: runner.finish_pace_avg,
            
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

// Восстанавливаем сохраненные значения при загрузке страницы
function restoreSavedPreferences() {
    const savedEvent = localStorage.getItem('selectedEventResults');
    const savedYear = localStorage.getItem('selectedYearResults');
    
    if (savedEvent) {
        currentEvent = savedEvent;
        document.getElementById('eventResultsSelector').value = currentEvent;
        updateEventCardBackground();
        updateEventThemeColor();
    }
    
    if (savedYear) {
        currentYear = parseInt(savedYear);
        document.getElementById('yearResultsSelector').value = currentYear;
    }
}

// Заполняем опции возрастных групп
function populateAgeGroups(runners) {
    const ageGroupSelect = document.getElementById('ageGroupFilter');
    const savedValue = ageGroupSelect.value; // Сохраняем текущее выбранное значение
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
    
    // Сортируем возрастные группы: <49 в начало, >75 в конец, остальные в середине
    const sortedGroups = Array.from(ageGroups).sort((a, b) => {
        // <49 должна быть первой после "Все"
        if (a === '<49') return -1;
        if (b === '<49') return 1;
        
        // >75 должна быть последней
        if (a === '>75') return 1;
        if (b === '>75') return -1;
        
        // Остальные по алфавиту/возрастанию
        return a.localeCompare(b, 'ru');
    });
    
    sortedGroups.forEach(group => {
        const option = document.createElement('option');
        option.value = group;
        option.textContent = group;
        ageGroupSelect.appendChild(option);
    });
    
    // Восстанавливаем сохраненное значение
    if (savedValue) {
        ageGroupSelect.value = savedValue;
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
    
    // Рендерим таблицу и сортируем по времени финиша по умолчанию
    sortState.column = 'time';
    sortState.direction = 'asc';
    sortTable('time');
}

// Функция для форматирования времени из миллисекунд в чч:мм:сс (поддерживает ISO 8601)
function formatTime(timeData) {
    if (!timeData) return '-';
    
    // Если это уже строка в формате HH:MM:SS, возвращаем как есть
    if (typeof timeData === 'string') {
        // Проверяем формат HH:MM:SS
        if (timeData.match(/^\d{1,2}:\d{2}:\d{2}$/)) {
            return timeData;
        }
        // Парсим ISO 8601 duration: PT1H30M45S или PT1577S => HH:MM:SS
        if (timeData.startsWith('PT')) {
            const match = timeData.match(/PT(?:(\d+)H)?(?:(\d+)M)?(?:(\d+(?:\.\d+)?)S)?/);
            if (match) {
                let hours = parseInt(match[1] || 0);
                let minutes = parseInt(match[2] || 0);
                let seconds = Math.floor(parseFloat(match[3] || 0));
                
                // Конвертируем лишние секунды в минуты и часы
                minutes += Math.floor(seconds / 60);
                seconds = seconds % 60;
                hours += Math.floor(minutes / 60);
                minutes = minutes % 60;
                
                return `${hours.toString().padStart(2, '0')}:${minutes.toString().padStart(2, '0')}:${seconds.toString().padStart(2, '0')}`;
            }
        }
        // Если строка но не в известном формате, возвращаем "-"
        return '-';
    }
    
    // Если это число (миллисекунды), преобразуем
    const totalSeconds = Math.floor(timeData / 1000);
    const hours = Math.floor(totalSeconds / 3600);
    const minutes = Math.floor((totalSeconds % 3600) / 60);
    const seconds = totalSeconds % 60;
    return `${hours.toString().padStart(2, '0')}:${minutes.toString().padStart(2, '0')}:${seconds.toString().padStart(2, '0')}`;
}

// Функция для расчета темпа (минут на км)
function calculatePace(timeData, distanceStr) {
    if (!timeData || !distanceStr) return '-';
    
    // Парсим дистанцию (например, "5 км" -> 5)
    const distanceNum = parseFloat(distanceStr);
    if (distanceNum <= 0) return '-';
    
    // Парсим время
    let totalSeconds = 0;
    
    // Если это строка формата "0:16:01"
    if (typeof timeData === 'string' && timeData.includes(':')) {
        const parts = timeData.split(':');
        if (parts.length === 3) {
            totalSeconds = parseInt(parts[0]) * 3600 + parseInt(parts[1]) * 60 + parseInt(parts[2]);
        } else if (parts.length === 2) {
            totalSeconds = parseInt(parts[0]) * 60 + parseInt(parts[1]);
        }
    }
    // Если это число (миллисекунды или секунды)
    else if (typeof timeData === 'number') {
        // Если больше 60000, это миллисекунды
        totalSeconds = timeData > 60000 ? timeData / 1000 : timeData;
    }
    // Если это ISO 8601 формат PT2490S
    else if (typeof timeData === 'string' && timeData.startsWith('PT')) {
        const match = timeData.match(/PT(?:(\d+)H)?(?:(\d+)M)?(?:(\d+(?:\.\d+)?)S)?/);
        if (match) {
            const h = parseInt(match[1] || 0);
            const m = parseInt(match[2] || 0);
            const s = parseFloat(match[3] || 0);
            totalSeconds = h * 3600 + m * 60 + Math.floor(s);
        }
    }
    
    if (totalSeconds <= 0) return '-';
    
    const totalMinutes = totalSeconds / 60;
    const pace = totalMinutes / distanceNum;
    return pace.toFixed(5);
}

// Функция сортировки таблицы
function sortTable(columnName) {
    // Если кликнули на тот же столбец - меняем направление
    if (sortState.column === columnName) {
        sortState.direction = sortState.direction === 'asc' ? 'desc' : 'asc';
    } else {
        // Новый столбец - начинаем с ascending
        sortState.column = columnName;
        sortState.direction = 'asc';
    }
    
    // Копируем filtered runners и сортируем
    let toSort = [...filteredRunners];
    
    toSort.sort((a, b) => {
        let valA, valB;
        
        switch(columnName) {
            case 'index':
                valA = 0;
                valB = 0;
                break;
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
                valA = (a.event || '').toLowerCase();
                valB = (b.event || '').toLowerCase();
                break;
            case 'gender':
                valA = (a.gender || '').toLowerCase();
                valB = (b.gender || '').toLowerCase();
                break;
            case 'category':
                valA = (a.category || '').toLowerCase();
                valB = (b.category || '').toLowerCase();
                break;
            case 'status':
                valA = (a.status || '').toLowerCase();
                valB = (b.status || '').toLowerCase();
                break;
            case 'time':
                // Специальная логика для времени финиша
                // "Not started" в конце, остальные по времени (быстрее первыми)
                const statusA = (a.race_status || 'не стартовал').toLowerCase();
                const statusB = (b.race_status || 'не стартовал').toLowerCase();
                
                const isNotStartedA = statusA.includes('not') && statusA.includes('start');
                const isNotStartedB = statusB.includes('not') && statusB.includes('start');
                
                if (isNotStartedA && !isNotStartedB) return 1;
                if (!isNotStartedA && isNotStartedB) return -1;
                if (isNotStartedA && isNotStartedB) return 0;
                
                // Для стартовавших - сортируем по времени финиша
                const timeA = a.time_clear_finish || a['times.official_:::finish:::'];
                const timeB = b.time_clear_finish || b['times.official_:::finish:::'];
                
                // Конвертируем время в секунды для сравнения
                const secsA = parseFloat(timeA) || Infinity;
                const secsB = parseFloat(timeB) || Infinity;
                
                valA = secsA;
                valB = secsB;
                break;
            case 'pace':
                const pace1 = calculatePace(a.time_clear_finish || a['times.official_:::finish:::'], a.distance || a.event);
                const pace2 = calculatePace(b.time_clear_finish || b['times.official_:::finish:::'], b.distance || b.event);
                valA = pace1 === '-' ? Infinity : parseFloat(pace1);
                valB = pace2 === '-' ? Infinity : parseFloat(pace2);
                break;
            default:
                return 0;
        }
        
        // Сравнение
        if (valA < valB) return sortState.direction === 'asc' ? -1 : 1;
        if (valA > valB) return sortState.direction === 'asc' ? 1 : -1;
        return 0;
    });
    
    // Рендерим таблицу
    renderResultsTable(toSort);
}

// Отрисовываем таблицу результатов
function renderResultsTable(runners) {
    const tbody = document.getElementById('resultsTableBody');
    tbody.innerHTML = '';
    
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
        
        //финиша (поддерживаем оба формата данных)
        const finishTime = runner.time_clear_finish || runner['times.official_:::finish:::'];
        time = formatTime(finishTime);
        
        // Темп: используем значение из БД как есть
        let pace = runner.finish_pace_avg || '-';
        // Если значение содержит число, оставляем как есть
        if (pace && pace !== '#ЗНАЧ!' && typeof pace === 'string') {
            // Убедимся что есть "мин/км" в конце если нужно
            if (!pace.includes('мин')) {
                pace = pace + ' мин/км';
            }
        } else {
            pace = '-';
        }
        
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
