-- Подписи/дистанции КТ теперь отдаются фронту из БД за выбранный год
-- (/api/siberman/results → checkpoints): у архивных лет 2016–2024 свой
-- набор КТ. Для 2025–2026 записываем ровно то, что до сих пор было
-- зашито во фронт (CHECKPOINT_LABELS/CHECKPOINT_DIST_KM в
-- siberman-common.js) — страницы этих лет не меняются.
UPDATE checkpoints SET label='Разворот 1 (1,3 км)', distance_km=1.30 WHERE race_year IN (2025, 2026) AND stage='swim' AND seq=1;
UPDATE checkpoints SET label='1 круг (2,6 км)', distance_km=2.60 WHERE race_year IN (2025, 2026) AND stage='swim' AND seq=2;
UPDATE checkpoints SET label='Разворот 2 (3,9 км)', distance_km=3.90 WHERE race_year IN (2025, 2026) AND stage='swim' AND seq=3;
UPDATE checkpoints SET label='2 круга (5,2 км)', distance_km=5.20 WHERE race_year IN (2025, 2026) AND stage='swim' AND seq=4;
UPDATE checkpoints SET label='Разворот 3 (6,5 км)', distance_km=6.50 WHERE race_year IN (2025, 2026) AND stage='swim' AND seq=5;
UPDATE checkpoints SET label='3 круга (7,8 км)', distance_km=7.80 WHERE race_year IN (2025, 2026) AND stage='swim' AND seq=6;
UPDATE checkpoints SET label='Финиш (10 км)', distance_km=10.00 WHERE race_year IN (2025, 2026) AND stage='swim' AND seq=7;
UPDATE checkpoints SET label='3 км', distance_km=3.00 WHERE race_year IN (2025, 2026) AND stage='bike_day1' AND seq=1;
UPDATE checkpoints SET label='10 км', distance_km=10.00 WHERE race_year IN (2025, 2026) AND stage='bike_day1' AND seq=2;
UPDATE checkpoints SET label='72 км (разворот)', distance_km=72.00 WHERE race_year IN (2025, 2026) AND stage='bike_day1' AND seq=3;
UPDATE checkpoints SET label='135 км', distance_km=135.00 WHERE race_year IN (2025, 2026) AND stage='bike_day1' AND seq=4;
UPDATE checkpoints SET label='142 км', distance_km=142.00 WHERE race_year IN (2025, 2026) AND stage='bike_day1' AND seq=5;
UPDATE checkpoints SET label='Финиш (145 км)', distance_km=145.00 WHERE race_year IN (2025, 2026) AND stage='bike_day1' AND seq=6;
UPDATE checkpoints SET label='51 км', distance_km=51.00 WHERE race_year IN (2025, 2026) AND stage='bike_day2' AND seq=1;
UPDATE checkpoints SET label='83 км', distance_km=83.00 WHERE race_year IN (2025, 2026) AND stage='bike_day2' AND seq=2;
UPDATE checkpoints SET label='119 км', distance_km=119.00 WHERE race_year IN (2025, 2026) AND stage='bike_day2' AND seq=3;
UPDATE checkpoints SET label='160 км (СШГЭС)', distance_km=160.00 WHERE race_year IN (2025, 2026) AND stage='bike_day2' AND seq=4;
UPDATE checkpoints SET label='196.7 км (Кольцо Саяногорск)', distance_km=196.70 WHERE race_year IN (2025, 2026) AND stage='bike_day2' AND seq=5;
UPDATE checkpoints SET label='205.6 км', distance_km=205.60 WHERE race_year IN (2025, 2026) AND stage='bike_day2' AND seq=6;
UPDATE checkpoints SET label='265 км', distance_km=265.00 WHERE race_year IN (2025, 2026) AND stage='bike_day2' AND seq=7;
UPDATE checkpoints SET label='Финиш (276 км)', distance_km=276.00 WHERE race_year IN (2025, 2026) AND stage='bike_day2' AND seq=8;
UPDATE checkpoints SET label='1 круг (7 км)', distance_km=7.00 WHERE race_year IN (2025, 2026) AND stage='run' AND seq=1;
UPDATE checkpoints SET label='2 круг (14 км)', distance_km=14.00 WHERE race_year IN (2025, 2026) AND stage='run' AND seq=2;
UPDATE checkpoints SET label='3 круг (21 км)', distance_km=21.00 WHERE race_year IN (2025, 2026) AND stage='run' AND seq=3;
UPDATE checkpoints SET label='4 круг (28 км)', distance_km=28.00 WHERE race_year IN (2025, 2026) AND stage='run' AND seq=4;
UPDATE checkpoints SET label='5 круг (35 км)', distance_km=35.00 WHERE race_year IN (2025, 2026) AND stage='run' AND seq=5;
UPDATE checkpoints SET label='6 круг (42 км)', distance_km=42.00 WHERE race_year IN (2025, 2026) AND stage='run' AND seq=6;
UPDATE checkpoints SET label='7 круг (49 км)', distance_km=49.00 WHERE race_year IN (2025, 2026) AND stage='run' AND seq=7;
UPDATE checkpoints SET label='8 круг (56 км)', distance_km=56.00 WHERE race_year IN (2025, 2026) AND stage='run' AND seq=8;
UPDATE checkpoints SET label='9 круг (63 км)', distance_km=63.00 WHERE race_year IN (2025, 2026) AND stage='run' AND seq=9;
UPDATE checkpoints SET label='10 круг (70 км)', distance_km=70.00 WHERE race_year IN (2025, 2026) AND stage='run' AND seq=10;
UPDATE checkpoints SET label='11 круг (77 км)', distance_km=77.00 WHERE race_year IN (2025, 2026) AND stage='run' AND seq=11;
UPDATE checkpoints SET label='Финиш — 12 круг (84 км)', distance_km=84.00 WHERE race_year IN (2025, 2026) AND stage='run' AND seq=12;
