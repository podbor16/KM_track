// legacy/static/analytics-start-list.js
// Javascript для страницы стартового списка
let allRunners = [];
let filteredRunners = [];
let sortState = { column: 'surname', direction: 'asc' }; // Отслеживание сортировки
let currentEvent = 'night_run'; // Текущее выбранное событие
let currentYear = new Date().getFullYear();

const eventNameMap = KMUtils.EVENT_NAMES;
const eventColorMap = KMUtils.EVENT_COLORS;

// ──────────────── Состояние в URL (прямая ссылка на конкретный
// событие+год+дистанцию+фильтры, напр. чтобы прислать ссылку на старт-лист
// конкретного забега) ────────────────
// distance/ageGroup применяются "один раз" при первой загрузке данных — их
// селекты в момент чтения URL ещё пустые (заполняются позже из реальных
// данных события в populateDistances()/populateAgeGroups()), поэтому
// напрямую задать select.value здесь бесполезно (браузер игнорирует
// значение без совпадающей <option>). Флаги обнуляются после первого
// успешного применения, чтобы не перебивать дальнейший ручной выбор
// пользователя при каждом ре-рендере фильтров.
let _urlEvent = null;
let _urlYear = null;
let _urlDistance = null;
let _urlAgeGroup = null;

function readStateFromUrl() {
    const params = new URLSearchParams(location.search);
    const event = params.get('event');
    _urlEvent = event && eventNameMap[event] ? event : null;
    const yearParam = parseInt(params.get('year'), 10);
    _urlYear = Number.isFinite(yearParam) ? yearParam : null;
    _urlDistance = params.get('distance') || null;
    _urlAgeGroup = params.get('ageGroup') || null;
    const gender = params.get('gender');
    if (gender === 'Мужчина' || gender === 'Женщина') _setGenderFilterActivePill(gender);
    const search = params.get('search');
    if (search) document.getElementById('surnameSearch').value = search;
}

// Пишет текущие фильтры в query-параметры при каждом применении фильтров
// (history.replaceState — НЕ pushState, иначе каждый клик фильтра добавлял
// бы шаг в историю браузера вместо осмысленных переходов; тот же принцип,
// что на Siberman results.html, см. syncUrlFromState() там).
function syncUrlFromState() {
    const params = new URLSearchParams();
    params.set('event', currentEvent);
    params.set('year', currentYear);
    const distance = document.getElementById('distanceFilter').value;
    if (distance) params.set('distance', distance);
    const gender = getGenderFilterValue();
    if (gender) params.set('gender', gender);
    const ageGroup = document.getElementById('ageGroupFilter').value;
    if (ageGroup) params.set('ageGroup', ageGroup);
    const search = document.getElementById('surnameSearch').value;
    if (search) params.set('search', search);
    const qs = params.toString();
    const newUrl = qs ? `${location.pathname}?${qs}` : location.pathname;
    if (newUrl !== location.pathname + location.search) history.replaceState(null, '', newUrl);
}

// Инициализация страницы — дефолт из активного забега, переопределяется
// параметрами URL, если открыли по прямой ссылке
document.addEventListener('DOMContentLoaded', async function() {
    populateYearSelector();
    readStateFromUrl();
    try {
        const cfg = await fetch('/api/current-event').then(r => r.json());
        currentEvent = _urlEvent || cfg.event || 'night_run';
        currentYear = _urlYear || cfg.year || new Date().getFullYear();
    } catch {
        currentEvent = _urlEvent || 'night_run';
        currentYear = _urlYear || currentYear;
    }
    document.getElementById('eventSelector').value = currentEvent;
    const ySel = document.getElementById('yearStartSelector');
    if (ySel) ySel.value = currentYear;
    updateEventThemeColor();
    updateEventBanner();
    updatePageTitle();
    loadRunnersData();
    new SSEClient('/api/sse/notify', {
        startlist_updated: () => loadRunnersData(true)
    });
});

function populateYearSelector() {
    const sel = document.getElementById('yearStartSelector');
    if (!sel) return;
    const now = new Date().getFullYear();
    for (let y = now + 1; y >= 2020; y--) {
        const opt = document.createElement('option');
        opt.value = y;
        opt.textContent = y;
        sel.appendChild(opt);
    }
    sel.value = now;
}

