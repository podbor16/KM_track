// static/js/krasmarafon-broadcast-posts.js
// Генератор текстовых постов "Топ-3 мужчины"/"Топ-3 женщины" по контрольным
// точкам Жары (5 км/21.1 км) для вкладки "Трансляция" в /admin. Источник
// данных — уже существующие live-JSON файлы, которые generate_top10_json()
// (src/krasmarafon/services/live_top10_export.py) пишет во время гонки
// (см. docs/superpowers/specs/2026-08-18-zhara-live-top10-broadcast-json-design.md).
// Дизайн этой конкретной фичи (формат поста, markdown-конвенция **/__ как у
// Siberman) — docs/superpowers/specs/2026-08-19-krasmarafon-broadcast-top3-posts-design.md.

const BCP_JSON_URLS = {
    '5 км': '/live/zhara_5km_top10.json',
    '21.1 км': '/live/zhara_21km_top10.json',
};

const BCP_NO_DATA_MESSAGE = 'Нет данных — трансляция ещё не активна';

// Строит готовый к копированию текст поста для одной (checkpoint, sexKey).
// checkpoint — один объект из data.checkpoints (см. схему в спеке),
// sexKey — 'male' | 'female'. Чистая функция, без обращения к DOM — легко
// тестируется через node:vm без стабов document/fetch.
function buildTop3Post(checkpoint, sexKey) {
    const list = (sexKey === 'male' ? checkpoint.top10_male : checkpoint.top10_female) || [];
    const top3 = list.slice(0, 3);
    // Пустой топ-3 — короткое сообщение вместо всего поста (тот же приём,
    // что у Siberman: bcBuildStagePost() возвращает голую строку без
    // заголовка/подписи, когда никто ещё не дошёл до отметки).
    if (top3.length === 0) {
        return 'Нет данных для этой отметки — пока никто не финишировал.';
    }

    const sexLabel = sexKey === 'male' ? 'Мужчины' : 'Женщины';
    let titleSuffix;
    if (checkpoint.code === 'finish') {
        titleSuffix = 'Финиш';
    } else {
        // label — "КТ{i} ({N} км)" (live_top10_export.py), N km извлекаем
        // регэкспом, а не пересчитываем на клиенте заново.
        const m = /\(([\d.]+)\s*км\)/.exec(checkpoint.label || '');
        titleSuffix = `Отсечка ${m ? m[1] : '?'} км`;
    }
    const title = `**${sexLabel}. ${titleSuffix}**`;

    const entries = top3.map((entry, idx) => {
        // entry.time уже "ЧЧ:ММ:СС" — обрезаем "00:" в начале, часовую
        // часть оставляем как есть, если гонка реально идёт больше часа.
        let time = entry.time || '';
        if (time.startsWith('00:')) time = time.slice(3);
        const gapSuffix = (entry.gap_sex && entry.gap_sex !== 'Лидер') ? ` (${entry.gap_sex})` : '';
        const lines = [`${idx + 1}. ${entry.surname} ${entry.name}`, `⏱️${time}${gapSuffix}`];
        if (entry.pace) lines.push(`${entry.pace} мин/км`);
        return lines.join('\n');
    });

    const footer = '__👉 ссылка на лайв-результаты: https://results.krasmarafon.ru/results__';
    return `${title}\n\n${entries.join('\n\n')}\n\n${footer}`;
}

// ---- DOM-обвязка ----
// Fetch происходит ДВАЖДЫ по дизайну (не кешируем JSON между шагами):
// (1) при смене дистанции — только чтобы заполнить список отметок
//     (структура отметок стабильна в рамках гонки, но перезапрашиваем
//     всё равно ради простоты — один путь кода, не два);
// (2) при каждом клике "Сгенерировать" — гарантирует, что пост строится
//     по самым свежим данным на момент публикации, а не по снапшоту с
//     момента выбора дистанции (тот же принцип, что у Siberman bcGenerate()
//     — там тоже fetch происходит заново на каждый клик "Сгенерировать").

async function bcpFetchDistanceData(distanceLabel) {
    const url = BCP_JSON_URLS[distanceLabel];
    const r = await fetch(url);
    if (!r.ok) throw new Error('not ok');
    return r.json();
}

function bcpShowError(show) {
    const errEl = document.getElementById('bcp-error');
    if (!errEl) return;
    errEl.textContent = BCP_NO_DATA_MESSAGE;
    errEl.style.display = show ? '' : 'none';
}

async function bcpOnDistanceChange() {
    const distSel = document.getElementById('bcp-distance');
    const cpSel = document.getElementById('bcp-checkpoint');
    cpSel.innerHTML = '<option value="">— отметка —</option>';
    document.getElementById('bcp-output-male').value = '';
    document.getElementById('bcp-output-female').value = '';
    bcpShowError(false);
    try {
        const data = await bcpFetchDistanceData(distSel.value);
        (data.checkpoints || []).forEach(cp => {
            const opt = document.createElement('option');
            opt.value = cp.code;
            opt.textContent = cp.label;
            cpSel.appendChild(opt);
        });
    } catch (e) {
        bcpShowError(true);
    }
}

async function bcpGenerate(sexKey) {
    const distSel = document.getElementById('bcp-distance');
    const cpSel = document.getElementById('bcp-checkpoint');
    const outputId = sexKey === 'male' ? 'bcp-output-male' : 'bcp-output-female';
    const ta = document.getElementById(outputId);
    if (!cpSel.value) return;
    const wantedDistance = distSel.value;
    const wantedCode = cpSel.value;
    bcpShowError(false);
    try {
        const data = await bcpFetchDistanceData(wantedDistance);
        const checkpoint = (data.checkpoints || []).find(cp => cp.code === wantedCode);
        // Отметка не найдена в свежих данных (не должно происходить в норме —
        // список отметок строится из того же JSON) — это другой случай, чем
        // "источник данных недоступен": показываем сообщение о пустой
        // отметке, а не общую ошибку "трансляция не активна".
        ta.value = checkpoint
            ? buildTop3Post(checkpoint, sexKey)
            : 'Нет данных для этой отметки — пока никто не финишировал.';
    } catch (e) {
        bcpShowError(true);
    }
}

function bcpCopy(textareaId) {
    const ta = document.getElementById(textareaId);
    navigator.clipboard.writeText(ta.value).catch(() => {
        ta.select();
        document.execCommand('copy');
    });
}

document.addEventListener('DOMContentLoaded', () => {
    const distSel = document.getElementById('bcp-distance');
    if (!distSel) return; // разметки вкладки нет на этой странице — не наш случай
    distSel.addEventListener('change', bcpOnDistanceChange);
    document.getElementById('bcp-generate-male').addEventListener('click', () => bcpGenerate('male'));
    document.getElementById('bcp-generate-female').addEventListener('click', () => bcpGenerate('female'));
    document.getElementById('bcp-copy-male').addEventListener('click', () => bcpCopy('bcp-output-male'));
    document.getElementById('bcp-copy-female').addEventListener('click', () => bcpCopy('bcp-output-female'));
    bcpOnDistanceChange(); // заполнить отметки для дистанции, выбранной по умолчанию
});
