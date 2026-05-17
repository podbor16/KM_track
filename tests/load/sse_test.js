/**
 * k6 нагрузочный тест SSE-соединений KM_track.
 * Каждый VU держит SSE-соединение K6_CONN_HOLD секунд (по умолчанию 30),
 * затем переподключается — имитирует реального зрителя трекера.
 *
 * Запуск:
 *   k6 run tests/load/sse_test.js --vus 335 --duration 8m
 *
 * Переменные окружения:
 *   K6_HOST        — хост (по умолч. https://analytics.krasmarafon.ru)
 *   K6_EVENT_ID    — event_id для SSE (по умолч. 106)
 *   K6_CONN_HOLD   — секунд держать соединение (по умолч. 30)
 */

import http from 'k6/http';
import { check } from 'k6';
import { Rate, Trend } from 'k6/metrics';

const HOST = __ENV.K6_HOST || 'https://analytics.krasmarafon.ru';
const EVENT_ID = __ENV.K6_EVENT_ID || '106';
const CONN_HOLD_S = parseInt(__ENV.K6_CONN_HOLD || '30', 10);

// Кастомные метрики
const sseErrorRate = new Rate('sse_error_rate');
const sseTimeToFirstByte = new Trend('sse_ttfb_ms', true);

export const options = {
  // vus и duration задаются снаружи через CLI
  thresholds: {
    'sse_error_rate': ['rate<0.01'],           // < 1% ошибок подключения
    'sse_ttfb_ms': ['p(95)<3000'],             // TTFB p95 < 3с
    'http_req_failed': ['rate<0.01'],
  },
};

export default function () {
  const url = `${HOST}/api/sse/tracker?event_id=${EVENT_ID}`;

  const res = http.get(url, {
    headers: {
      'Accept': 'text/event-stream',
      'Cache-Control': 'no-cache',
    },
    timeout: `${CONN_HOLD_S + 10}s`,
  });

  const ok = check(res, {
    'SSE: статус 200': (r) => r.status === 200,
    'SSE: content-type text/event-stream': (r) =>
      (r.headers['Content-Type'] || '').includes('text/event-stream'),
  });

  sseErrorRate.add(!ok);
  if (res.timings) {
    sseTimeToFirstByte.add(res.timings.waiting);
  }
}
