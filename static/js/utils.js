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
        'pervomay':   'Первомайский полумарафон'
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
        'pervomay':   '#d0393b'
    },

    // Форматирует время в HH:MM:SS; принимает строку HH:MM:SS, ISO 8601 (PT...) или число мс
    formatTime(timeData) {
        if (!timeData) return '-';
        if (typeof timeData === 'string') {
            if (timeData.match(/^\d{1,2}:\d{2}:\d{2}$/)) return timeData;
            if (timeData.startsWith('PT')) {
                const m = timeData.match(/PT(?:(\d+)H)?(?:(\d+)M)?(?:(\d+(?:\.\d+)?)S)?/);
                if (m) {
                    let h = parseInt(m[1] || 0);
                    let min = parseInt(m[2] || 0);
                    let sec = Math.floor(parseFloat(m[3] || 0));
                    min += Math.floor(sec / 60); sec %= 60;
                    h += Math.floor(min / 60); min %= 60;
                    return `${String(h).padStart(2,'0')}:${String(min).padStart(2,'0')}:${String(sec).padStart(2,'0')}`;
                }
            }
            return '-';
        }
        const ts = Math.floor(timeData / 1000);
        const h = Math.floor(ts / 3600);
        const min = Math.floor((ts % 3600) / 60);
        const sec = ts % 60;
        return `${String(h).padStart(2,'0')}:${String(min).padStart(2,'0')}:${String(sec).padStart(2,'0')}`;
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

    // Конвертирует "HH:MM:SS" или "PTxHxMxS" в секунды; возвращает Infinity для пустых/некорректных значений
    parseTimeToSeconds(timeStr) {
        if (!timeStr || typeof timeStr !== 'string') return Infinity;
        if (timeStr.startsWith('PT')) {
            const m = timeStr.match(/PT(?:(\d+)H)?(?:(\d+)M)?(?:(\d+(?:\.\d+)?)S)?/);
            if (m) return parseInt(m[1]||0)*3600 + parseInt(m[2]||0)*60 + Math.floor(parseFloat(m[3]||0));
        }
        const parts = timeStr.split(':');
        if (parts.length === 3)
            return parseInt(parts[0]) * 3600 + parseInt(parts[1]) * 60 + parseInt(parts[2]);
        return Infinity;
    },

    // Числовой ключ сортировки возрастной группы: женщины 0-6, мужчины 10-16
    categoryOrder(cat) {
        if (!cat) return 99;
        const c = cat.toLowerCase();
        const base = c.startsWith('женщин') ? 0 : 10;
        if (c.includes('до 49'))                            return base + 1;
        if (c.includes('50-59'))                            return base + 2;
        if (c.includes('60-64'))                            return base + 3;
        if (c.includes('65-69'))                            return base + 4;
        if (c.includes('70-74'))                            return base + 5;
        if (c.includes('75') || c.includes('65 лет и старше')) return base + 6;
        return base + 7;
    },

    // Извлекает числовое значение км из строки типа "10 км"
    parseDistanceKm(distStr) {
        if (!distStr) return 0;
        const m = String(distStr).match(/(\d+(?:[.,]\d+)?)/);
        return m ? parseFloat(m[1].replace(',', '.')) : 0;
    },

    // Убирает скобочный суффикс с годами рождения из названия категории: "мужчины до 49 лет (1977 г.р.)" → "мужчины до 49 лет"
    normalizeCategory(cat) {
        if (!cat) return '';
        return cat.replace(/\s*\(.*?\)/g, '').trim();
    },

    // Парсит ISO 8601 duration (PT1H26M0S) в читаемый формат H:MM:SS
    parseDuration(duration) {
        if (!duration) return null;
        if (!String(duration).startsWith('PT')) return duration;
        const m = String(duration).match(/PT(?:(\d+)H)?(?:(\d+)M)?(?:(\d+)S)?/);
        if (!m) return duration;
        const totalSeconds = (parseInt(m[1] || 0) * 3600) + (parseInt(m[2] || 0) * 60) + parseInt(m[3] || 0);
        const h = Math.floor(totalSeconds / 3600);
        const min = Math.floor((totalSeconds % 3600) / 60);
        const s = totalSeconds % 60;
        if (h > 0) return `${h}:${String(min).padStart(2,'0')}:${String(s).padStart(2,'0')}`;
        return `${min}:${String(s).padStart(2,'0')}`;
    }
};
