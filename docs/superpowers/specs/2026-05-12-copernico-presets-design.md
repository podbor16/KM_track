# Spec: Copernico Preset Configs

**Дата:** 2026-05-12  
**Статус:** Реализовано

---

## Проблема

Поля Copernico были захардкожены в `load_race_results.py`. Матчинг КТ-полей работал через динамические паттерны (`times.official_2.5km`, `times.real_kt1` и т.д.), что ненадёжно: каждый забег может использовать произвольные имена полей на усмотрение главного судьи. Кроме того, один пресет `km_analytics` возвращал все КТ-поля полумарафона даже для 5км дистанций, где они null.

## Решение

Каждый забег/дистанция имеет свой пресет в Copernico и описывает его в `config/copernico/<preset_name>.yaml`. Код читает поля оттуда — никакого динамического угадывания.

---

## Структура

```
config/
  copernico/
    km_pervomay_5km_2026.yaml   # Первомайский 5км — нет КТ с хронометражем
    km_pervomay_21km_2026.yaml  # Первомайский 21.1км — 7 КТ
    km_vesna_5km_2026.yaml      # Весна 5км — template (заполнить перед стартом)
  events/
    pervomay.yaml → preset: "km_pervomay_*"
    vesna.yaml    → preset: "km_vesna_5km_2026"
```

Имя файла = имя пресета в Copernico = значение `copernico.preset` в event YAML.

---

## Схема preset YAML

```yaml
description: "Краткое описание"

fields:
  bib: dorsal
  surname: surname
  name: name
  birthdate: birthdate
  gender: gender
  status: status
  category: category

time_fields:
  gun_start:   "times.official_:::start:::"   # обязательное
  gun_finish:  "times.official_:::finish:::"  # обязательное
  chip_start:  null                           # null если не предоставляется
  chip_finish: null                           # null если не предоставляется

checkpoint_fields:          # маппинг: наш kt1..kt7 → реальное поле Copernico
  kt1: "times.official_:::razvorot:::"
  # kt2..kt7: опциональны — включать только если пресет их возвращает
```

---

## Изменения в коде

### `load_race_results.py`
- `RaceLoader.__init__()`: добавлен параметр `preset_cfg: Optional[Dict]`
- `_build_kt_field_map()` → **удалён**, заменён на `_build_kt_field_map_from_preset()` который читает `checkpoint_fields` из preset_cfg
- Поля `times.official_:::start:::` и аналогичные заменены на переменные из `preset_cfg["time_fields"]`
- `main()`: загружает `config/copernico/{preset}.yaml` перед созданием `RaceLoader`; если файл не найден → `parser.error()` с подсказкой

### `scripts/prerace_check.py`
- Добавлен **блок G: Поля пресета**:
  1. Проверяет существование `config/copernico/{preset}.yaml` → OK/FAIL
  2. Если `race_id != null`: делает fetch из Copernico, сравнивает полученные ключи с ожидаемыми из конфига
  3. Missing fields → FAIL; unknown extra `times.*` fields → INFO

---

## Рабочий процесс для нового забега

1. Создать пресет в Copernico с нужными полями
2. Получить реальные имена полей из `race_data.json` (первый fetch)
3. Создать `config/copernico/<preset_name>.yaml` с явным маппингом
4. Обновить `copernico.preset` в event YAML
5. Запустить `prerace_check.py --config ... --distance ...` → блок G должен быть OK

---

## Известные особенности

- `times.official_15.9` (Первомайский 21.1км) — поле без суффикса `km` (аномалия Copernico). Захвачено явно в `km_pervomay_21km_2026.yaml`
- Весна 2026 (`km_vesna_5km_2026.yaml`) — `chip_start`, `chip_finish`, `kt1` заданы как `null` (placeholder). Заполнить после первого fetch в день забега
