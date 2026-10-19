'use strict';
// Блок «География» (/hall/geo): карта Leaflet + Esri Light Gray, закрашенные страны участников, кружки
// городов с числом людей (близкие объединяются, распадаются при приближении), списки стран и городов.
// Колесо мыши над картой — масштаб; телефон: одним пальцем — прокрутка страницы, двумя — карта. Макет stats-geo-v10.

const CITY_LIMIT = 10;
const touch = L.Browser.touch && L.Browser.mobile;
const map = L.map('map', { scrollWheelZoom: true, worldCopyJump: true, dragging: !touch, tap: false });
map.attributionControl.setPrefix(false);                  // без «Leaflet» и флага; «Esri» — по условиям Esri
L.tileLayer('https://server.arcgisonline.com/ArcGIS/rest/services/Canvas/World_Light_Gray_Base/MapServer/tile/{z}/{y}/{x}',
  { maxZoom: 16, attribution: 'Esri' }).addTo(map);

if (touch) {
  const hint = document.getElementById('map-hint'), el = map.getContainer();
  let timer;
  el.addEventListener('touchmove', e => {
    if (e.touches.length !== 1) return;
    hint.style.opacity = 1;
    clearTimeout(timer);
    timer = setTimeout(() => { hint.style.opacity = 0; }, 1200);
  }, { passive: true });
  el.addEventListener('touchstart', e => { if (e.touches.length > 1) hint.style.opacity = 0; }, { passive: true });
}

const size = n => Math.round(22 + Math.sqrt(n) * 3.2);
const label = c => (c.country && c.country !== 'Россия' ? `${c.name}, ${c.country}` : c.name);
const icon = n => { const d = size(n); return L.divIcon({ className: 'city-pt', iconSize: [d, d], html: `<span>${n}</span>` }); };

function peopleHtml(c) {
  return `<b>${hallEsc(label(c))}</b> · ${c.count}<div class="pop-people">`
    + c.people.map(p => hallAthlete(p.person_id, hallEsc(p.fio))).join('<br>') + '</div>';
}

function drawCities(cities) {
  const group = L.markerClusterGroup({
    maxClusterRadius: 45, showCoverageOnHover: false, spiderfyOnMaxZoom: false, zoomToBoundsOnClick: true,
    iconCreateFunction: cl => {
      const kids = cl.getAllChildMarkers().sort((a, b) => b.options.count - a.options.count);
      const n = kids.reduce((s, m) => s + m.options.count, 0);
      const names = kids.slice(0, 5).map(m => m.options.city).join(', ') + (kids.length > 5 ? ` и ещё ${kids.length - 5}` : '');
      cl.bindTooltip(hallEsc(names), { direction: 'top', offset: [0, -size(n) / 2] });
      return icon(n);
    },
  });
  const placed = cities.filter(c => c.lat != null && c.lon != null);
  placed.forEach(c => {
    L.marker([c.lat, c.lon], { count: c.count, city: label(c), icon: icon(c.count) })
      .bindTooltip(hallEsc(label(c)), { direction: 'top', offset: [0, -size(c.count) / 2] })
      .bindPopup(peopleHtml(c)).addTo(group);
  });
  group.addTo(map);
  if (map.getSize().x < 560 || !placed.length) map.setView([55, 62], 2);   // телефон — Евразия
  else map.fitBounds(placed.map(c => [c.lat, c.lon]), { padding: [20, 20], maxZoom: 6 });
}

// Кольца через линию перемены дат (Чукотка, Алеуты): отрицательные долготы +360°, иначе полосы через карту.
function unwrap(ring) {
  const xs = ring.map(c => c[0]);
  if (Math.max(...xs) - Math.min(...xs) > 180) ring.forEach(c => { if (c[0] < 0) c[0] += 360; });
}

async function drawCountries(countries) {
  const have = new Map(countries.filter(c => c.iso).map(c => [String(c.iso).padStart(3, '0'), c]));
  if (!have.size) return;
  try {
    const topo = await (await fetch('/static/lib/world-atlas-2.0.2/countries-110m.json')).json();
    const fc = topojson.feature(topo, topo.objects.countries);
    fc.features = fc.features.filter(f => f.geometry && have.has(String(f.id).padStart(3, '0')));
    fc.features.forEach(f => {
      const g = f.geometry;
      (g.type === 'Polygon' ? [g.coordinates] : g.coordinates).forEach(p => p.forEach(unwrap));
    });
    L.geoJSON(fc, {
      style: { color: '#003D62', weight: 1, fillColor: '#003D62', fillOpacity: 0.18 },
      onEachFeature: (f, layer) => {
        const c = have.get(String(f.id).padStart(3, '0'));
        layer.bindTooltip(hallEsc(`${c.name} · ${c.count} чел.`), { sticky: true });
      },
    }).addTo(map).bringToBack();
  } catch (e) { /* без границ стран карта остаётся рабочей */ }
}

function renderCities(list, all) {
  const shown = all ? list : list.slice(0, CITY_LIMIT);
  const more = list.length > CITY_LIMIT
    ? `<button type="button" class="geo-more" id="geo-more">${all ? 'Свернуть' : `Все города (${list.length})`}</button>` : '';
  document.getElementById('cities').innerHTML = '<div class="geo-h">Города</div>'
    + shown.map(c => `<div><span>${hallEsc(c.name)}${c.country && c.country !== 'Россия' ? ` <i>${hallEsc(c.country)}</i>` : ''}</span>
      <b>${c.count}</b></div>`).join('') + more;
  const btn = document.getElementById('geo-more');
  if (btn) btn.onclick = () => renderCities(list, !all);
}

function drawLists(g) {
  document.getElementById('geo-note').textContent = `Город известен у ${g.known} из ${g.total} ${g.total % 10 === 1 && g.total % 100 !== 11 ? 'человека' : 'человек'} `
    + '(в протоколах эстафет города нет). Закрашены страны участников; число в кружке — сколько людей, нажмите — кто.';
  document.getElementById('countries').innerHTML = '<div class="geo-h">Страны</div>'
    + g.countries.map(c => `<div><span>${hallEsc(c.name || 'Страна не указана')}</span><b>${c.count}</b></div>`).join('');
  renderCities(g.cities, false);
}

hallLoad('/api/siberman/hall/geo').then(g => { drawLists(g); drawCities(g.cities); drawCountries(g.countries); })
  .catch(err => { document.querySelector('.geo-map').outerHTML = `<div class="state-msg">${hallEsc(err.message)}</div>`; });
