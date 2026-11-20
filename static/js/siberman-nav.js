'use strict';

// Возврат только на публичные страницы результатов и профилей этого сайта.
const sibermanContextPaths = /^(?:\/|\/results\/?|\/hall\/(?:rating|records|geo|stats)|\/athlete\/[A-Za-z0-9_-]+)$/;
function sibermanBackHref(value) {
    if (!value || !value.startsWith('/')) return null;
    try {
        const url = new URL(value, window.location.origin);
        return url.origin === window.location.origin && sibermanContextPaths.test(url.pathname)
            ? url.pathname + url.search + url.hash : null;
    } catch {
        return null;
    }
}

function sibermanContextHref(path) {
    const back = sibermanBackHref(window.location.pathname + window.location.search + window.location.hash);
    if (!back) return path;
    const url = new URL(path, window.location.origin);
    url.searchParams.set('back', back);
    return url.pathname + url.search + url.hash;
}

(() => {
    const header = document.getElementById('sb-site-header');
    if (!header) return;
    header.hidden = window.self !== window.top;
    const menu = header.querySelector('.sb-site-menu');
    document.addEventListener('click', event => {
        if (menu.open && !menu.contains(event.target)) menu.open = false;
    });
    document.addEventListener('keydown', event => {
        if (event.key !== 'Escape' || !menu.open) return;
        menu.open = false;
        menu.querySelector('summary').focus();
    });
})();

window.addEventListener('DOMContentLoaded', () => {
    const link = document.querySelector('[data-siberman-back]');
    if (!link) return;
    const back = sibermanBackHref(new URLSearchParams(window.location.search).get('back'));
    if (!back) return;
    link.href = back;
    if (back.startsWith('/athlete/')) link.textContent = '← К профилю спортсмена';
    else if (back.startsWith('/hall/')) link.textContent = '← К предыдущему разделу';
    else link.textContent = '← К результатам';
    const header = document.querySelector('[data-siberman-detail]');
    if (!header || back.startsWith('/athlete/')) return;
    const path = new URL(back, window.location.origin).pathname;
    const section = path.startsWith('/hall/') ? path.split('/').pop() : 'results';
    for (const item of header.querySelectorAll('[data-siberman-section]')) {
        if (item.dataset.sibermanSection === section) {
            item.setAttribute('aria-current', 'location');
            header.querySelector('summary').textContent = item.textContent;
        } else item.removeAttribute('aria-current');
    }
});
