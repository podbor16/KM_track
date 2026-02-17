// legacy/static/analytics.js
// Функция заново загружает данные из основного источника (race_data.json)
let currentMode = 'before'; // По умолчанию режим "результаты"
let allRunners = [];
let filteredRunners = [];
let sortState = { column: null, direction: 'asc' }; // Отслеживание сортировки

// Инициализация страницы
document.addEventListener('DOMContentLoaded', function() {
    // Устанавливаем правильную активную кнопку при загрузке
    document.getElementById('beforeModeBtn').classList.toggle('active', currentMode === 'before');
    document.getElementById('duringModeBtn').classList.toggle('active', currentMode === 'during');
    
    loadRunnersData();
});

// Функция переключения режимов
function switchMode(mode) {
    currentMode = mode;
    
    // Обновляем активные кнопки
    document.getElementById('beforeModeBtn').classList.toggle('active', mode === 'before');
    document.getElementById('duringModeBtn').classList.toggle('active', mode === 'during');
    
    // Пока скрываем оба режима
    document.getElementById('startListWrapper').style.display = 'none';
    document.getElementById('resultsWrapper').style.display = 'none';
    
    // Сбрасываем фильтры и поиск, сортировку
    document.getElementById('genderFilter').value = '';
    document.getElementById('ageGroupFilter').value = '';
    document.getElementById('distanceFilter').value = '';
    document.getElementById('surnameSearch').value = '';
    sortState = { column: null, direction: 'asc' };
    
    // Перезагружаем данные в зависимости от режима
    loadRunnersData();
}

