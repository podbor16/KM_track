"""Песочница siberman_demo: копия таблиц результатов из локальной siberman (спека п. 2)."""
import os

import mysql.connector

LOCAL_HOSTS = ('127.0.0.1', 'localhost')
LOCAL_PORT = 3308
TABLES = (
    'participants', 'checkpoints', 'checkpoint_times', 'transitions', 'stage_totals',
    'overall_results', 'race_config', 'siberman_records', 'siberman_persons',
    'siberman_person_links',
)


def _env_params() -> dict:
    """Параметры из окружения; недостающие - из .env.local (приоритет у окружения)."""
    from dotenv import dotenv_values
    root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
    file_vals = dotenv_values(os.path.join(root, '.env.local'))

    def get(k, d=None):
        return os.environ.get(k) or file_vals.get(k) or d

    return {
        'host': get('DB_HOST', '127.0.0.1'),
        'port': int(get('DB_PORT', LOCAL_PORT)),
        'user': get('DB_USER', 'root'),
        'password': get('DB_PASSWORD', ''),
    }


def assert_local(host, port) -> None:
    if host not in LOCAL_HOSTS or int(port) != LOCAL_PORT:
        raise RuntimeError(f"Только локальный MySQL {LOCAL_HOSTS[0]}:{LOCAL_PORT}, получено {host}:{port}")


def connect(database=None):
    p = _env_params()
    assert_local(p['host'], p['port'])
    kw = dict(p, charset='utf8mb4', use_unicode=True)
    if database:
        kw['database'] = database
    return mysql.connector.connect(**kw)


def recreate(src='siberman', dst='siberman_demo') -> None:
    if dst == src or dst == 'siberman':
        raise RuntimeError("Песочница не может совпадать с исходной БД")
    conn = connect()
    try:
        cur = conn.cursor()
        cur.execute(f"DROP DATABASE IF EXISTS `{dst}`")
        cur.execute(f"CREATE DATABASE `{dst}` CHARACTER SET utf8mb4")
        cur.execute("SET FOREIGN_KEY_CHECKS=0")
        for t in TABLES:
            cur.execute(f"CREATE TABLE `{dst}`.`{t}` LIKE `{src}`.`{t}`")
            cur.execute(f"INSERT INTO `{dst}`.`{t}` SELECT * FROM `{src}`.`{t}`")
        cur.execute("SET FOREIGN_KEY_CHECKS=1")
        conn.commit()
    finally:
        conn.close()
