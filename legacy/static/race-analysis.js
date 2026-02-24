// race-analysis.js - Логика для страницы Анализ забегов

document.addEventListener('DOMContentLoaded', function() {
    initializeRaceCards();
    initializeModal();
});

/**
 * Инициализирует модальное окно
 */
function initializeModal() {
    const modal = document.getElementById('race-modal');
    const closeBtn = document.querySelector('.race-modal-close');
    const backdrop = document.querySelector('.race-modal-backdrop');

    // Закрытие по кнопке "X"
    closeBtn.addEventListener('click', closeModal);

    // Закрытие по клику на backdrop
    backdrop.addEventListener('click', closeModal);

    // Предотвращение закрытия при клике в контейнер модали
    document.querySelector('.race-modal-container').addEventListener('click', function(e) {
        e.stopPropagation();
    });
}

/**
 * Закрывает модальное окно
 */
function closeModal() {
    const modal = document.getElementById('race-modal');
    modal.classList.remove('active');
}

/**
 * Открывает модальное окно с информацией о забеге
 * @param {string} raceName - Название забега
 */
function openRaceModal(raceName) {
    const modal = document.getElementById('race-modal');
    const title = document.querySelector('.race-modal-title');
    const body = document.querySelector('.race-modal-body');

    title.textContent = raceName;
    
    // Обновляем описание (позже будет подтягиваться из данных)
    body.innerHTML = `<p>${getRaceDescription(raceName)}</p><p style="margin-top: 20px; color: #666;">Информация о забеге и аналитика будут добавлены позже</p>`;

    modal.classList.add('active');
    
    // Закрытие модали клавишей Escape
    document.addEventListener('keydown', handleEscapeKey);
}

/**
 * Обработчик клавиши Escape для закрытия модали
 */
function handleEscapeKey(e) {
    if (e.key === 'Escape') {
        closeModal();
        document.removeEventListener('keydown', handleEscapeKey);
    }
}

/**
 * Возвращает описание забега по названию
 * @param {string} raceName - Название забега
 * @returns {string} - Описание забега
 */
function getRaceDescription(raceName) {
    const descriptions = {
        'Ночной забег': 'Забег под звёздами на набережной',
        'Весна': 'Весенний полумарафон по живописным маршрутам',
        'Красочный забег': 'Яркий 5-километровый забег на острове Татышев',
        'Женская Семерка': '7-км забег для женщин-спортсменов',
        'Жара': 'Летний полумарафон на площади Мира в августе',
        'Детский Забег': '1-км забег для самых маленьких спортсменов',
        'Х Трейл': 'Трейл-забег по пересечённой местности',
        'Снежная семерка': '7-км зимний забег на острове Татышев в декабре'
    };
    
    return descriptions[raceName] || 'Информация о забеге';
}

/**
 * Инициализирует интерактивность карточек забегов
 */
function initializeRaceCards() {
    const raceCards = document.querySelectorAll('.race-card');
    
    raceCards.forEach((card, index) => {
        // Обработчик клика
        card.addEventListener('click', function() {
            handleRaceCardClick(this, index);
        });

        // Поддержка клавиатуры для доступности
        card.setAttribute('tabindex', '0');
        card.setAttribute('role', 'button');
        
        card.addEventListener('keydown', function(e) {
            if (e.key === 'Enter' || e.key === ' ') {
                e.preventDefault();
                handleRaceCardClick(this, index);
            }
        });

        // Визуальная обратная связь при фокусе
        card.addEventListener('focus', function() {
            this.style.outline = '2px solid #ee2d62';
            this.style.outlineOffset = '2px';
        });

        card.addEventListener('blur', function() {
            this.style.outline = 'none';
        });
    });
}

/**
 * Обработчик клика по карточке забега
 * @param {HTMLElement} card - Элемент карточки
 * @param {number} index - Индекс карточки (0-7)
 */
function handleRaceCardClick(card, index) {
    const title = card.querySelector('.race-card-title')?.textContent.trim() || card.dataset.raceName;
    
    // Логирование для отладки
    console.log('Выбран забег:', title);
    
    // Для первой карточки открываем модальное окно
    if (index === 0) {
        openRaceModal(title);
    } else {
        // Заглушка для будущей функциональности других карточек
        console.log('Аналитика для "' + title + '" будет реализована в ближайшее время');
    }
}

/**
 * Функция для поиска забега по названию (может быть полезна в будущем)
 * @param {string} raceName - Название забега
 * @returns {HTMLElement|null} - Элемент карточки или null
 */
function findRaceCard(raceName) {
    const raceCards = document.querySelectorAll('.race-card');
    
    for (let card of raceCards) {
        const title = card.querySelector('.race-card-title')?.textContent.trim() || card.dataset.raceName;
        if (title.toLowerCase() === raceName.toLowerCase()) {
            return card;
        }
    }
    
    return null;
}
