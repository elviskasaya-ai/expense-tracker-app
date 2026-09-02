import os
import hashlib
import psycopg2
from psycopg2.extras import RealDictCursor

# Updated Supabase Connection using IPv4 Direct / Pooler settings
DEFAULT_DB_URL = "postgresql://postgres.smrrldaavpjoipqgvhxv:123Getr$chhh@aws-0-eu-central-1.pooler.supabase.com:6543/postgres?sslmode=require"

def get_db_connection():
    conn_str = os.environ.get("DATABASE_URL", DEFAULT_DB_URL)
    return psycopg2.connect(conn_str, cursor_factory=RealDictCursor)