// Функция обновления цвета темы в зависимости от события
function updateEventThemeColor() {
    const color = eventColorMap[currentEvent] || '#EE2D62';
    document.documentElement.style.setProperty('--primary-color', color);
}

// Декоративный баннер события над тулбаром — показывается ТОЛЬКО если для
// события реально есть фото в static/images/events/ (не у всех событий оно
// есть). Наличие проверяется загрузкой картинки в браузере (Image()
// onload/onerror), а не хардкод-списком — новое фото подхватится само.
// Видимость серого подзаголовка под h1 зависит от того, показан ли баннер
// (проверяется асинхронной загрузкой картинки — см. updateEventBanner).
// Флаг общий с updatePageTitle(): applyFilters() дёргает updatePageTitle()
// уже ПОСЛЕ завершения загрузки баннера (порядок не гарантирован), поэтому
// решение "показывать ли подзаголовок" нельзя принимать только в момент
// onload/onerror картинки — оно должно применяться и при каждой
// пересборке заголовка через innerHTML.
let _eventBannerVisible = false;

function updateEventBanner() {
    const banner = document.getElementById('eventBanner');
    if (!banner) return;
    const eventDisplayName = eventNameMap[currentEvent] || '';
    if (!eventDisplayName) {
        banner.style.display = 'none';
        _eventBannerVisible = false;
        _setPageTitleSubtitleVisible(true);
        return;
    }
    const imageUrl = `/static/images/events/${encodeURIComponent(eventDisplayName)}.png`;
    const img = new Image();
    img.onload = () => {
        banner.style.backgroundImage = `url('${imageUrl}')`;
        banner.style.display = '';
        _eventBannerVisible = true;
        _setPageTitleSubtitleVisible(false);
    };
    img.onerror = () => {
        banner.style.display = 'none';
        _eventBannerVisible = false;
        _setPageTitleSubtitleVisible(true);
    };
    img.src = imageUrl;
}

function _setPageTitleSubtitleVisible(visible) {
    const subtitle = document.querySelector('.page-title-event');
    if (subtitle) subtitle.style.display = visible ? '' : 'none';
}

// Последний год, для которого у события реально есть заявки (leads) или
// уже сконфигурирована дистанция в events (см. get_leads_filter_options на
// бэкенде) — дефолт года при смене СОБЫТИЯ, а не текущий календарный год,
// у которого может вообще не быть данных для новостыранного события.
async function fetchLatestYearForEvent(event) {
    const eventName = eventNameMap[event];
    if (!eventName) return null;
    try {
        const data = await fetch(`/api/registered-runners-years?event_name=${encodeURIComponent(eventName)}`).then(r => r.json());
        return Array.isArray(data.years) && data.years.length ? data.years[0] : null;
    } catch {
        return null;
    }
}

// Функция для смены события или года. trigger различает, какой селектор
// вызвал смену ('event'/'year') — год автоматически переключается на
// последний доступный ТОЛЬКО при смене события, ручной выбор года в
// селекторе не перебивается.
async function switchEvent(trigger) {
    const eventSelector = document.getElementById('eventSelector');
    currentEvent = eventSelector.value;
    const ySel = document.getElementById('yearStartSelector');

    if (trigger === 'event') {
        const latestYear = await fetchLatestYearForEvent(currentEvent);
        if (latestYear) {
            currentYear = latestYear;
            if (ySel) ySel.value = latestYear;
        } else if (ySel) {
            currentYear = parseInt(ySel.value) || currentYear;
        }
    } else if (ySel) {
        currentYear = parseInt(ySel.value) || currentYear;
    }

    // Сохраняем выбор в localStorage
    localStorage.setItem('selectedEvent', currentEvent);

    // Обновляем цвет темы
    updateEventThemeColor();
    updateEventBanner();

    // Сбрасываем фильтры. distanceFilter сбрасывается в '' — этого значения
    // больше нет среди опций (см. populateDistances()), поэтому при
    // следующей загрузке данных сработает её фоллбэк и выберется
    // максимальная дистанция нового события, а не унаследуется дистанция
    // от предыдущего.
    _setGenderFilterActivePill('');
    document.getElementById('ageGroupFilter').value = '';
    document.getElementById('distanceFilter').value = '';
    document.getElementById('surnameSearch').value = '';
    sortState = { column: 'surname', direction: 'asc' };

    // Обновляем заголовок
    updatePageTitle();

    // Перезагружаем данные
    console.log('Смена события на:', currentEvent);
    loadRunnersData();
}

