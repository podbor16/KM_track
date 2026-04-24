// legacy/static/analytics-start-list.js
// Javascript для страницы стартового списка
let allRunners = [];
let filteredRunners = [];
let sortState = { column: null, direction: 'asc' }; // Отслеживание сортировки
let currentEvent = 'night_run'; // Текущее выбранное событие

const eventNameMap = KMUtils.EVENT_NAMES;
const eventColorMap = KMUtils.EVENT_COLORS;

// Инициализация страницы — дефолт из активного забега
document.addEventListener('DOMContentLoaded', async function() {
    try {
        const cfg = await fetch('/api/current-event').then(r => r.json());
        currentEvent = cfg.event || 'night_run';
    } catch {
        currentEvent = 'night_run';
    }
    document.getElementById('eventSelector').value = currentEvent;
    updateEventCardBackground();
    updateEventThemeColor();
    loadRunnersData();
});

// Функция обновления фонового изображения карточки события
function updateEventCardBackground() {
    const eventCard = document.getElementById('eventCard');
    const eventDisplayName = eventNameMap[currentEvent];
    const imageUrl = `/static/images/events/${encodeURIComponent(eventDisplayName)}.png`;
    eventCard.style.backgroundImage = `url('${imageUrl}')`;
}

// Функция обновления цвета темы в зависимости от события
function updateEventThemeColor() {
    const color = eventColorMap[currentEvent] || '#EE2D62';
    document.documentElement.style.setProperty('--primary-color', color);
}

// Функция для смены события
async function switchEvent() {
    const eventSelector = document.getElementById('eventSelector');
    currentEvent = eventSelector.value;
    
    // Сохраняем выбор в localStorage
    localStorage.setItem('selectedEvent', currentEvent);
    
    // Обновляем фон карточки события и цвет темы
    updateEventCardBackground();
    updateEventThemeColor();
    
    // Сбрасываем фильтры
    document.getElementById('genderFilter').value = '';
    document.getElementById('ageGroupFilter').value = '';
    document.getElementById('distanceFilter').value = '';
    document.getElementById('surnameSearch').value = '';
    sortState = { column: null, direction: 'asc' };
    
    // Перезагружаем данные
    console.log('Смена события на:', currentEvent);
    loadRunnersData();
}

