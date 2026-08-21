// legacy/static/analytics-results.js
// Javascript для страницы результатов забега
let allRunners = [];
let filteredRunners = [];
let sortState = { column: 'time_gun', direction: 'asc' }; // Дефолт: по официальному времени
let currentEvent = 'night_run';
let currentYear = new Date().getFullYear();
const timeMode = 'gun'; // фиксировано для сегментных функций
const runnerDataMap = new Map(); // resultId → runner object

// Раздел /athlete-profile временно скрыт (решение пользователя,
// 2026-08-21) — кнопка "Профиль" в панели деталей до его возвращения не
// показывается. Один флаг вместо закомментированного кода — включить
// обратно: PROFILE_BUTTON_ENABLED = true.
const PROFILE_BUTTON_ENABLED = false;

const eventNameMap = KMUtils.EVENT_NAMES;
const eventColorMap = KMUtils.EVENT_COLORS;

// ──────────────── Состояние в URL (прямая ссылка на конкретный
// событие+год+дистанцию+фильтры, напр. чтобы прислать ссылку на результаты
// конкретного забега) — тот же приём, что на /start-list, см.
// analytics-start-list.js readStateFromUrl()/syncUrlFromState().
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
    if (gender === 'Мужчина' || gender === 'Женщина') {
        document.getElementById('genderFilter').dataset.value = gender;
    }
    const search = params.get('search');
    if (search) document.getElementById('surnameSearch').value = search;
}

// Пишет текущие фильтры в query-параметры при каждом применении фильтров
// (history.replaceState — НЕ pushState, иначе каждый клик фильтра добавлял
// бы шаг в историю браузера вместо осмысленных переходов).
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

// «Жара» награждает по чистому времени, а не по официальному (решение
// оргкомитета, действует с 2026 года и далее) — единственное исключение
// среди событий Красмарафона. Сравниваем по внутреннему ключу события
// (не по отображаемому имени) — он не зависит от года.
function isZharaEvent() {
    return currentEvent === 'zhara';
}

// Расставляет заголовки+сортировку двух колонок времени в зависимости от
// события: для Жары чистое время идёт первым, для остальных — официальное.
function updateTimeColumnHeaders() {
    const th1 = document.getElementById('thTimeCol1');
    const th2 = document.getElementById('thTimeCol2');
    if (!th1 || !th2) return;
    const gun  = { label: 'Офиц. время',  key: 'time_gun' };
    const net  = { label: 'Чистое время', key: 'time_net' };
    const [first, second] = isZharaEvent() ? [net, gun] : [gun, net];
    th1.textContent = first.label;
    th1.setAttribute('onclick', `sortTable('${first.key}')`);
    th2.textContent = second.label;
    th2.setAttribute('onclick', `sortTable('${second.key}')`);
}

// Дефолтная сортировка при смене события — чистое время для Жары,
// официальное для остальных. Сбрасывается при каждой смене события/года,
// пользователь может дальше сортировать вручную кликом по заголовку.
function resetSortStateForEvent() {
    sortState = { column: isZharaEvent() ? 'time_net' : 'time_gun', direction: 'asc' };
    updateTimeColumnHeaders();
}

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
    'pervomay_2026': [142, 143],  // 5 км (142), 21.1 км (143)
    'dostigaya_tseli_2026': 152
};

// Последний год, для которого у события есть настроенный event_id
// (eventYearToIdMap) — прокси для "есть данные в БД", используется и как
// дефолт при первой загрузке страницы, и при смене события в селекторе.
function latestConfiguredYearForEvent(event) {
    const years = Object.keys(eventYearToIdMap)
        .filter(key => key.startsWith(`${event}_`))
        .map(key => parseInt(key.slice(event.length + 1), 10))
        .filter(y => !isNaN(y));
    return years.length ? Math.max(...years) : null;
}

// Инициализация страницы — дефолт: активный забег + последний год с
// данными, переопределяется параметрами URL, если открыли по прямой
// ссылке. Именованная функция (не анонимная в addEventListener) — чтобы её
// можно было вызвать напрямую из тестов (см. analytics-start-list.js).
async function initResultsPage() {
    populateYearSelector();
    readStateFromUrl();
    try {
        const cfg = await fetch('/api/current-event').then(r => r.json());
        currentEvent = _urlEvent || cfg.event || 'night_run';
        const cfgYear = cfg.year || new Date().getFullYear();
        currentYear = _urlYear || latestConfiguredYearForEvent(currentEvent) || cfgYear;
    } catch {
        currentEvent = _urlEvent || 'night_run';
        currentYear  = _urlYear || (new Date().getFullYear() - 1);
    }
    document.getElementById('eventResultsSelector').value = currentEvent;
    document.getElementById('yearResultsSelector').value  = currentYear;
    updateEventThemeColor();
    updateEventBanner();
    updatePageTitle();
    resetSortStateForEvent();
    loadRunnersData();

    new SSEClient('/api/sse/notify', {
        results_updated: (msg) => {
            const eventIds = eventYearToIdMap[`${currentEvent}_${currentYear}`];
            const ids = Array.isArray(eventIds) ? eventIds : [eventIds];
            if (!msg.event_id || ids.includes(msg.event_id)) loadRunnersData(true);
        }
    });
}
document.addEventListener('DOMContentLoaded', initResultsPage);