function updatePageTitle() {
    const title = document.getElementById('pageTitle');
    if (!title) return;
    const name = eventNameMap[currentEvent] || currentEvent;
    const distSel = document.getElementById('distanceFilter');
    const dist = distSel && distSel.value ? `, ${distSel.value}` : '';
    const subtitle = `${name} ${currentYear}${dist}`;
    const subtitleStyle = _eventBannerVisible ? ' style="display:none"' : '';
    title.innerHTML = `Стартовый список<br><span class="page-title-event"${subtitleStyle}>${subtitle}</span>`;
    const bannerTitle = document.getElementById('eventBannerTitle');
    if (bannerTitle) bannerTitle.textContent = subtitle;
}

// Функция загрузки данных
async function loadRunnersData(silent = false) {
    console.log('Загрузка данных для стартового списка, событие:', currentEvent);
    if (!silent) {
        allRunners = [];
        filteredRunners = [];
        document.getElementById('startListBody').innerHTML = '';
        showLoading(true);
    }

    try {
        // Загружаем зарегистрированных участников из БД с фильтром по событию
        const eventName = eventNameMap[currentEvent] || 'Ночной забег';
        const url = `/api/registered-runners?event_name=${encodeURIComponent(eventName)}&event_year=${currentYear}`;
        const data = await fetch(url).then(r => r.json());

        
        const raw = Array.isArray(data) ? data : (data.runners || data.data || []);
        allRunners = raw.map(r => ({...r, category: KMUtils.normalizeCategory(r.category)}));
        
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
        if (!silent) showLoading(false);
    } catch (error) {
        if (!silent) {
            console.error('Ошибка загрузки данных:', error);
            showError('Ошибка загрузки данных: ' + error.message);
            showLoading(false);
        } else {
            console.warn('⚠️ Фоновое обновление стартового списка не удалось:', error.message);
        }
    }
}

