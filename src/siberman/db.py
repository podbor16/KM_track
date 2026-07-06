import os
import mysql.connector
from typing import Optional


def get_siberman_connection() -> Optional[mysql.connector.MySQLConnection]:
    try:
        return mysql.connector.connect(
            host=os.getenv("DB_HOST", "127.0.0.1"),
            port=int(os.getenv("DB_PORT", "3306")),
            database=os.getenv("SIBERMAN_DB_NAME", "siberman"),
            user=os.getenv("DB_USER", "km_analytic"),
            password=os.getenv("DB_PASSWORD"),
            charset="utf8mb4",
            autocommit=True,
            connection_timeout=10,
        )
    except Exception as e:
        import logging
        logging.getLogger(__name__).error(f"❌ siberman connect error: {e}")
        return None
