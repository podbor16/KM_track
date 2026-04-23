document.addEventListener('DOMContentLoaded', function() {
    const searchInput = document.getElementById('athleteSearchInput');
    const resultsContainer = document.getElementById('resultsContainer');
    const searchStatus = document.getElementById('searchStatus');

    let searchTimeout;
    let currentSelectedIndex = -1;

    if (!searchInput || !resultsContainer || !searchStatus) {
        console.error('❌ history.js: не найдены обязательные элементы DOM');
        return;
    }

    searchInput.addEventListener('input', function() {
        const query = this.value.trim();

        clearTimeout(searchTimeout);

        if (!query) {
            resultsContainer.innerHTML = '<div class="no-results">Начните вводить для поиска...</div>';
            resultsContainer.classList.remove('show');
            searchStatus.textContent = '';
            currentSelectedIndex = -1;
            return;
        }

        if (query.length < 2) {
            resultsContainer.innerHTML = '<div class="no-results">Введите минимум 2 символа</div>';
            resultsContainer.classList.add('show');
            searchStatus.textContent = '';
            return;
        }

        searchStatus.innerHTML = '<span class="search-loader"></span> Поиск...';

        searchTimeout = setTimeout(() => {
            performSearch(query);
        }, 300);
    });

    async function performSearch(query) {
        try {
            const response = await fetch(`/api/search-athletes?q=${encodeURIComponent(query)}`);

            if (!response.ok) {
                throw new Error(`HTTP ошибка! статус: ${response.status}`);
            }

            const data = await response.json();

            if (!data.results || data.results.length === 0) {
                resultsContainer.innerHTML = '<div class="no-results">Спортсмены не найдены</div>';
                searchStatus.textContent = `По запросу "${query}" ничего не найдено`;
            } else {
                displayResults(data.results);
                searchStatus.textContent = `Найдено ${data.count || data.results.length} спортсменов`;
            }

            resultsContainer.classList.add('show');
            currentSelectedIndex = -1;

        } catch (error) {
            console.error('❌ Ошибка при поиске:', error);
            resultsContainer.innerHTML = `<div class="no-results">Ошибка при поиске:<br><small>${error.message}</small></div>`;
            searchStatus.textContent = '❌ Ошибка поиска';
            resultsContainer.classList.add('show');
        }
    }

    function displayResults(results) {
        if (!results || results.length === 0) {
            resultsContainer.innerHTML = '<div class="no-results">Нет результатов</div>';
            return;
        }

        let html = '';
        results.forEach((athlete, index) => {
            const surname = athlete.surname || 'Не указано';
            const name = athlete.name || 'Не указано';
            const birth_year = athlete.birth_year || 'Неизвестно';

            html += `
                <div class="autocomplete-item" data-index="${index}" data-surname="${surname}" data-name="${name}">
                    <div class="athlete-info">${surname} ${name}, ${birth_year} г.р.</div>
                </div>
            `;
        });

        resultsContainer.innerHTML = html;

        const items = resultsContainer.querySelectorAll('.autocomplete-item');

        items.forEach(item => {
            item.addEventListener('click', function() {
                selectAthlete(this);
            });

            item.addEventListener('mouseenter', function() {
                items.forEach(i => i.classList.remove('selected'));
                this.classList.add('selected');
                currentSelectedIndex = parseInt(this.dataset.index);
            });
        });
    }

    function selectAthlete(element) {
        const surname = element.dataset.surname;
        const name = element.dataset.name;

        searchInput.value = `${surname} ${name}`;
        resultsContainer.classList.remove('show');
        searchStatus.textContent = '✓ Спортсмен выбран';

        window.location.href = `/athlete-profile?surname=${encodeURIComponent(surname)}&name=${encodeURIComponent(name)}`;
    }

    document.addEventListener('click', function(e) {
        if (!e.target.closest('.athlete-search-container')) {
            resultsContainer.classList.remove('show');
        }
    });

    searchInput.addEventListener('keydown', function(e) {
        const items = resultsContainer.querySelectorAll('.autocomplete-item');

        if (e.key === 'ArrowDown') {
            e.preventDefault();
            if (currentSelectedIndex < items.length - 1) {
                currentSelectedIndex++;
                items[currentSelectedIndex].scrollIntoView({ block: 'nearest' });
                items.forEach(i => i.classList.remove('selected'));
                items[currentSelectedIndex].classList.add('selected');
            }
        } else if (e.key === 'ArrowUp') {
            e.preventDefault();
            if (currentSelectedIndex > 0) {
                currentSelectedIndex--;
                items[currentSelectedIndex].scrollIntoView({ block: 'nearest' });
                items.forEach(i => i.classList.remove('selected'));
                items[currentSelectedIndex].classList.add('selected');
            }
        } else if (e.key === 'Enter') {
            e.preventDefault();
            if (currentSelectedIndex >= 0 && items[currentSelectedIndex]) {
                selectAthlete(items[currentSelectedIndex]);
            }
        } else if (e.key === 'Escape') {
            resultsContainer.classList.remove('show');
        }
    });

    searchInput.focus();
});
