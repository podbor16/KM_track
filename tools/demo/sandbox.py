"""Общие песочницы *_demo: копия таблиц из локальной БД и подмена подключения прод-сервиса."""
import os
from contextlib import contextmanager

import itertools

import mysql.connector
from mysql.connector import pooling

LOCAL_HOSTS = ('127.0.0.1', 'localhost')
LOCAL_PORT = 3308
_pool_ids = itertools.count(1)


def _env_params() -> dict:
    """Параметры из окружения; недостающие - из .env.local (приоритет у окружения)."""
    from dotenv import dotenv_values
    root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
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


def recreate(src: str, dst: str, tables=None) -> None:
    """Пересоздаёт dst копией таблиц src (tables=None - все таблицы src). dst обязан оканчиваться на _demo."""
    if dst == src or not dst.endswith('_demo'):
        raise RuntimeError("Песочница должна оканчиваться на _demo и не совпадать с исходной БД")
    conn = connect()
    try:
        cur = conn.cursor()
        if tables is None:
            cur.execute(f"SHOW FULL TABLES FROM `{src}` WHERE Table_type='BASE TABLE'")
            tables = [r[0] for r in cur.fetchall()]
        cur.execute(f"DROP DATABASE IF EXISTS `{dst}`")
        cur.execute(f"CREATE DATABASE `{dst}` CHARACTER SET utf8mb4")
        cur.execute("SET FOREIGN_KEY_CHECKS=0")
        for t in tables:
            cur.execute(f"CREATE TABLE `{dst}`.`{t}` LIKE `{src}`.`{t}`")
            cur.execute(f"INSERT INTO `{dst}`.`{t}` SELECT * FROM `{src}`.`{t}`")
        cur.execute("SET FOREIGN_KEY_CHECKS=1")
        conn.commit()
    finally:
        conn.close()


@contextmanager
def use_sandbox(service_module, attr: str, dbname: str):
    """Подменяет service_module.<attr> (функцию подключения прод-сервиса) подключением к песочнице dbname."""
    if not dbname.endswith('_demo'):
        raise RuntimeError("Подмена разрешена только на БД *_demo")
    p = _env_params()
    assert_local(p['host'], p['port'])
    # пул: close() прод-кода возвращает соединение (со сбросом сессии — новая транзакция, как у
    # свежего соединения), без TCP/auth-рукопожатия на каждый вызов
    pool = pooling.MySQLConnectionPool(pool_name=f"demo_{next(_pool_ids)}", pool_size=4,
                                       charset='utf8mb4', use_unicode=True, database=dbname, **p)
    original = getattr(service_module, attr)
    setattr(service_module, attr, pool.get_connection)
    try:
        yield
    finally:
        setattr(service_module, attr, original)
        pool._remove_connections()
