'use strict';

(() => {
    const root = document.documentElement;
    const storageKey = 'siberman-theme';
    if (window.self !== window.top && root.hasAttribute('data-light-embed')) {
        root.dataset.theme = 'light';
        return;
    }

    function restoreTheme() {
        try {
            root.dataset.theme = localStorage.getItem(storageKey) === 'dark' ? 'dark' : 'light';
        } catch {
            // Хранилище может быть отключено настройками браузера.
            root.dataset.theme = 'light';
        }
    }
    restoreTheme();

    document.addEventListener('DOMContentLoaded', () => {
        const button = document.getElementById('themeBtn');
        if (!button) return;

        function updateButton() {
            const isDark = root.dataset.theme === 'dark';
            button.textContent = isDark ? '☀️' : '🌙';
            button.setAttribute('aria-label', isDark ? 'Включить светлую тему' : 'Включить тёмную тему');
        }

        updateButton();
        window.addEventListener('pageshow', event => {
            if (!event.persisted) return;
            restoreTheme();
            updateButton();
        });
        button.addEventListener('click', () => {
            root.dataset.theme = root.dataset.theme === 'dark' ? 'light' : 'dark';
            updateButton();
            try {
                localStorage.setItem(storageKey, root.dataset.theme);
            } catch {
                // Тема переключается и при недоступном хранилище.
            }
        });
    });
})();
