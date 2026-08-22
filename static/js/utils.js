// Общие утилиты KM_Track — доступны через window.KMUtils
window.KMUtils = {
    EVENT_NAMES: {
        'night_run':  'Ночной забег',
        'vesna':      'Весна',
        'colorrun':   'Красочный забег',
        'girlseven':  'Женская семерка',
        'zhara':      'Жара',
        'kids':       'Детский забег',
        'xtrailrun':  'Х Трейл',
        'snow7':      'Снежная семерка',
        'pervomay':   'Первомайский полумарафон',
        'dostigaya_tseli': 'Достигая цели'
    },

    EVENT_COLORS: {
        'night_run':  '#1c2c55',
        'vesna':      '#85c6e2',
        'colorrun':   '#059C43',
        'girlseven':  '#f072ab',
        'zhara':      '#ee2d62',
        'kids':       '#ee2d62',
        'xtrailrun':  '#562872',
        'snow7':      '#00BFDF',
        'pervomay':   '#d0393b',
        'dostigaya_tseli': '#c1272d'
    },

    // Общий парсер длительности → секунды. Принимает строку "H:MM:SS"/"MM:SS",
    // ISO 8601 (PT...) или число мс. null, если распознать не удалось.
    _durationToSeconds(timeData) {
        if (timeData === null || timeData === undefined || timeData === '') return null;
        if (typeof timeData === 'number') return Math.floor(timeData / 1000);
        const s = String(timeData);
        if (s.startsWith('PT')) {
            const m = s.match(/PT(?:(\d+)H)?(?:(\d+)M)?(?:(\d+(?:\.\d+)?)S)?/);
            if (!m) return null;
            return parseInt(m[1] || 0) * 3600 + parseInt(m[2] || 0) * 60 + Math.floor(parseFloat(m[3] || 0));
        }
        const parts = s.split(':').map(p => parseInt(p, 10));
        if (parts.some(isNaN)) return null;
        if (parts.length === 3) return parts[0] * 3600 + parts[1] * 60 + parts[2];
        if (parts.length === 2) return parts[0] * 60 + parts[1];
        return null;
    },

    // Форматирует секунды по единому правилу проекта: меньше часа → "M:SS",
    // час и больше → "H:MM:SS" (часы без ведущего нуля, минуты/секунды — с).
    _formatSecondsAdaptive(totalSeconds) {
        if (totalSeconds === null || totalSeconds === undefined || isNaN(totalSeconds)) return null;
        totalSeconds = Math.floor(totalSeconds);
        const h = Math.floor(totalSeconds / 3600);
        const min = Math.floor((totalSeconds % 3600) / 60);
        const sec = totalSeconds % 60;
        if (h > 0) return `${h}:${String(min).padStart(2,'0')}:${String(sec).padStart(2,'0')}`;
        return `${min}:${String(sec).padStart(2,'0')}`;
    },

    // Форматирует время по единому правилу проекта (< 1 часа → M:SS, иначе
    // H:MM:SS); принимает строку HH:MM:SS/MM:SS, ISO 8601 (PT...) или число мс
    formatTime(timeData) {
        return this._formatSecondsAdaptive(this._durationToSeconds(timeData)) ?? '-';
    },

    // Вычисляет темп (минут/км) как число; принимает время (строка HH:MM:SS / ISO 8601 / мс) и строку дистанции
    calculatePace(timeData, distanceStr) {
        if (!timeData || !distanceStr) return '-';
        const distanceNum = parseFloat(distanceStr);
        if (distanceNum <= 0) return '-';
        let totalSeconds = 0;
        if (typeof timeData === 'string' && timeData.includes(':')) {
            const parts = timeData.split(':');
            if (parts.length === 3) {
                totalSeconds = parseInt(parts[0]) * 3600 + parseInt(parts[1]) * 60 + parseInt(parts[2]);
            } else if (parts.length === 2) {
                totalSeconds = parseInt(parts[0]) * 60 + parseInt(parts[1]);
            }
        } else if (typeof timeData === 'number') {
            totalSeconds = timeData > 60000 ? timeData / 1000 : timeData;
        } else if (typeof timeData === 'string' && timeData.startsWith('PT')) {
            const m = timeData.match(/PT(?:(\d+)H)?(?:(\d+)M)?(?:(\d+(?:\.\d+)?)S)?/);
            if (m) {
                totalSeconds = parseInt(m[1] || 0) * 3600 + parseInt(m[2] || 0) * 60 + Math.floor(parseFloat(m[3] || 0));
            }
        }
        if (totalSeconds <= 0) return '-';
        return (totalSeconds / 60 / distanceNum).toFixed(5);
    },

    // Конвертирует "H:MM:SS"/"M:SS" или "PTxHxMxS" в секунды; возвращает
    // Infinity для пустых/некорректных значений (сортировка уносит в конец)
    parseTimeToSeconds(timeStr) {
        if (!timeStr || typeof timeStr !== 'string') return Infinity;
        const total = this._durationToSeconds(timeStr);
        return total === null ? Infinity : total;
    },

    // Возрастная группа бывает в двух форматах: старый развёрнутый
    // ("женщины до 49 лет") и новый компактный ("Ж18-49", "М80+", настраивается
    // по событию/дистанции в age_group_configs) — различаются регистром первой
    // буквы (лат. "женщины"/"мужчины" строчные, компактный — прописные "Ж"/"М").
    isFemaleCategory(cat) {
        return !!cat && (cat.startsWith('женщины') || cat.startsWith('Ж'));
    },
    isMaleCategory(cat) {
        return !!cat && (cat.startsWith('мужчины') || cat.startsWith('М'));
    },

    // Числовой ключ сортировки возрастной группы — понимает оба формата: сортирует
    // по первому числу в строке (49/50/60/65/70/75 или 18/50/60.../80 и т.п.),
    // это работает одинаково что для "женщины до 49 лет", что для "Ж18-49"/"М80+",
    // не завязано на конкретный набор границ конкретного события.
    categoryOrder(cat) {
        if (!cat) return 9999;
        const base = this.isFemaleCategory(cat) ? 0 : (this.isMaleCategory(cat) ? 1000 : 2000);
        const m = cat.match(/\d+/);
        const age = m ? parseInt(m[0], 10) : 999;
        return base + age;
    },

    // Извлекает числовое значение км из строки вида "10 км"/"500 м" — единица
    // измерения ОБЯЗАТЕЛЬНО учитывается (не только число): "500 м" раньше
    // парсилось как голое число 500 без учёта "м" и в сравнении оказывалось
    // "больше", чем "1 км" (число 1) — на /start_list это ломало дефолт на
    // максимальную дистанцию (Детский забег открывался на "500 м" вместо
    // максимальной "1 км", реальная находка 2026-08-19).
    parseDistanceKm(distStr) {
        if (!distStr) return 0;
        const m = String(distStr).match(/(\d+(?:[.,]\d+)?)\s*(км|km|м|m)?/i);
        if (!m) return 0;
        const value = parseFloat(m[1].replace(',', '.'));
        const unit = (m[2] || 'км').toLowerCase();
        return (unit === 'м' || unit === 'm') ? value / 1000 : value;
    },

    // Убирает скобочный суффикс с годами рождения из названия категории: "мужчины до 49 лет (1977 г.р.)" → "мужчины до 49 лет"
    normalizeCategory(cat) {
        if (!cat) return '';
        return cat.replace(/\s*\(.*?\)/g, '').trim();
    },

    // Парсит длительность (ISO 8601 PT.../"H:MM:SS"/"MM:SS") в читаемый формат
    // по единому правилу проекта (< 1 часа → M:SS, иначе H:MM:SS)
    parseDuration(duration) {
        if (!duration) return null;
        const totalSeconds = this._durationToSeconds(duration);
        if (totalSeconds === null) return duration;
        return this._formatSecondsAdaptive(totalSeconds);
    },

    // fetch() с явным cache:'no-store' — сервер уже шлёт Cache-Control:
    // no-store на все /api/* и HTML (nginx location /), но некоторые
    // WebView (замечено в браузере Telegram — Android System WebView под
    // капотом) не всегда честно ревалидируют по одним только заголовкам
    // ответа и отдают закэшированный fetch() без похода в сеть вовсе.
    // Явная опция cache в самом запросе форсирует пропуск HTTP-кэша на
    // уровне браузерного API, а не только на уровне заголовков —
    // надёжнее для таких WebView. См. sessions/2026-05-23-telegram-cache-fix
    // (тот фикс закрыл HTML/статику, но не сами fetch()-запросы за данными).
    fetchFresh(url, options = {}) {
        return fetch(url, { ...options, cache: 'no-store' });
    }
};
