import psycopg2
from psycopg2.extras import RealDictCursor

# Try Session Pooler format
conn_str = "postgresql://postgres.jduyxfhqosoaijbfisxh:123Getr$chhh@aws-1-eu-west-2.pooler.supabase.com:5432/postgres"

try:
    print("Attempting to connect to Supabase...")
    conn = psycopg2.connect(conn_str, cursor_factory=RealDictCursor)
    cursor = conn.cursor()
    cursor.execute("SELECT id, username, role FROM users WHERE username = 'testmanager';")
    user = cursor.fetchone()
    print("Connection Successful!")
    print("Fetched User Row:", user)
    conn.close()
except Exception as e:
    print("\n--- CONNECTION ERROR DETAILS ---")
    print(e)