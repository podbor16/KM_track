import os
import mysql.connector
from typing import Optional


def get_duathlon_connection() -> Optional[mysql.connector.MySQLConnection]:
    try:
        return mysql.connector.connect(
            host=os.getenv("DB_HOST", "127.0.0.1"),
            port=int(os.getenv("DB_PORT", "3306")),
            database="duathlon_222",
            user=os.getenv("DB_USER", "km_analytic"),
            password=os.getenv("DB_PASSWORD"),
            charset="utf8mb4",
            autocommit=True,
            connection_timeout=10,
        )
    except Exception as e:
        import logging
        logging.getLogger(__name__).error(f"❌ duathlon_222 connect error: {e}")
        return None
