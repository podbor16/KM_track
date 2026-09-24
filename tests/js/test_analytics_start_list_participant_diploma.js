// Кнопка «Диплом» в строке стартового списка — только у дистанций с дипломом
// участника (participant_only в YAML, набор PARTICIPANT_DIPLOMA_EVENT_IDS из
// шаблона start_list.html), ссылка /diploma/lead/{lead_id}.
// Запуск: node tests/js/test_analytics_start_list_participant_diploma.js
const fs = require('fs');
const path = require('path');
const vm = require('vm');
const assert = require('assert');

const ROOT = path.resolve(__dirname, '..', '..');
const utilsJs = fs.readFileSync(path.join(ROOT, 'static/js/utils.js'), 'utf-8');
const scriptJs = fs.readFileSync(path.join(ROOT, 'static/js/analytics-start-list.js'), 'utf-8');

const rows = [];
const tbody = { set innerHTML(v) { rows.length = 0; }, appendChild(r) { rows.push(r); } };
const sandbox = {
    console,
    fetch: () => Promise.resolve({ json: () => Promise.resolve({}) }),
    document: {
        getElementById: (id) => (id === 'startListBody' ? tbody : { style: {}, classList: { toggle() {} }, addEventListener() {} }),
        createElement: () => ({ className: '', innerHTML: '' }),
        addEventListener: () => {},
        querySelectorAll: () => [],
    },
    localStorage: { getItem: () => null, setItem: () => {} },
    URLSearchParams,
    location: { pathname: '/start_list', search: '', hash: '' },
    history: { replaceState: () => {} },
    PARTICIPANT_DIPLOMA_EVENT_IDS: new Set([118]),
};
sandbox.window = sandbox;
vm.createContext(sandbox);
vm.runInContext(utilsJs, sandbox);
vm.runInContext(scriptJs, sandbox);

let failures = 0;
function check(name, fn) {
    try { fn(); console.log(`OK   ${name}`); }
    catch (e) { failures++; console.log(`FAIL ${name}: ${e.message}`); }
}

const runner2km = { surname: 'Иванова', name: 'Анна', distance: '2 км', lead_id: 42, event_id: 118 };
const runner5km = { surname: 'Петров', name: 'Пётр', distance: '5 км', lead_id: 43, event_id: 117 };

check('hasParticipantDiploma — только для event_id из набора и с lead_id', () => {
    assert.strictEqual(sandbox.hasParticipantDiploma(runner2km), true);
    assert.strictEqual(sandbox.hasParticipantDiploma(runner5km), false);
    assert.strictEqual(sandbox.hasParticipantDiploma({ ...runner2km, lead_id: null }), false);
});

check('renderStartList — ссылка на диплом участника только в строке 2 км', () => {
    sandbox.renderStartList([runner2km, runner5km]);
    assert.strictEqual(rows.length, 2);
    assert.ok(rows[0].innerHTML.includes('href="/diploma/lead/42"'));
    assert.ok(!rows[1].innerHTML.includes('/diploma/'));
});

console.log(failures === 0 ? '\nALL PASSED' : `\n${failures} FAILED`);
process.exit(failures === 0 ? 0 : 1);
