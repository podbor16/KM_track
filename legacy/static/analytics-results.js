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

// Инициализация страницы
document.addEventListener('DOMContentLoaded', function() {
    populateYearSelector();
    restoreSavedPreferences();
    updateEventThemeColor();
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
    console.log('Загрузка данных для результатов');
    showLoading(true);
    
    try {
        // Загружаем данные гонки из race_data.json
        const eventName = eventNameMap[currentEvent] || 'Ночной забег';
        const apiUrl = `/api/race-results?event_name=${encodeURIComponent(eventName)}&year=${currentYear}`;
        console.log('Запрос к ' + apiUrl);
        const data = await fetch(apiUrl).then(response => {
            console.log('Ответ от /api/race-results получен, статус:', response.status);
            return response.json();
        });
        
        allRunners = Array.isArray(data) ? data : (data.runners || data.data || []);
        
        // Добавим логирование для отладки
        console.log('Данные получены:', data);
        console.log('allRunners:', allRunners);
        console.log('Количество элементов:', allRunners.length);
        if (allRunners.length > 0) {
            console.log('Пример первого элемента:', allRunners[0]);
        }
        
        // Заполняем фильтры
        populateAgeGroups(allRunners);
        populateDistances(allRunners);
        
        applyFilters();
        showLoading(false);
    } catch (error) {
        console.error('Ошибка загрузки данных:', error);
        showError('Ошибка загрузки данных: ' + error.message);
        showLoading(false);
    }
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
    
    // Рендерим таблицу и сортируем по темпу по умолчанию
    sortState.column = 'pace';
    sortState.direction = 'asc';
    sortTable('pace');
}

// Функция для форматирования времени из миллисекунд в чч:мм:сс
function formatTime(milliseconds) {
    if (!milliseconds) return '-';
    const totalSeconds = Math.floor(milliseconds / 1000);
    const hours = Math.floor(totalSeconds / 3600);
    const minutes = Math.floor((totalSeconds % 3600) / 60);
    const seconds = totalSeconds % 60;
    return `${hours.toString().padStart(2, '0')}:${minutes.toString().padStart(2, '0')}:${seconds.toString().padStart(2, '0')}`;
}

// Функция для расчета темпа (минут на км)
function calculatePace(milliseconds, distanceStr) {
    if (!milliseconds || !distanceStr) return '-';
    const distance = parseFloat(distanceStr);
    if (distance <= 0) return '-';
    const totalMinutes = milliseconds / 1000 / 60;
    const pace = totalMinutes / distance;
    return pace.toFixed(2);
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
            case 'pace':
                const pace1 = calculatePace(a['times.official_:::finish:::'], a.event);
                const pace2 = calculatePace(b['times.official_:::finish:::'], b.event);
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
        let birthYear = 'N/A';
        if (runner.birthdate) {
            const year = new Date(runner.birthdate).getFullYear();
            birthYear = year > 0 ? year : 'N/A';
        }
        
        // Статус и время
        let status = '';
        let time = '';
        let pace = '-';
        let statusClass = '';
        
        // Переводим статусы на русский
        let statusRu = runner.status || 'Неизвестно';
        if (runner.status === 'finished') statusRu = 'Финишировал';
        if (runner.status === 'notstarted') statusRu = 'Не стартовал';
        if (runner.status === 'disqualified') statusRu = 'Дисквалифицирован';
        if (runner.status === 'running') statusRu = 'Бежит';
        
        status = statusRu;
        statusClass = `status-${runner.status || 'unknown'}`;
        const finishTime = runner['times.official_:::finish:::'];
        time = formatTime(finishTime);
        pace = calculatePace(finishTime, runner.event);
        
        // Фамилия, имя, пол
        let firstName = runner.name || 'N/A';
        let lastName = runner.surname || 'N/A';
        let genderClass = '';
        let genderText = 'N/A';
        
        if (runner.gender) {
            if (runner.gender === 'male') {
                genderText = 'мужчина';
                genderClass = 'gender-male';
            } else if (runner.gender === 'female') {
                genderText = 'женщина';
                genderClass = 'gender-female';
            } else {
                genderText = runner.gender;
                genderClass = '';
            }
        }
        
        // Дистанция и возрастная группа
        let distance = runner.event || '7 km';
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
    
    console.log(`Отрисовано ${runners.length} строк таблицы результатов`);
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