// Функция загрузки данных
async function loadRunnersData() {
    console.log('Загрузка данных для стартового списка, событие:', currentEvent);
    allRunners = [];
    filteredRunners = [];
    document.getElementById('startListBody').innerHTML = '';
    showLoading(true);

    try {
        // Загружаем зарегистрированных участников из БД с фильтром по событию
        const eventName = eventNameMap[currentEvent] || 'Ночной забег';
        console.log('Запрос к /api/registered-runners с событием:', eventName);
        const data = await fetch(`/api/registered-runners?event_name=${encodeURIComponent(eventName)}`).then(response => {
            console.log('Ответ от /api/registered-runners получен, статус:', response.status);
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

// Заполняем опции возрастных групп
function populateAgeGroups(runners) {
    const ageGroupSelect = document.getElementById('ageGroupFilter');
    const genderFilter = document.getElementById('genderFilter').value; // Получаем выбранный пол
    const savedValue = ageGroupSelect.value;
    const ageGroups = new Set();
    
    runners.forEach(runner => {
        if (runner.category) {
            ageGroups.add(runner.category);
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
        if (runner.distance) {
            distance = runner.distance;
        } else if (runner.event) {
            distance = runner.event;
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
        let runnerSurname = (runner.surname || '').toLowerCase();
        let runnerGender = (runner.sex || '').trim();
        
        // Фильтр по полу
        if (genderFilter !== '' && runnerGender !== genderFilter) {
            return false;
        }
        
        // Фильтр по возрастной группе
        let runnerCategory = runner.category || '';
        
        if (ageGroupFilter !== '' && runnerCategory !== ageGroupFilter) {
            return false;
        }
        
        // Фильтр по дистанции
        let runnerDistance = runner.distance || '';
        
        if (distanceFilter !== '' && runnerDistance !== distanceFilter) {
            return false;
        }
        
        return true;
    });
    
    console.log(`Результат фильтрации: ${filteredRunners.length} из ${allRunners.length} участников`);
    
    // Заполняем фильтры дистанций со ВСЕМИ данными (чтобы опции не исчезали)
    populateAgeGroups(allRunners);
    populateDistances(allRunners);
    
    // Рендерим таблицу
    renderStartList(filteredRunners);
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
            case 'bib':
                valA = a.bib || 0;
                valB = b.bib || 0;
                break;
            case 'surname':
                valA = (a.surname || '').toLowerCase();
                valB = (b.surname || '').toLowerCase();
                break;
            case 'name':
                valA = (a.name || '').toLowerCase();
                valB = (b.name || '').toLowerCase();
                break;
            case 'birthday':
                valA = a.birthdate || a.birthday ? new Date(a.birthdate || a.birthday).getFullYear() : 0;
                valB = b.birthdate || b.birthday ? new Date(b.birthdate || b.birthday).getFullYear() : 0;
                break;
            case 'distance':
                valA = (a.distance || '').toLowerCase();
                valB = (b.distance || '').toLowerCase();
                break;
            case 'sex':
                valA = (a.sex || '').toLowerCase();
                valB = (b.sex || '').toLowerCase();
                break;    
            case 'category':
                valA = (a.category || '').toLowerCase();
                valB = (b.category || '').toLowerCase();
                break;

            case 'city':
                valA = (a.city || a.City || '').toLowerCase();
                valB = (b.city || b.City || '').toLowerCase();
                break;
            case 'club':
                valA = (a.club || a.Club || 'Без клуба').toLowerCase();
                valB = (b.club || b.Club || 'Без клуба').toLowerCase();
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
    renderStartList(toSort);
}

// Отрисовываем таблицу стартового списка
function renderStartList(runners) {
    const tbody = document.getElementById('startListBody');
    tbody.innerHTML = '';
    
    runners.forEach((runner, index) => {
        const row = document.createElement('tr');
        
        // Фамилия, имя
        let firstName = runner.name || 'N/A';
        let lastName = runner.surname || 'N/A';

        // Год рождения
        let birthYear = 'N/A';
        if (runner.birthday) {
            try {
                const dateStr = runner.birthday;
                const year = new Date(dateStr).getFullYear();
                birthYear = year > 0 ? year : 'N/A';
            } catch (e) {
                birthYear = 'N/A';
            }
        }
        
        // Дистанция
        let distance = runner.distance || '1 км';
        
        // Пол
        let genderClass = '';
        let genderText = 'N/A';
        
        if (runner.sex) {
            if (runner.sex === 'Мужчина') {
                genderText = 'Мужчина';
                genderClass = 'gender-male';
            } else if (runner.sex === 'Женщина') {
                genderText = 'Женщина';
                genderClass = 'gender-female';
            } else {
                genderText = runner.sex;
                genderClass = '';
            }
        }
        
        // Возрастная категория
        let category = runner.category || 'Неизвестно';
        
        // Город, клуб - заменяем null, 'null' и N/A на пустую строку
        let city = (runner.city && runner.city.toLowerCase() !== 'n/a' && runner.city.toLowerCase() !== 'null') ? runner.city : '';
        let club = (runner.club && runner.club.toLowerCase() !== 'n/a' && runner.club.toLowerCase() !== 'null') ? runner.club : '';
        
        let rowHTML = `
            <td>${index + 1}</td>
            <td>${lastName}</td>
            <td>${firstName}</td>
            <td>${birthYear}</td>
            <td>${distance}</td>
            <td><span class="gender-tag ${genderClass}">${genderText}</span></td>
            <td><span class="age-group-tag">${category}</span></td>
            <td>${city}</td>
            <td>${club}</td>
        `;
        
        row.innerHTML = rowHTML;
        tbody.appendChild(row);
    });
    
    console.log(`Отрисовано ${runners.length} строк таблицы стартового списка`);
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