// Заполняем опции возрастных групп — только те, что реально встречаются
// у участников ТЕКУЩЕЙ выбранной дистанции (у разных дистанций Жары —
// разные, несовпадающие схемы категорий, см. age_group_configs).
function populateAgeGroups(runners) {
    const ageGroupSelect = document.getElementById('ageGroupFilter');
    const genderFilter = getGenderFilterValue(); // Получаем выбранный пол
    const distanceFilter = document.getElementById('distanceFilter').value;
    const savedValue = ageGroupSelect.value;
    const ageGroups = new Set();

    runners.forEach(runner => {
        if (distanceFilter !== '' && (runner.distance || '') !== distanceFilter) return;
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

    // Фильтруем группы по выбранному полу — исключаем ТОЛЬКО явно
    // противоположный пол, а не "оставляем только явно совпадающий": у
    // Детского забега категории без деления по полу ("8 лет", без префикса
    // "М"/"Ж"/"мужчины"/"женщины") не матчат ни isMaleCategory, ни
    // isFemaleCategory — при "оставляем только явно совпадающий" такие
    // категории пропадали бы из списка целиком при ЛЮБОМ активном фильтре
    // пола, хотя они относятся к участникам обоих полов.
    let filteredGroups = Array.from(ageGroups);

    if (genderFilter === 'Мужчина') {
        filteredGroups = filteredGroups.filter(group => !KMUtils.isFemaleCategory(group));
    } else if (genderFilter === 'Женщина') {
        filteredGroups = filteredGroups.filter(group => !KMUtils.isMaleCategory(group));
    }

    // Сортируем группы в правильном порядке (женские сначала, затем мужские,
    // внутри — по возрасту; единая логика с сортировкой таблицы, см. KMUtils.categoryOrder)
    const sortedGroups = filteredGroups.sort((a, b) => KMUtils.categoryOrder(a) - KMUtils.categoryOrder(b));

    sortedGroups.forEach(group => {
        const option = document.createElement('option');
        option.value = group;
        option.textContent = group;
        ageGroupSelect.appendChild(option);
    });
    
    // Восстанавливаем значение: приоритет — значение из URL при первой
    // загрузке (once, см. readStateFromUrl), иначе текущее выбранное,
    // иначе "Все"
    const optionValues = Array.from(ageGroupSelect.options).map(opt => opt.value);
    if (_urlAgeGroup && optionValues.includes(_urlAgeGroup)) {
        ageGroupSelect.value = _urlAgeGroup;
        _urlAgeGroup = null;
    } else if (savedValue && optionValues.includes(savedValue)) {
        ageGroupSelect.value = savedValue;
    } else {
        // Если выбранное значение больше не доступно, выбираем "Все"
        ageGroupSelect.value = '';
    }
}

// Заполняем опции дистанций — без опции "Все": стартовый список
// просматривается по одной дистанции за раз (у разных дистанций одного
// события — разные схемы возрастных категорий/номеров, смешивать их в
// одной таблице неинформативно). По умолчанию выбирается максимальная
// доступная дистанция.
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

    // Сортируем дистанции по возрастанию — KMUtils.parseDistanceKm()
    // приводит к единому километровому масштабу (не голое parseInt: "500 м"
    // без учёта единицы измерения "больше" числа в "1 км")
    const sortedDistances = Array.from(distances).sort((a, b) => {
        const numA = KMUtils.parseDistanceKm(a);
        const numB = KMUtils.parseDistanceKm(b);
        if (numA !== numB) {
            return numA - numB;
        }
        // Если значения одинаковые, сортируем по строке
        return a.localeCompare(b, 'ru');
    });

    sortedDistances.forEach(distance => {
        const option = document.createElement('option');
        option.value = distance;
        option.textContent = distance;
        distanceSelect.appendChild(option);
    });

    // Восстанавливаем значение: приоритет — значение из URL при первой
    // загрузке (once, см. readStateFromUrl), иначе текущее выбранное,
    // иначе максимальная дистанция (последняя после сортировки по
    // возрастанию), не первая попавшаяся и не пустое значение.
    if (_urlDistance && sortedDistances.includes(_urlDistance)) {
        distanceSelect.value = _urlDistance;
        _urlDistance = null;
    } else if (savedValue && sortedDistances.includes(savedValue)) {
        distanceSelect.value = savedValue;
    } else if (sortedDistances.length > 0) {
        distanceSelect.value = sortedDistances[sortedDistances.length - 1];
    }
}

// Текущее значение пилюли пола: '' | 'Мужчина' | 'Женщина'
function getGenderFilterValue() {
    return document.getElementById('genderFilter').dataset.value || '';
}

// Устанавливает активную пилюлю пола БЕЗ побочных вызовов (onGenderChange/
// applyFilters) — нужна для программного сброса (switchEvent()), где
// пересчёт фильтров и так произойдёт позже через loadRunnersData() на
// новых данных; вызывать его здесь преждевременно (тот же принцип, что и
// обычное присваивание select.value, которое не вызывает onchange).
function _setGenderFilterActivePill(value) {
    const container = document.getElementById('genderFilter');
    container.dataset.value = value;
    container.querySelectorAll('.km-pill').forEach(pill => {
        pill.classList.toggle('active', pill.dataset.value === value);
    });
}

// Переключает активную пилюлю пола — вызывается по клику (эквивалент
// прежнего onchange у <select>).
function setGenderFilter(value) {
    _setGenderFilterActivePill(value);
    onGenderChange();
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
    const genderFilter = getGenderFilterValue();
    const distanceFilter = document.getElementById('distanceFilter').value;

    // Некоторые дистанции не разбиты на возрастные категории вообще (нет
    // брекетов в age_group_configs — напр. "2 км" Жары, "500 м" Детского
    // забега) — бэкенд отдаёт для них пустую category у ВСЕХ участников.
    // Смотрим на реальные данные текущей дистанции, а не на хардкод
    // конкретных строк дистанций — правило само подхватывает будущие
    // дистанции без категорий, без правки JS.
    const runnersOnDistance = allRunners.filter(r => (r.distance || '') === distanceFilter);
    const hideAgeGroup = runnersOnDistance.length > 0 && runnersOnDistance.every(r => !r.category);
    document.getElementById('ageGroupFilterGroup').style.display = hideAgeGroup ? 'none' : '';
    document.getElementById('startListTable').classList.toggle('km-table--hide-age-group', hideAgeGroup);
    if (hideAgeGroup) {
        document.getElementById('ageGroupFilter').value = '';
    }

    // "Номер" (стартовый номер/bib) — не в каждом импорте, показываем колонку
    // только если хоть у кого-то из загруженных участников есть значение
    // (проверяем по ВСЕМ участникам события, не только по отфильтрованным —
    // чтобы колонка не мигала при смене фильтров пола/дистанции/группы).
    const hasStartNumbers = allRunners.some(r => r.start_number);
    document.getElementById('startListTable').classList.toggle('km-table--show-start-number', hasStartNumbers);

    const ageGroupFilter = document.getElementById('ageGroupFilter').value;
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
    renderStartList(_sortArray(filteredRunners));

    // Обновляем заголовок (дистанция могла смениться)
    updatePageTitle();

    // Прямая ссылка на текущий вид (событие/год/дистанция/фильтры) в URL
    syncUrlFromState();
}

function _sortArray(arr) {
    if (!sortState.column) return arr;
    return [...arr].sort((a, b) => {
        let valA, valB;
        switch (sortState.column) {
            case 'index':
                valA = 0; valB = 0; break;
            case 'bib':
                valA = a.bib || 0;
                valB = b.bib || 0;
                break;
            case 'start_number':
                // Без номера — в конец списка при сортировке по возрастанию
                valA = a.start_number || Infinity;
                valB = b.start_number || Infinity;
                break;
            case 'surname':
                valA = (a.surname || '').toLowerCase();
                valB = (b.surname || '').toLowerCase();
                break;
            case 'name':
                valA = (a.name || '').toLowerCase();
                valB = (b.name || '').toLowerCase();
                break;
            case 'birthday': {
                const bdA = a.birthdate || a.birthday;
                const bdB = b.birthdate || b.birthday;
                valA = bdA ? new Date(bdA).getFullYear() : 0;
                valB = bdB ? new Date(bdB).getFullYear() : 0;
                break;
            }
            case 'distance':
                valA = KMUtils.parseDistanceKm(a.distance);
                valB = KMUtils.parseDistanceKm(b.distance);
                break;
            case 'sex':
                valA = (a.sex || '').toLowerCase();
                valB = (b.sex || '').toLowerCase();
                break;
            case 'category':
                valA = KMUtils.categoryOrder(a.category);
                valB = KMUtils.categoryOrder(b.category);
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
    renderStartList(_sortArray(filteredRunners));
}

// Отрисовываем таблицу стартового списка
function renderStartList(runners) {
    const tbody = document.getElementById('startListBody');
    tbody.innerHTML = '';
    
    runners.forEach((runner, index) => {
        const row = document.createElement('tr');
        row.className = 'km-tr';
        
        // Фамилия, имя
        let firstName = runner.name || 'N/A';
        let lastName = runner.surname || 'N/A';

        // Год рождения. "1900-01-01" — сентинел БД для "дата не указана"
        // (leads.birthday NOT NULL DEFAULT '1900-01-01'), не настоящий год.
        let birthYear = 'N/A';
        if (runner.birthday && !String(runner.birthday).startsWith('1900')) {
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
        
        // Возрастная категория. Пустая строка от бэкенда — легитимное "нет
        // брекета для этого возраста/дистанции" (не то же самое, что явное
        // "Неизвестно" — та строка приходит текстом при нераспознанной дате
        // рождения и сюда не попадает, т.к. уже truthy). "Ошибка возраста" —
        // границы для дистанции настроены, но возраст участника не попадает
        // ни в одну (непочищенная регистрация) — выделяем визуально.
        let category = runner.category || '—';
        let categoryTagClass = category === 'Ошибка возраста' ? 'age-group-tag age-group-tag--error' : 'age-group-tag';
        
        // Город, клуб - заменяем null, 'null' и N/A на пустую строку
        let city = (runner.city && runner.city.toLowerCase() !== 'n/a' && runner.city.toLowerCase() !== 'null') ? runner.city : '';
        let club = (runner.club && runner.club.toLowerCase() !== 'n/a' && runner.club.toLowerCase() !== 'null') ? runner.club : '';
        
        const rowBg = index % 2 === 0 ? 'km-td--even' : 'km-td--odd';
        let rowHTML = `
            <td class="km-td km-td--c ${rowBg}">${index + 1}</td>
            <td class="km-td km-td--c ${rowBg}">${runner.start_number || ''}</td>
            <td class="km-td km-td--l ${rowBg}"><div class="km-name-main">${lastName}</div></td>
            <td class="km-td km-td--l ${rowBg}"><div class="km-name-main">${firstName}</div></td>
            <td class="km-td km-td--c ${rowBg}">${birthYear}</td>
            <td class="km-td km-td--c ${rowBg}">${distance}</td>
            <td class="km-td km-td--c ${rowBg}"><span class="gender-tag ${genderClass}">${genderText}</span></td>
            <td class="km-td km-td--c ${rowBg}"><span class="${categoryTagClass}">${category}</span></td>
            <td class="km-td km-td--l ${rowBg}">${city}</td>
            <td class="km-td km-td--l ${rowBg}">${club}</td>
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

// Экспорт в PDF через браузерный print
function exportStartListPdf() {
    if (!filteredRunners.length) { alert('Нет данных для экспорта'); return; }
    const title = document.getElementById('pageTitle').innerText.replace(/\n/g, ' ');

    // Сортировка по фамилии, при совпадении — по имени
    const sorted = [...filteredRunners].sort((a, b) => {
        const s = (a.surname || '').localeCompare(b.surname || '', 'ru');
        return s !== 0 ? s : (a.name || '').localeCompare(b.name || '', 'ru');
    });

    // "Номер" — только если хоть у кого-то в выгрузке есть значение (см. тот
    // же принцип, что и колонка на самой странице, applyFilters())
    const showStartNumber = sorted.some(r => r.start_number);
    const numberCell = r => showStartNumber ? `<td>${r.start_number || ''}</td>` : '';
    const numberHeader = showStartNumber ? '<th>Номер</th>' : '';

    const rows = sorted.map((r, i) => {
        // "1900-01-01" — сентинел БД "дата не указана" (birthday необязателен
        // при импорте), не настоящий год рождения
        const bYear = (r.birthday && !String(r.birthday).startsWith('1900'))
            ? String(r.birthday).replace(/^(\d{4}).*/, '$1') : '—';
        return `<tr>
            <td>${i + 1}</td>
            ${numberCell(r)}
            <td>${r.surname || ''}</td>
            <td>${r.name || ''}</td>
            <td>${bYear}</td>
            <td>${r.distance || r.event_distance || '—'}</td>
            <td>${r.sex || '—'}</td>
            <td>${r.category || '—'}</td>
            <td>${r.city || '—'}</td>
        </tr>`;
    }).join('');
    const html = `<!DOCTYPE html><html><head><meta charset="UTF-8"><title>${title}</title>
<style>
  body{font-family:Arial,sans-serif;font-size:10px;margin:16px}
  h2{font-size:14px;margin:0 0 4px}
  p{font-size:9px;color:#666;margin:0 0 10px}
  table{border-collapse:collapse;width:100%}
  th,td{border:1px solid #bbb;padding:3px 6px;text-align:left}
  th{background:#222;color:#fff;font-size:9px;text-transform:uppercase}
  tr:nth-child(even){background:#f7f7f7}
  @page{margin:15mm}
</style></head><body>
<h2>${title}</h2>
<p>${sorted.length} участников · ${new Date().toLocaleDateString('ru-RU')}</p>
<table><thead><tr>
  <th>№</th>${numberHeader}<th>Фамилия</th><th>Имя</th><th>Год рожд.</th>
  <th>Дистанция</th><th>Пол</th><th>Возрастная группа</th><th>Город</th>
</tr></thead><tbody>${rows}</tbody></table>
<script>window.onload=()=>window.print();<\/script>
</body></html>`;
    const w = window.open('', '_blank');
    w.document.write(html);
    w.document.close();
}