document.addEventListener('click', e => {
    const tab = e.target.closest('.detail-tab');
    if (!tab) return;
    const panel = tab.closest('td');
    panel.querySelectorAll('.detail-tab').forEach(t => t.classList.toggle('active', t === tab));
    panel.querySelectorAll('.detail-tab-pane').forEach(p =>
        p.classList.toggle('active', p.dataset.pane === tab.dataset.tab)
    );
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

    // +1 чтобы включать следующий год (предрегистрация на будущие события)
    for (let year = currentYear + 1; year >= 2020; year--) {
        const option = document.createElement('option');
        option.value = year;
        option.textContent = year;
        yearSelector.appendChild(option);
    }
    
    // Устанавливаем текущий год по умолчанию
    yearSelector.value = currentYear;
}

// Функция переключения события и года. trigger различает, какой селектор
// вызвал смену ('event'/'year') — год автоматически переключается на
// последний доступный ТОЛЬКО при смене события, ручной выбор года не
// перебивается.
async function switchEventResults(trigger) {
    currentEvent = document.getElementById('eventResultsSelector').value;
    const yearSel = document.getElementById('yearResultsSelector');

    if (trigger === 'event') {
        const latestYear = latestConfiguredYearForEvent(currentEvent);
        currentYear = latestYear || parseInt(yearSel.value);
        if (latestYear) yearSel.value = latestYear;
    } else {
        currentYear = parseInt(yearSel.value);
    }

    // Обновляем цвет темы
    updateEventThemeColor();

    // Меняем фоновую картинку баннера события
    updateEventBanner();

    // Обновляем заголовок страницы
    updatePageTitle();

    // Дефолтная сортировка + заголовки колонок под новое событие
    resetSortStateForEvent();

    // Перезагружаем данные
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
    title.innerHTML = `Результаты<br><span class="page-title-event"${subtitleStyle}>${subtitle}</span>`;
    const bannerTitle = document.getElementById('eventBannerTitle');
    if (bannerTitle) bannerTitle.textContent = subtitle;
}

// Видимость серого подзаголовка под h1 зависит от того, показан ли баннер
// (проверяется асинхронной загрузкой картинки — см. updateEventBanner).
// Флаг общий с updatePageTitle(): рендер результатов дёргает updatePageTitle()
// уже ПОСЛЕ завершения загрузки баннера (порядок не гарантирован), поэтому
// решение "показывать ли подзаголовок" нельзя принимать только в момент
// onload/onerror картинки — оно должно применяться и при каждой
// пересборке заголовка через innerHTML.
let _eventBannerVisible = false;

// Декоративный баннер события над тулбаром — показывается ТОЛЬКО если для
// события реально есть фото в static/images/events/ (не у всех событий оно
// есть). Наличие проверяется загрузкой картинки в браузере (Image()
// onload/onerror), а не хардкод-списком — новое фото подхватится само.
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
            console.log('Загрузка результатов из БД через API');
            
            // Если это массив дистанций (для Жары), загружаем все вместе
            const eventIds = Array.isArray(eventIdOrIds) ? eventIdOrIds : [eventIdOrIds];
            
            for (const eventId of eventIds) {
                const response = await fetch(`/api/event-results?event_id=${eventId}`);
                
                if (!response.ok) {
                    throw new Error(`Ошибка загрузки результатов для event_id=${eventId}`);
                }
                
                const data = await response.json();
                console.log(`Загружено из БД (event_id=${eventId}):`, data.results ? data.results.length : 0, 'участников');
                // event_id не приходит в самих результатах (только в query
                // параметре запроса) — событий-групп с несколькими
                // дистанциями (Жара/Первомай/Достигая цели) объединяют
                // несколько event_id в один allRunners, поэтому привязку
                // нужно проставить здесь, до конкатенации, иначе после
                // merge её не восстановить (нужна для ссылки на диплом).
                rawData = rawData.concat((data.results || []).map(r => ({ ...r, event_id: eventId })));
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
        populateGenderFilter(allRunners);
        populateAgeGroups(allRunners);
        populateDistances(allRunners);

        applyFilters();
        if (!silent) {
            showLoading(false);
            document.getElementById('resultsWrapper').style.display = '';
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
            event_id: runner.event_id,

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
    if (lowerStatus.includes('notstarted') || lowerStatus.includes('not start')) return 'notstarted';
    if (lowerStatus.includes('running') || lowerStatus.includes('started')) return 'running';
    if (lowerStatus.includes('withdraw')) return 'disqualified';
    if (lowerStatus.includes('disqualif')) return 'disqualified';
    
    return 'notstarted';
}


// Пилюли пола — только те, что реально встречаются у участников (напр. на
// "Женской семёрке" мужчин нет вообще, не показываем такой вариант).
// genderFilter — контейнер <div>, а не <select>: активное значение хранится
// в data-value, читается через getGenderFilterValue().
function populateGenderFilter(runners) {
    const container = document.getElementById('genderFilter');
    const savedValue = container.dataset.value || '';

    const genders = new Set();
    runners.forEach(runner => {
        if (runner.gender) genders.add(runner.gender);
    });

    // Женщина раньше Мужчины — соответствует порядку в остальном UI
    const order = { 'Женщина': 0, 'Мужчина': 1 };
    const sortedGenders = Array.from(genders).sort((a, b) => (order[a] ?? 99) - (order[b] ?? 99));
    const values = ['', ...sortedGenders];
    const newValue = values.includes(savedValue) ? savedValue : '';

    // Значение фильтра (data-value/сравнения с runner.gender) остаётся
    // "Мужчина"/"Женщина" — меняется только отображаемый текст пилюли,
    // тот же приём, что уже используется в tracker-api.js для кнопок пола.
    const labels = { 'Женщина': 'Женщины', 'Мужчина': 'Мужчины' };
    container.innerHTML = '';
    values.forEach(value => {
        const pill = document.createElement('button');
        pill.type = 'button';
        pill.className = 'km-pill' + (value === newValue ? ' active' : '');
        pill.textContent = value ? (labels[value] || value) : 'Все';
        pill.addEventListener('click', () => setGenderFilter(value));
        container.appendChild(pill);
    });
    container.dataset.value = newValue;
}

// Текущее значение пилюли пола: '' | 'Мужчина' | 'Женщина'
function getGenderFilterValue() {
    return document.getElementById('genderFilter').dataset.value || '';
}

// Переключает активную пилюлю пола — вызывается по клику (эквивалент
// прежнего onchange у <select>). Дальнейший ре-рендер пилюль (с уже
// правильным активным значением) происходит внутри applyFilters() →
// populateGenderFilter(allRunners), как и раньше для select.
function setGenderFilter(value) {
    document.getElementById('genderFilter').dataset.value = value;
    onGenderChange();
}

// Заполняем опции возрастных групп
function populateAgeGroups(runners) {
    const ageGroupSelect = document.getElementById('ageGroupFilter');
    const genderFilter = getGenderFilterValue(); // Получаем выбранный пол
    const savedValue = ageGroupSelect.value;

    // Категория → множество полов, которым она реально встречается у участников.
    // Формат строки category не унифицирован между событиями ("Ж 49" / "женщины
    // до 49 лет" / "Мужчины 30-39"), поэтому определяем пол категории по факту
    // (runner.gender уже нормализован одинаково везде), а не парсингом строки.
    const categoryGenders = new Map();
    runners.forEach(runner => {
        const cat = runner.category || runner.age_group || runner['Возрастная категория'];
        if (!cat) return;
        if (!categoryGenders.has(cat)) categoryGenders.set(cat, new Set());
        if (runner.gender) categoryGenders.get(cat).add(runner.gender);
    });

    // Очищаем текущие опции
    ageGroupSelect.innerHTML = '';

    // Добавляем опцию "Все" первой
    const allOption = document.createElement('option');
    allOption.value = '';
    allOption.textContent = 'Все';
    ageGroupSelect.appendChild(allOption);

    // Фильтруем группы по выбранному полу
    let filteredGroups = Array.from(categoryGenders.keys());

    if (genderFilter) {
        filteredGroups = filteredGroups.filter(group => categoryGenders.get(group).has(genderFilter));
    }
    
    // Порядок возраста — первое число в названии категории, по возрастанию.
    // Раньше был список regex под конкретные диапазоны ("49"/"50-59"/...) —
    // не покрывал детские категории Жары ("Ж12-13"/"Ж14-15"/"Ж16-17", все
    // падали в один "прочее"-бакет и шли в произвольном порядке) и путал
    // "75-79"/"80+" (оба матчили одно и то же правило). Числовое извлечение
    // работает для любого формата без хардкода границ конкретного события —
    // тот же приём, что уже в KMUtils.categoryOrder() на /start-list.
    const ageGroupOrder = cat => {
        const m = cat.match(/\d+/);
        return m ? parseInt(m[0], 10) : 999;
    };

    // Сортируем группы в правильном порядке
    const sortedGroups = filteredGroups.sort((a, b) => {
        // Если пол не выбран - женские группы в начало, потом мужские
        if (!genderFilter) {
            const aIsFemale = categoryGenders.get(a).has('Женщина');
            const bIsFemale = categoryGenders.get(b).has('Женщина');

            if (aIsFemale && !bIsFemale) return -1;
            if (!aIsFemale && bIsFemale) return 1;
        }

        return ageGroupOrder(a) - ageGroupOrder(b);
    });
    
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

    // "Все" не даём выбрать: rank_absolute/rank_sex/rank_category считаются
    // отдельно на каждую дистанцию (event_id) — при смешении дистанций места
    // задваиваются и теряют смысл. Дистанция должна быть выбрана всегда.

    // Сортируем дистанции по возрастанию
    const sortedDistances = Array.from(distances).sort((a, b) => {
        // Извлекаем числовое значение для сортировки
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
    // иначе первая дистанция по умолчанию
    if (_urlDistance && sortedDistances.includes(_urlDistance)) {
        distanceSelect.value = _urlDistance;
        _urlDistance = null;
    } else if (savedValue && sortedDistances.includes(savedValue)) {
        distanceSelect.value = savedValue;
    } else if (sortedDistances.length > 0) {
        distanceSelect.value = sortedDistances[0];
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
    const genderFilter = getGenderFilterValue();
    const ageGroupFilter = document.getElementById('ageGroupFilter').value;
    const distanceFilter = document.getElementById('distanceFilter').value;
    const surnameSearch = document.getElementById('surnameSearch').value.toLowerCase().trim();
    
    console.log('Применение фильтров:', { genderFilter, ageGroupFilter, distanceFilter, surnameSearch, totalRunners: allRunners.length });
    
    // Числовой запрос — поиск по стартовому номеру, иначе — по фамилии с начала строки
    const isNumericSearch = /^\d+$/.test(surnameSearch);

    filteredRunners = allRunners.filter(runner => {
        if (surnameSearch !== '') {
            if (isNumericSearch) {
                if (!String(runner.start_number).includes(surnameSearch)) {
                    return false;
                }
            } else {
                const runnerSurname = (runner.surname || '').toLowerCase();
                if (!runnerSurname.startsWith(surnameSearch)) {
                    return false;
                }
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
    populateGenderFilter(allRunners);
    populateAgeGroups(allRunners);
    populateDistances(allRunners);
    
    document.getElementById('resultsWrapper').style.display = '';
    renderResultsTable(_sortArray(filteredRunners));

    // Обновляем заголовок (дистанция могла смениться)
    updatePageTitle();

    // Прямая ссылка на текущий вид (событие/год/дистанция/фильтры) в URL
    syncUrlFromState();
}

const formatTime = KMUtils.formatTime.bind(KMUtils);
const calculatePace = KMUtils.calculatePace.bind(KMUtils);

// Место должно пересчитываться под активные фильтры пол/возрастная группа —
// сервер уже присылает все три варианта (rank_absolute/rank_sex/rank_category),
// каждый посчитан отдельно на дистанцию (event_id). Возрастная группа в этой
// системе уже включает пол ("женщины до 49 лет"), поэтому при активном
// фильтре по группе rank_category достаточен сам по себе.
// Для Жары берём _clean-варианты — награждение там по чистому времени.
function getActiveRankField() {
    const genderFilter = getGenderFilterValue();
    const ageGroupFilter = document.getElementById('ageGroupFilter').value;
    const suffix = isZharaEvent() ? '_clean' : '';
    if (ageGroupFilter !== '') return 'rank_category' + suffix;
    if (genderFilter !== '') return 'rank_sex' + suffix;
    return 'rank_absolute' + suffix;
}

// Применяет текущий sortState к массиву, возвращает отсортированную копию
function _sortArray(arr) {
    if (!sortState.column) return arr;
    const pri = s => s === 'finished' ? 0 : s === 'running' ? 1 : s === 'notstarted' ? 3 : 2;
    return [...arr].sort((a, b) => {
        let valA, valB;
        switch (sortState.column) {
            case 'rank': {
                const rankField = getActiveRankField();
                valA = a[rankField] || 9999;
                valB = b[rankField] || 9999;
                break;
            }
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

    const rankField = getActiveRankField();

    runners.forEach((runner, index) => {
        const row = document.createElement('tr');
        row.className = 'km-tr';

        const rankAbs = runner[rankField];
        let rankDisplay;
        if (rankAbs === 1) rankDisplay = `<span class="km-rank-medal km-rank-medal--1">1</span>`;
        else if (rankAbs === 2) rankDisplay = `<span class="km-rank-medal km-rank-medal--2">2</span>`;
        else if (rankAbs === 3) rankDisplay = `<span class="km-rank-medal km-rank-medal--3">3</span>`;
        else rankDisplay = rankAbs ? `<span class="km-rank-num">${rankAbs}</span>` : '—';

        const fullName = `${runner.surname || ''} ${runner.name || ''}`.trim() || 'N/A';
        const timeGunCell = `<span class="km-time-gun">${formatTime(runner.time_gun_finish) || '—'}</span>`;
        const timeNetCell = `<span class="km-time-net">${formatTime(runner.time_clear_finish) || '—'}</span>`;
        const [timeCol1, timeCol2] = isZharaEvent() ? [timeNetCell, timeGunCell] : [timeGunCell, timeNetCell];
        const rowBg = index % 2 === 0 ? 'km-td--even' : 'km-td--odd';

        row.innerHTML = `
            <td class="km-td ${rowBg}">${rankDisplay}</td>
            <td class="km-td ${rowBg}"><span class="km-bib">${runner.start_number || ''}</span></td>
            <td class="km-td km-td--l ${rowBg}"><div class="km-name-main">${fullName}</div></td>
            <td class="km-td ${rowBg}">${timeCol1}</td>
            <td class="km-td ${rowBg}">${timeCol2}</td>
        `;

        const resultId = String(runner.id || '');
        row.dataset.resultId = resultId;

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
        'start': '',
        'kt1': '',
        'kt2': '',
        'kt3': '',
        'kt4': '',
        'kt5': '',
        'kt6': '',
        'kt7': '',
        'finish': ''
    };

    const mainPart = code.split('-')[0];
    return icons[mainPart] || '';
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
    const distance = runner.event || runner.distance || '';
    let birthYear = '';
    if (runner.birthdate) {
        const y = new Date(runner.birthdate).getFullYear();
        if (y > 1900) birthYear = y;
    }
    // Полное слово в шапке карточки ("Мужчина"/"Женщина") — сокращение
    // "М"/"Ж" (genderShort) оставлено для компактных мест по полу ниже
    // ("М 5"/"Ж 12"), там развёрнутое слово не поместится.
    // Категория — раньше нигде не показывалась в результатах, хотя место
    // по категории уже есть в самой карточке ("По кат." ниже).
    const metaParts = [distance, runner.gender || '', birthYear ? `${birthYear} г.р.` : '', runner.category || '']
        .filter(Boolean);

    const timeGun = formatTime(runner.time_gun_finish) || '—';
    const timeNet = formatTime(runner.time_clear_finish) || '—';
    const paceGunRaw = KMUtils.parseDuration(runner.finish_pace_avg_gun || runner.finish_pace_avg);
    const paceNetRaw = KMUtils.parseDuration(runner.finish_pace_avg_clean || runner.finish_pace_avg);
    const paceGun = (paceGunRaw && paceGunRaw !== '#ЗНАЧ!') ? paceGunRaw + ' мин/км' : '—';
    const paceNet = (paceNetRaw && paceNetRaw !== '#ЗНАЧ!') ? paceNetRaw + ' мин/км' : '—';

    const statusMap = { finished: 'Финишировал', running: 'Бежит', notstarted: 'Не стартовал', disqualified: 'Нарушение' };
    const status = statusMap[runner.status] || runner.status || '—';

    // Ranks with X/N suffix when race is complete
    const { raceComplete } = getRaceStats();
    const nAll = raceComplete ? allRunners.filter(r => r.status === 'Finished').length : null;
    const nSex = raceComplete ? allRunners.filter(r => r.status === 'Finished' && r.gender === runner.gender).length : null;
    const nCat = raceComplete ? allRunners.filter(r => r.status === 'Finished' && r.category === runner.category).length : null;
    const fmtRank = (rank, total) => {
        if (!rank) return '—';
        return total ? `${rank}/${total}` : `#${rank}`;
    };
    const rankAbs      = fmtRank(runner.rank_absolute,       nAll);
    const rankSex      = runner.rank_sex      ? `${genderShort} ${fmtRank(runner.rank_sex,      nSex)}` : '—';
    const rankCat      = runner.rank_category ? fmtRank(runner.rank_category, nCat) : '—';
    const rankAbsClean = fmtRank(runner.rank_absolute_clean, nAll);
    const rankSexClean = runner.rank_sex_clean      ? `${genderShort} ${fmtRank(runner.rank_sex_clean,      nSex)}` : '—';
    const rankCatClean = runner.rank_category_clean ? fmtRank(runner.rank_category_clean, nCat) : '—';

    const profileUrl = `/athlete-profile?surname=${encodeURIComponent(runner.surname || '')}&name=${encodeURIComponent(runner.name || '')}`;
    const profileBtn = PROFILE_BUTTON_ENABLED
        ? `<a href="${profileUrl}" class="km-btn-profile" target="_blank">Профиль</a>`
        : '';

    // DIPLOMA_EVENT_IDS — глобальный Set из results.html (event_id, для
    // которых вообще настроен diploma-конфиг). event_id проставляется на
    // runner при загрузке (см. loadRunnersData) — без него, как и без
    // start_number, ссылка на /diploma/{event_id}/{bib} была бы битой.
    const hasDiploma = runner.status === 'finished' && runner.event_id && runner.start_number
        && typeof DIPLOMA_EVENT_IDS !== 'undefined' && DIPLOMA_EVENT_IDS.has(runner.event_id);
    const diplomaBtn = hasDiploma
        ? `<a href="/diploma/${runner.event_id}/${runner.start_number}" class="km-btn-profile" target="_blank">🏅 Диплом</a>`
        : '';

    const timeCol = (title, time, cls, pace, absR, sexR, catR) => `
        <div class="detail-time-col detail-time-col--${cls}">
            <div class="detail-time-col-title">${title}</div>
            <div class="detail-time-big detail-time-big--${cls}">${time}</div>
            <div class="detail-rank-row"><span class="detail-rank-label">Темп</span><span class="detail-rank-val">${pace}</span></div>
            <div class="detail-rank-row"><span class="detail-rank-label">Место абс.</span><span class="detail-rank-val"><span class="detail-rank-num">${absR}</span></span></div>
            <div class="detail-rank-row"><span class="detail-rank-label">По полу</span><span class="detail-rank-val">${sexR}</span></div>
            <div class="detail-rank-row"><span class="detail-rank-label">По кат.</span><span class="detail-rank-val">${catR}</span></div>
        </div>`;

    return `
    <div class="detail-panel-header">
        <div>
            <div class="detail-name-row">
                <span class="detail-panel-name">${fullName}</span>
                ${profileBtn}
                ${diplomaBtn}
            </div>
            <div class="detail-panel-meta">${metaParts.join(' · ')} · ${status}</div>
        </div>
        <div class="detail-panel-actions">
            <button class="detail-panel-close" title="Закрыть">&times;</button>
        </div>
    </div>
    <div class="detail-tabs">
        <button class="detail-tab active" data-tab="times">Время и место</button>
        <button class="detail-tab" data-tab="pace">График темпа</button>
        <button class="detail-tab" data-tab="segments">Сегменты</button>
    </div>
    <div class="detail-tab-pane active" data-pane="times">
        <div class="detail-times-grid">
            ${isZharaEvent() ? `
            ${timeCol('ЧИСТОЕ ВРЕМЯ', timeNet, 'net', paceNet, rankAbsClean, rankSexClean, rankCatClean)}
            ${timeCol('ОФИЦИАЛЬНОЕ ВРЕМЯ', timeGun, 'gun', paceGun, rankAbs, rankSex, rankCat)}
            ` : `
            ${timeCol('ОФИЦИАЛЬНОЕ ВРЕМЯ', timeGun, 'gun', paceGun, rankAbs, rankSex, rankCat)}
            ${timeCol('ЧИСТОЕ ВРЕМЯ', timeNet, 'net', paceNet, rankAbsClean, rankSexClean, rankCatClean)}
            `}
        </div>
    </div>
    <div class="detail-tab-pane" data-pane="pace">
        <div class="detail-chart-section">
            <div class="detail-section-title">График темпа по отрезкам</div>
            <div class="detail-chart-canvas-wrap"><canvas class="pace-chart-canvas"></canvas></div>
        </div>
    </div>
    <div class="detail-tab-pane" data-pane="segments">
        <div class="detail-splits-section">
            <div class="detail-section-title">Сегменты и сплиты</div>
            <div class="segments-placeholder segs-placeholder">Загрузка...</div>
        </div>
    </div>`;
}

/**
 * Загружает сегменты и вставляет таблицу вместо заглушки
 */
async function loadSegmentsIntoPanel(cell, resultId) {
    const segPlaceholder = cell.querySelector('.segs-placeholder');
    try {
        const resp = await fetch(`/api/result-segments?result_id=${resultId}`);
        if (!resp.ok) throw new Error(`Ошибка сервера: ${resp.status}`);
        const segments = await resp.json();

        if (!segments.length) {
            const paceCanvas = cell.querySelector('canvas.pace-chart-canvas');
            if (paceCanvas) paceCanvas.closest('.detail-chart-canvas-wrap').innerHTML =
                '<div style="color:#aaa;font-size:13px;padding:8px 0;text-align:center">Данные КТ не найдены</div>';
            if (segPlaceholder) segPlaceholder.textContent = 'Данные КТ не найдены';
            return;
        }

        const consecutive = filterConsecutiveSegments(segments);
        const splits       = filterSplitSegments(segments);
        const kmMap        = buildKmMap(segments);

        // Рендер графика темпа прямо на canvas, встроенный в HTML
        const paceCanvas = cell.querySelector('canvas.pace-chart-canvas');
        if (paceCanvas) renderPaceChart(consecutive, kmMap, paceCanvas);

        const segsPane = cell.querySelector('[data-pane="segments"] .detail-splits-section');
        if (segPlaceholder) segPlaceholder.remove();
        if (segsPane) {
            try {
                renderSegmentSection(segsPane, 'Отрезки', '#e63946', consecutive, kmMap);
                renderSegmentSection(segsPane, 'Сплиты от старта', '#4a9eff', splits, kmMap);
            } catch (segErr) {
                console.error('Ошибка renderSegmentSection:', segErr);
                segsPane.insertAdjacentHTML('beforeend',
                    `<div style="color:#c0392b;font-size:13px;padding:8px 0">Ошибка отрезков: ${segErr.message}</div>`);
            }
        }
    } catch (e) {
        console.error('Ошибка loadSegmentsIntoPanel:', e);
        const errMsg = `Ошибка загрузки КТ: ${e.message}`;
        const paceCanvas = cell.querySelector('canvas.pace-chart-canvas');
        if (paceCanvas) paceCanvas.closest('.detail-chart-canvas-wrap').innerHTML =
            `<div style="color:#c0392b;font-size:13px;padding:8px 0;text-align:center">${errMsg}</div>`;
        if (segPlaceholder) segPlaceholder.textContent = errMsg;
        else {
            const segsPane = cell.querySelector('[data-pane="segments"]');
            if (segsPane) segsPane.insertAdjacentHTML('beforeend',
                `<div style="color:#c0392b;font-size:13px;padding:8px 0">${errMsg}</div>`);
        }
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

const KT_ORDER = ['start', 'kt1', 'kt2', 'kt3', 'kt4', 'kt5', 'kt6', 'kt7', 'finish'];

/**
 * Разбирает сегментный код "start-kt1" → {from: 'start', to: 'kt1'}
 */
function parseSegmentCode(code) {
    const idx = code.lastIndexOf('-');
    if (idx < 0) return { from: code, to: '' };
    return { from: code.slice(0, idx), to: code.slice(idx + 1) };
}

/**
 * Конвертирует время/темп в секунды. Обрабатывает ISO 8601 PT-строки (timedelta от FastAPI),
 * HH:MM:SS строки, MM:SS строки и числа (float total_seconds).
 */
function toTotalSec(val) {
    if (!val && val !== 0) return null;
    if (typeof val === 'number') return val;
    if (typeof val !== 'string') return null;
    if (val.startsWith('PT')) {
        const m = val.match(/PT(?:(\d+)H)?(?:(\d+)M)?(?:(\d+(?:\.\d+)?)S)?/);
        if (!m) return null;
        return parseInt(m[1]||0)*3600 + parseInt(m[2]||0)*60 + Math.floor(parseFloat(m[3]||0));
    }
    const parts = val.split(':').map(Number);
    if (parts.length === 3) return parts[0]*3600 + parts[1]*60 + parts[2];
    if (parts.length === 2) return parts[0]*60 + parts[1];
    return null;
}

/**
 * Строит карту { 'start': 0, 'kt1': 3.0, 'kt2': 5.3, ..., 'finish': 21.1 }
 * Вычисляет to_km = time_sec / pace_sec_per_km.
 * Если данных нет — ключ отсутствует.
 */
function buildKmMap(segments) {
    const map = { start: 0 };

    // Pass 1: km-позиции от 'start-*' сплитов
    for (const seg of segments) {
        const { from, to } = parseSegmentCode(seg.segment_code);
        if (from !== 'start') continue;
        const timeSec = toTotalSec(seg.sg_time_clear || seg.sg_time_gun);
        const paceSec = toTotalSec(seg.sg_pace_avg || seg.sg_pace_avg_gun);
        if (timeSec && paceSec) map[to] = Math.round((timeSec / paceSec) * 10) / 10;
    }

    // Pass 2: дополняем из последовательных сегментов
    let changed = true;
    while (changed) {
        changed = false;
        for (const seg of segments) {
            const { from, to } = parseSegmentCode(seg.segment_code);
            if (!(from in map) || to in map) continue;
            const timeSec = toTotalSec(seg.sg_time_clear || seg.sg_time_gun);
            const paceSec = toTotalSec(seg.sg_pace_avg || seg.sg_pace_avg_gun);
            if (timeSec && paceSec) {
                map[to] = Math.round((map[from] + timeSec / paceSec) * 10) / 10;
                changed = true;
            }
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
 * Смежность определяется по фактическому набору КТ участника,
 * поэтому гонки с <7 КТ (например, 5 км с одним kt1) работают корректно.
 */
function filterConsecutiveSegments(segments) {
    // Собираем уникальные КТ, для которых есть данные
    const ktsWithData = new Set();
    for (const seg of segments) {
        if (!(seg.sg_time_clear || seg.sg_time_gun)) continue;
        const { from, to } = parseSegmentCode(seg.segment_code);
        if (KT_ORDER.includes(from)) ktsWithData.add(from);
        if (KT_ORDER.includes(to)) ktsWithData.add(to);
    }
    // Сортируем по позиции в KT_ORDER
    const sortedKts = [...ktsWithData].sort(
        (a, b) => KT_ORDER.indexOf(a) - KT_ORDER.indexOf(b)
    );
    // Сегмент считается последовательным, если from→to — соседи в фактическом наборе КТ
    return segments.filter(seg => {
        const { from, to } = parseSegmentCode(seg.segment_code);
        if (!(seg.sg_time_clear || seg.sg_time_gun)) return false;
        const fi = sortedKts.indexOf(from);
        const ti = sortedKts.indexOf(to);
        return fi >= 0 && ti === fi + 1;
    }).sort((a, b) => {
        const ai = sortedKts.indexOf(parseSegmentCode(a.segment_code).from);
        const bi = sortedKts.indexOf(parseSegmentCode(b.segment_code).from);
        return ai - bi;
    });
}

/**
 * Возвращает сплиты от старта: start→kt1, start→kt2, ..., start→finish.
 * Только сегменты с данными. Отсортированы по to_km (по to в KT_ORDER).
 */
function filterSplitSegments(segments) {
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

/**
 * Рендерит бар-чарт темпа по последовательным отрезкам.
 * Цвет и высота — относительная шкала per-participant.
 * @param {Array} consecutive — результат filterConsecutiveSegments()
 * @param {Object} kmMap — результат buildKmMap()
 * @returns {HTMLElement|null} — контейнер чарта или null если нечего показать
 */
function renderPaceChart(consecutive, kmMap, canvas) {
    if (!consecutive || !consecutive.length) return null;
    if (typeof Chart === 'undefined') return null;
    const useGun = typeof timeMode !== 'undefined' ? timeMode === 'gun' : true;
    const rangeLabels = [], values = [], colors = [], topLabels = [], paceStrs = [];

    consecutive.forEach(seg => {
        const paceStr = useGun ? (seg.sg_pace_avg_gun || seg.sg_pace_avg) : seg.sg_pace_avg;
        if (!paceStr) return;
        const secs = toTotalSec(paceStr);
        if (!secs) return;

        const { from, to } = parseSegmentCode(seg.segment_code);
        const fromKm = kmMap && kmMap[from] !== undefined ? kmMap[from] : null;
        const toKm   = kmMap && kmMap[to]   !== undefined ? kmMap[to]   : null;
        const rangeLabel = (fromKm !== null && toKm !== null)
            ? `${fromKm}–${toKm} км`
            : (seg.segment_code || '?');

        const rawTime = useGun ? (seg.sg_time_gun || seg.sg_time_clear) : seg.sg_time_clear;
        const timeStr = formatTime(rawTime) || '—';

        const paceMin = secs / 60;
        const pm = Math.floor(paceMin);
        const ps = Math.round((paceMin - pm) * 60);

        rangeLabels.push(rangeLabel);
        values.push(parseFloat(paceMin.toFixed(2)));
        const segDist = (fromKm !== null && toKm !== null) ? toKm - fromKm : null;
        topLabels.push({ time: timeStr, dist: segDist !== null ? `${segDist} км` : '' });
        paceStrs.push(`${pm}:${String(ps).padStart(2, '0')} мин/км`);
    });
    if (!values.length) return null;

    const avg = values.reduce((a, b) => a + b, 0) / values.length;
    values.forEach(v => colors.push(v <= avg ? 'rgba(39,174,96,0.75)' : 'rgba(238,45,98,0.75)'));

    const target = canvas || document.createElement('canvas');
    Chart.getChart(target)?.destroy();

    const topLabelPlugin = {
        id: 'kmTopLabels',
        afterDatasetsDraw(chart) {
            const ctx = chart.ctx;
            const meta = chart.getDatasetMeta(0);
            ctx.save();
            ctx.textAlign = 'center';
            meta.data.forEach((bar, i) => {
                const x = bar.x;
                const top = bar.y;
                ctx.font = 'bold 11px "Courier New", monospace';
                ctx.fillStyle = '#222';
                ctx.fillText(topLabels[i].time, x, top - 14);
                ctx.font = '10px Arial, sans-serif';
                ctx.fillStyle = '#666';
                ctx.fillText(topLabels[i].dist, x, top - 3);
            });
            ctx.restore();
        }
    };

    new Chart(target, {
        type: 'bar',
        data: {
            labels: rangeLabels,
            datasets: [{
                data: values,
                backgroundColor: colors,
                borderColor: colors.map(c => c.replace('0.75', '1')),
                borderWidth: 2,
                borderRadius: 6
            }]
        },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            layout: { padding: { top: 32 } },
            plugins: {
                legend: { display: false },
                tooltip: { callbacks: { label: ctx => {
                    const sec = Math.round(ctx.raw * 60);
                    const m = Math.floor(sec / 60);
                    const s = sec % 60;
                    return `Темп: ${m}:${String(s).padStart(2, '0')}/км`;
                }}}
            },
            scales: {
                y: {
                    ticks: { callback: val => {
                        const m = Math.floor(val);
                        const s = Math.round((val - m) * 60);
                        return `${m}:${String(s).padStart(2, '0')}`;
                    }, font: { size: 11 } },
                    grid: { color: '#f0f0f0' }
                },
                x: {
                    grid: { display: false },
                    ticks: {
                        callback: (val, idx) => [paceStrs[idx], rangeLabels[idx]],
                        font: { size: 10 }
                    }
                }
            }
        },
        plugins: [topLabelPlugin]
    });
    return canvas ? null : target;
}

function renderSegmentSection(container, title, color, rows, kmMap) {
    if (!rows.length) return;
    const useGun = timeMode === 'gun';
    const modeLabel = useGun ? 'офиц.' : 'чист.';
    const segKmName = code => {
        const { from, to } = parseSegmentCode(code);
        const fk = kmMap && kmMap[from] != null ? kmMap[from] : null;
        const tk = kmMap && kmMap[to]   != null ? kmMap[to]   : null;
        return (fk !== null && tk !== null) ? `${fk}–${tk} км` : formatSegmentName(code);
    };

    const header = document.createElement('div');
    header.className = 'segment-section-header';
    header.style.color = color;
    header.textContent = title;
    container.appendChild(header);

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
    rows.forEach((segment, i) => {
        const prevSegment = i > 0 ? rows[i - 1] : null;
        const code = segment.segment_code || '-';
        const time = formatTime(useGun ? (segment.sg_time_gun || segment.sg_time_clear) : segment.sg_time_clear) || '-';
        const pace = formatSegmentPace(useGun ? (segment.sg_pace_avg_gun || segment.sg_pace_avg) : segment.sg_pace_avg);
        const rankAbsolute = useGun ? (segment.sg_rank_absolute_gun || segment.sg_rank_absolute || '-') : (segment.sg_rank_absolute || '-');
        const rankSex      = useGun ? (segment.sg_rank_sex_gun      || segment.sg_rank_sex      || '-') : (segment.sg_rank_sex      || '-');
        const rankCategory = useGun ? (segment.sg_rank_category_gun || segment.sg_rank_category || '-') : (segment.sg_rank_category || '-');

        let paceHtml = pace;
        if (prevSegment) {
            const prevPace = formatSegmentPace(useGun ? (prevSegment.sg_pace_avg_gun || prevSegment.sg_pace_avg) : prevSegment.sg_pace_avg);
            const cmp = compareSegments(pace, prevPace);
            if (cmp) {
                const clr = cmp.improved ? '#27ae60' : '#e74c3c';
                paceHtml += ` <span style="color:${clr};font-size:0.85em">${cmp.direction}${cmp.percent}%</span>`;
            }
        }

        const rankBadge = (rank) => {
            const clr = getRankColor(rank);
            return `<span class="seg-rank-badge" style="background:${clr}">${rank}</span>`;
        };

        const tr = document.createElement('tr');
        tr.innerHTML = `
            <td class="seg-name">${segKmName(code)}</td>
            <td class="seg-time">${time}</td>
            <td class="seg-pace">${paceHtml}</td>
            <td class="seg-rank">${rankBadge(rankAbsolute)}</td>
            <td class="seg-rank">${rankBadge(rankSex)}</td>
            <td class="seg-rank">${rankBadge(rankCategory)}</td>
        `;
        tbody.appendChild(tr);
    });

    table.appendChild(tbody);
    container.appendChild(table);
}

// === Вспомогательные функции ===

function getRaceStats() {
    const finishers = allRunners.filter(r => r.status === 'Finished').length;
    const raceComplete = finishers > 0 && !allRunners.some(r => r.status === 'Running');
    return { finishers, raceComplete };
}

// Экспорт результатов в PDF через браузерный print
function exportResultsPdf() {
    if (!filteredRunners.length) { alert('Нет данных для экспорта'); return; }
    const title = document.getElementById('pageTitle').innerText.replace(/\n/g, ' ');
    const zhara = isZharaEvent();
    const primaryTimeField = zhara ? 'time_clear_finish' : 'time_gun_finish';

    // Сортировка: финишёры по возрастанию основного (для Жары — чистого,
    // иначе официального) времени, остальные в конце
    const sorted = [...filteredRunners].sort((a, b) => {
        const tA = KMUtils.parseTimeToSeconds(a[primaryTimeField]);
        const tB = KMUtils.parseTimeToSeconds(b[primaryTimeField]);
        const hasA = tA > 0;
        const hasB = tB > 0;
        if (hasA && hasB) return tA - tB;
        if (hasA) return -1;
        if (hasB) return 1;
        return 0;
    });

    const rows = sorted.map((r, i) => {
        const tGunCell   = `<td>${formatTime(r.time_gun_finish)   || '—'}</td>`;
        const tCleanCell = `<td>${formatTime(r.time_clear_finish) || '—'}</td>`;
        const timeCells = zhara ? tCleanCell + tGunCell : tGunCell + tCleanCell;
        const rankAbs = (zhara ? r.rank_absolute_clean : r.rank_absolute) ?? '—';
        const rankSex = (zhara ? r.rank_sex_clean      : r.rank_sex)      ?? '—';
        const rankCat = (zhara ? r.rank_category_clean : r.rank_category) ?? '—';
        const noFinish = !r[primaryTimeField];
        const rowStyle = noFinish ? ' style="color:#999"' : '';
        return `<tr${rowStyle}>
            <td>${noFinish ? '—' : i + 1}</td>
            <td>${(r.surname||'')} ${(r.name||'')}</td>
            <td>${r.distance||r.event_distance||'—'}</td>
            <td>${r.category||'—'}</td>
            ${timeCells}
            <td>${rankAbs}</td>
            <td>${rankSex}</td>
            <td>${rankCat}</td>
        </tr>`;
    }).join('');
    const timeHeaders = zhara
        ? '<th>Чистое время</th><th>Офиц. время</th>'
        : '<th>Офиц. время</th><th>Чистое время</th>';
    const html = `<!DOCTYPE html><html><head><meta charset="UTF-8"><title>${title}</title>
<style>
  body{font-family:Arial,sans-serif;font-size:10px;margin:16px}
  h2{font-size:14px;margin:0 0 4px}
  p{font-size:9px;color:#666;margin:0 0 10px}
  table{border-collapse:collapse;width:100%}
  th,td{border:1px solid #bbb;padding:3px 6px;text-align:left}
  th{background:#222;color:#fff;font-size:9px;text-transform:uppercase;white-space:nowrap}
  tr:nth-child(even){background:#f7f7f7}
  @page{margin:15mm;size:landscape}
</style></head><body>
<h2>${title}</h2>
<p>${filteredRunners.length} участников · ${new Date().toLocaleDateString('ru-RU')}</p>
<table><thead><tr>
  <th>№</th><th>Фамилия и Имя</th><th>Дистанция</th><th>Категория</th>
  ${timeHeaders}
  <th>Место абс.</th><th>Место пол</th><th>Место кат.</th>
</tr></thead><tbody>${rows}</tbody></table>
<script>window.onload=()=>window.print();<\/script>
</body></html>`;
    const w = window.open('', '_blank');
    w.document.write(html);
    w.document.close();
}
