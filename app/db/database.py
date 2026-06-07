import os
import psycopg2
 
def get_db():
    return psycopg2.connect(
        host=os.getenv("DB_HOST", "localhost"),
        port=int(os.getenv("DB_PORT", "5432")),
        dbname=os.getenv("DB_NAME", "app_db"),
        user=os.getenv("DB_USER", "user"),
        password=os.getenv("DB_PASSWORD", "pass"),
    )