// Функция загрузки данных
async function loadRunnersData() {
    console.log('Загрузка данных начата, режим:', currentMode);
    showLoading(true);
    
    try {
        let data;
        
        if (currentMode === 'before') {
            // Режим до забега - загружаем зарегистрированных участников из БД
            console.log('Запрос к /api/registered-runners');
            data = await fetch('/api/registered-runners').then(response => {
                console.log('Ответ от /api/registered-runners получен, статус:', response.status);
                return response.json();
            });
        } else {
            // Режим во время/после забега - загружаем данные гонки из race_data.json
            console.log('Запрос к /api/race-results');
            data = await fetch('/api/race-results').then(response => {
                console.log('Ответ от /api/race-results получен, статус:', response.status);
                return response.json();
            });
        }
        
        allRunners = Array.isArray(data) ? data : (data.runners || data.data || []);
        
        // Добавим логирование для отладки
        console.log('Данные получены:', data);
        console.log('allRunners:', allRunners);
        console.log('Количество элементов:', allRunners.length);
        if (allRunners.length > 0) {
            console.log('Пример первого элемента:', allRunners[0]);
        }
        
        // Заполняем фильтры для обоих режимов
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
    const savedValue = ageGroupSelect.value; // Сохраняем текущее выбранное значение
    const ageGroups = new Set();
    
    runners.forEach(runner => {
        // Проверяем различные возможные названия полей для возрастной категории
        let category = null;
        
        if (currentMode === 'before') {
            // Для стартового списка используем поле 'category' (рассчитанное на сервере)
            if (runner.category) {
                category = runner.category;
            }
        } else {
            // Для результатов используем 'category'
            if (runner.category) {
                category = runner.category;
            } else if (runner.age_group) {
                category = runner.age_group;
            } else if (runner['Возрастная категория']) {
                category = runner['Возрастная категория'];
            }
        }
        
        if (category) {
            ageGroups.add(category);
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

// Применяем фильтры к данным
function applyFilters() {
    const genderFilter = document.getElementById('genderFilter').value;
    const ageGroupFilter = document.getElementById('ageGroupFilter').value;
    const distanceFilter = document.getElementById('distanceFilter').value;
    const surnameSearch = document.getElementById('surnameSearch').value.toLowerCase().trim();
    
    console.log('Применение фильтров:', { genderFilter, ageGroupFilter, distanceFilter, surnameSearch, currentMode, totalRunners: allRunners.length });
    
    filteredRunners = allRunners.filter(runner => {
        // Фильтр по фамилии - поиск с начала фамилии
        if (surnameSearch !== '') {
            const runnerSurname = (runner.surname || '').toLowerCase();
            if (!runnerSurname.startsWith(surnameSearch)) {
                return false;
            }
        }
        
        // КГЛючевые данные для работы
        let runnerSurname = (runner.surname || '').toLowerCase();
        let runnerGender = '';
        if (currentMode === 'before') {
            // Для стартового списка используем поле 'sex' директно
            runnerGender = (runner.sex || '').trim();
        } else {
            // Для результатов
            if (runner.gender) {
                runnerGender = (runner.gender || '').trim();
            } else if (runner.sex) {
                runnerGender = (runner.sex || '').trim();
            }
        }
        
        // Фильтр по полу
        if (genderFilter !== '' && runnerGender !== genderFilter) {
            return false;
        }
        
        // Фильтр по возрастной группе (для обоих режимов)
        let runnerCategory = '';
        if (runner.category) {
            runnerCategory = runner.category;
        } else if (runner.age_group) {
            runnerCategory = runner.age_group;
        } else if (runner['Возрастная категория']) {
            runnerCategory = runner['Возрастная категория'];
        }
        
        if (ageGroupFilter !== '' && runnerCategory !== ageGroupFilter) {
            return false;
        }
        
        // Фильтр по дистанции (для обоих режимов)
        let runnerDistance = '';
        if (runner.distance) {
            runnerDistance = runner.distance;
        } else if (runner.event) {
            runnerDistance = runner.event;
        }
        
        if (distanceFilter !== '' && runnerDistance !== distanceFilter) {
            return false;
        }
        
        return true;
    });
    
    console.log(`Результат фильтрации: ${filteredRunners.length} из ${allRunners.length} участников`);
    
    // Заполняем фильтры возрастных групп и дистанций со ВСЕМИ данными (чтобы опции не исчезали)
    populateAgeGroups(allRunners);
    populateDistances(allRunners);
    
    // Рендерим в зависимости от режима
    if (currentMode === 'before') {
        renderStartList(filteredRunners);
    } else {
        renderResultsTable(filteredRunners);
        // Автоматически сортируем по темпу (от минимального к максимальному) только для режима 'during'
        sortState.column = 'pace';
        sortState.direction = 'asc';
        sortTable('pace');
    }
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
        
        // Для режима 'before' - используем другие поля
        if (currentMode === 'before') {
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
                    valA = 0;
                    valB = 0;
                    break;
                case 'category':
                    valA = (a.category || '').toLowerCase();
                    valB = (b.category || '').toLowerCase();
                    break;
                case 'sex':
                    valA = (a.sex || '').toLowerCase();
                    valB = (b.sex || '').toLowerCase();
                    break;
                case 'city':
                    valA = (a.city || a.City || '').toLowerCase();
                    valB = (b.city || b.City || '').toLowerCase();
                    break;
                case 'club':
                    valA = (a.club || a.Club || '').toLowerCase();
                    valB = (b.club || b.Club || '').toLowerCase();
                    break;
                default:
                    return 0;
            }
        } else {
            // Для режима 'during'
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
                case 'birthday':
                    valA = a.birthdate ? new Date(a.birthdate).getFullYear() : 0;
                    valB = b.birthdate ? new Date(b.birthdate).getFullYear() : 0;
                    break;
                case 'event':
                    valA = (a.event || '').toLowerCase();
                    valB = (b.event || '').toLowerCase();
                    break;
                case 'sex':
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
            }
        }
        
        // Сравнение
        if (valA < valB) return sortState.direction === 'asc' ? -1 : 1;
        if (valA > valB) return sortState.direction === 'asc' ? 1 : -1;
        return 0;
    });
    
    // Рендерим в зависимости от режима
    if (currentMode === 'before') {
        renderStartList(toSort);
    } else {
        renderResultsTable(toSort);
    }
}

// Отрисовываем таблицу результатов (режим 'during')
function renderResultsTable(runners) {
    const tbody = document.getElementById('resultsTableBody');
    tbody.innerHTML = '';
    
    // Показываем таблицу результатов
    document.getElementById('resultsWrapper').style.display = 'block';
    document.getElementById('startListWrapper').style.display = 'none';
    
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
            <td>${runner.bib || '-'}</td>
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

// Отрисовываем таблицу стартового списка (режим 'before')
function renderStartList(runners) {
    const tbody = document.getElementById('startListBody');
    tbody.innerHTML = '';
    
    // Показываем таблицу стартового списка
    document.getElementById('startListWrapper').style.display = 'block';
    document.getElementById('resultsWrapper').style.display = 'none';
    
    runners.forEach((runner, index) => {
        const row = document.createElement('tr');
        
        // Фамилия, имя
        let firstName = runner.name || 'N/A';
        let lastName = runner.surname || 'N/A';
        
        // Дистанция - из race_data.json, дефолт "1 км"
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
        
        // Год рождения из birthday
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
        
        // Возрастная категория - высчитана на сервере из birthday
        let category = runner.category || 'Неизвестно';
        
        // Город, клуб
        let city = runner.city || 'N/A';
        let club = runner.club || 'N/A';
        
        let rowHTML = `
            <td>${index + 1}</td>
            <td>${lastName}</td>
            <td>${firstName}</td>
            <td>${distance}</td>
            <td><span class="gender-tag ${genderClass}">${genderText}</span></td>
            <td>${birthYear}</td>
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
