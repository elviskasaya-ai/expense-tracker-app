import os
import hashlib
import psycopg2
from psycopg2.extras import RealDictCursor

# Updated Supabase Connection using IPv4 Direct / Pooler settings
DEFAULT_DB_URL = "postgresql://postgres.jduyxfhqosoaijbfisxh:123Getr$chhh@aws-1-eu-west-2.pooler.supabase.com:5432/postgres"

def get_db_connection():
    conn_str = os.environ.get("DATABASE_URL", DEFAULT_DB_URL)
    return psycopg2.connect(conn_str, cursor_factory=RealDictCursor)

def get_manager_dashboard_stats():
    """Fetches high-level metrics for the Manager Analytics tab."""
    conn = get_db_connection()
    cursor = conn.cursor()
    
    # Total Paid Amount & Count
    cursor.execute("SELECT COUNT(*), COALESCE(SUM(amount), 0) FROM bills WHERE status = 'PAID';")
    paid_count, total_paid = cursor.fetchone().values()

    # Total Pending Amount & Count
    cursor.execute("SELECT COUNT(*), COALESCE(SUM(amount), 0) FROM bills WHERE status = 'PENDING_APPROVAL';")
    pending_count, total_pending = cursor.fetchone().values()

    conn.close()
    return {
        "paid_count": paid_count,
        "total_paid": float(total_paid),
        "pending_count": pending_count,
        "total_pending": float(total_pending)
    }

def get_bills_by_category():
    """Fetches total expenditure grouped by bill category."""
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT category, COALESCE(SUM(amount), 0) as total 
        FROM bills 
        WHERE status = 'PAID' 
        GROUP BY category 
        ORDER BY total DESC;
    """)
    rows = cursor.fetchall()
    conn.close()
    return rows
def get_pending_bills():
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("""
            SELECT id, user_id, requested_by, payee_phone, amount,
                   category, bill_ref, due_date, status, created_at
            FROM bills
            WHERE status = 'PENDING_APPROVAL'
            ORDER BY created_at DESC;
        """)
        bills = cursor.fetchall()
        conn.close()
        return bills
    except Exception as e:
        print(f"Error fetching pending bills: {e}")
        return []
def authenticate_user(username, password):
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute(
            "SELECT id, role, password_hash FROM users WHERE username = %s;",
            (username,)
        )
        user = cursor.fetchone()
        conn.close()

        if not user:
            return None, None

        stored = user["password_hash"]
        provided = password

        if stored == provided:
            return user["id"], user["role"]

        hashed = hashlib.sha256(password.encode()).hexdigest()
        if stored == hashed:
            return user["id"], user["role"]

        return None, None
    except Exception as e:
        print(f"Auth error: {e}")
        return None, None