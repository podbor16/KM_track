// JavaScript для страницы стартового списка и результатов забега

let currentMode = 'before'; // 'before' или 'during'
let allRunners = [];
let filteredRunners = [];

// Инициализация страницы
document.addEventListener('DOMContentLoaded', function() {
    loadRunnersData();
});

// Функция переключения режимов
function switchMode(mode) {
    currentMode = mode;
    
    // Обновляем активные кнопки
    document.getElementById('beforeModeBtn').classList.toggle('active', mode === 'before');
    document.getElementById('duringModeBtn').classList.toggle('active', mode === 'during');
    
    // Обновляем классы контейнера для скрытия/показа столбцов
    const tableContainer = document.querySelector('.container');
    tableContainer.classList.toggle('before-mode', mode === 'before');
    tableContainer.classList.toggle('during-mode', mode === 'during');
    
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
        
        populateAgeGroups(allRunners);
        applyFilters();
    } catch (error) {
        console.error('Ошибка загрузки данных:', error);
        showError('Ошибка загрузки данных: ' + error.message);
    } finally {
        showLoading(false);
    }
}

// Заполняем опции возрастных групп
function populateAgeGroups(runners) {
    const ageGroupSelect = document.getElementById('ageGroupFilter');
    const ageGroups = new Set();
    
    runners.forEach(runner => {
        // Проверяем различные возможные названия полей для возрастной категории
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
    
    // Добавляем уникальные возрастные группы
    const sortedGroups = Array.from(ageGroups).sort();
    sortedGroups.forEach(group => {
        const option = document.createElement('option');
        option.value = group;
        option.textContent = group;
        ageGroupSelect.appendChild(option);
    });
}

// Применяем фильтры к данным
function applyFilters() {
    const genderFilter = document.getElementById('genderFilter').value;
    const ageGroupFilter = document.getElementById('ageGroupFilter').value;
    
    filteredRunners = allRunners.filter(runner => {
        // Фильтр по полу - проверяем различные возможные названия полей
        let runnerGender = '';
        if (runner.gender) {
            runnerGender = runner.gender;
        } else if (runner.sex) {
            runnerGender = runner.sex;
        }
        
        if (genderFilter && runnerGender !== genderFilter) {
            return false;
        }
        
        // Фильтр по возрастной группе - проверяем различные возможные названия полей
        let runnerCategory = '';
        if (runner.category) {
            runnerCategory = runner.category;
        } else if (runner.age_group) {
            runnerCategory = runner.age_group;
        } else if (runner['Возрастная категория']) {
            runnerCategory = runner['Возрастная категория'];
        }
        
        if (ageGroupFilter && runnerCategory !== ageGroupFilter) {
            return false;
        }
        
        return true;
    });
    
    renderTable(filteredRunners);
}

// Отрисовываем таблицу
function renderTable(runners) {
    const tbody = document.getElementById('tableBody');
    tbody.innerHTML = '';
    
    runners.forEach((runner, index) => {
        const row = document.createElement('tr');
        
        // Вычисляем возраст - проверяем различные возможные названия полей
        let birthYear = 'N/A';
        if (runner.birthdate) {
            birthYear = new Date(runner.birthdate).getFullYear();
        } else if (runner.birth_date) {
            birthYear = new Date(runner.birth_date).getFullYear();
        } else if (runner['Дата рождения']) {
            birthYear = new Date(runner['Дата рождения']).getFullYear();
        }
        
        const currentYear = new Date().getFullYear();
        const age = birthYear !== 'N/A' ? currentYear - birthYear : 'N/A';
        
        // Определяем статус и время в зависимости от режима
        let status = '';
        let time = '';
        let statusClass = '';
        
        if (currentMode === 'before') {
            status = 'Зарегистрирован';
            time = '-';
            statusClass = 'status-registered';
        } else {
            status = runner.status || 'Неизвестно';
            statusClass = `status-${runner.status || 'unknown'}`;
            
            if (runner.status === 'finished' && runner.times && runner.times['real_:::finish:::']) {
                const finishTime = runner.times['real_:::finish:::'];
                const startTime = runner.times['real_:::start:::'] || 0;
                const netTime = finishTime - startTime;
                
                // Форматируем время в формат MM:SS
                const minutes = Math.floor(netTime / 60000);
                const seconds = Math.floor((netTime % 60000) / 1000);
                time = `${minutes.toString().padStart(2, '0')}:${seconds.toString().padStart(2, '0')}`;
            } else if (runner.status === 'running') {
                time = 'В пути';
            } else if (runner.status === 'notstarted') {
                time = 'Не стартовал';
            } else if (runner.status === 'disqualified') {
                time = 'Дисквалифицирован';
            } else {
                time = '-';
            }
        }
        
        // Определяем имя и фамилию - проверяем различные возможные названия полей
        let firstName = 'N/A';
        let lastName = 'N/A';
        let genderText = 'N/A';
        
        if (runner.name) {
            firstName = runner.name;
        } else if (runner.first_name) {
            firstName = runner.first_name;
        } else if (runner['Имя пользователя']) {
            firstName = runner['Имя пользователя'];
        }
        
        if (runner.surname) {
            lastName = runner.surname;
        } else if (runner.last_name) {
            lastName = runner.last_name;
        } else if (runner['Фамилия пользователя']) {
            lastName = runner['Фамилия пользователя'];
        }
        
        if (runner.gender) {
            genderText = runner.gender === 'male' ? 'Мужской' : runner.gender === 'female' ? 'Женский' : runner.gender;
        } else if (runner.sex) {
            genderText = runner.sex === 'male' ? 'Мужской' : runner.sex === 'female' ? 'Женский' : runner.sex;
        }
        
        // Определяем дистанцию и возрастную группу
        let distance = runner.event || runner.distance || runner['Дистанция'] || '7 km';
        let category = runner.category || runner.age_group || runner['Возрастная категория'] || '';
        
        let rowHTML = `
            <td>${index + 1}</td>
            <td>${lastName}</td>
            <td>${firstName}</td>
            <td>${birthYear}</td>
            <td class="distance-col">${distance}</td>
            <td>${genderText}</td>
            <td><span class="age-group-tag">${category}</span></td>
            <td class="${statusClass} status-col">${status}</td>
            <td class="time-cell time-col">${time}</td>
        `;
        
        row.innerHTML = rowHTML;
        tbody.appendChild(row);
    });
    
    // Добавим сообщение о количестве отрисованных строк
    console.log(`Отрисовано ${runners.length} строк таблицы`);
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