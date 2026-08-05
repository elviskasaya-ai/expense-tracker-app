import hashlib
import sqlite3
from datetime import datetime
import matplotlib.pyplot as plt
import pandas as pd
import streamlit as st


def hash_password(password):
    return hashlib.sha256(password.encode()).hexdigest()


class DatabaseManager:

    def __init__(self, db_file="expenses.db"):
        self.db_file = db_file
        self.init_db()

    def _get_connection(self):
        return sqlite3.connect(self.db_file)

    def init_db(self):
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS users (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    username TEXT UNIQUE NOT NULL,
                    password TEXT NOT NULL
                )
            """)
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS expenses (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER NOT NULL,
                    amount REAL NOT NULL,
                    category TEXT NOT NULL,
                    description TEXT,
                    date TEXT NOT NULL,
                    FOREIGN KEY(user_id) REFERENCES users(id)
                )
            """)
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS budgets (
                    user_id INTEGER NOT NULL,
                    category TEXT NOT NULL,
                    limit_amount REAL NOT NULL,
                    PRIMARY KEY (user_id, category),
                    FOREIGN KEY(user_id) REFERENCES users(id)
                )
            """)
            conn.commit()

    def register_user(self, username, password):
        try:
            with self._get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute(
                    "INSERT INTO users (username, password) VALUES (?, ?)",
                    (username, hash_password(password)),
                )
                conn.commit()
                return True
        except sqlite3.IntegrityError:
            return False

    def authenticate_user(self, username, password):
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT id FROM users WHERE username = ? AND password = ?",
                (username, hash_password(password)),
            )
            result = cursor.fetchone()
            return result[0] if result else None

    def add_expense(self, user_id, amount, category, description, date):
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                INSERT INTO expenses (user_id, amount, category, description, date)
                VALUES (?, ?, ?, ?, ?)
            """,
                (user_id, amount, category, description, date),
            )
            conn.commit()

    def get_expenses(self, user_id, category=None, month=None):
        query = (
            "SELECT id, date, category, amount, description FROM expenses WHERE"
            " user_id = ?"
        )
        params = [user_id]

        if category:
            query += " AND category = ?"
            params.append(category)
        if month:
            query += " AND date LIKE ?"
            params.append(f"{month}%")

        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(query, params)
            return cursor.fetchall()

    def get_category_breakdown(self, user_id):
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT category, SUM(amount) FROM expenses WHERE user_id = ?"
                " GROUP BY category",
                (user_id,),
            )
            breakdown = cursor.fetchall()

            cursor.execute(
                "SELECT SUM(amount) FROM expenses WHERE user_id = ?", (user_id,)
            )
            total_result = cursor.fetchone()[0]
            total_all = total_result if total_result else 0.0

            return breakdown, total_all

    def delete_expense(self, user_id, expense_id):
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "DELETE FROM expenses WHERE id = ? AND user_id = ?",
                (expense_id, user_id),
            )
            conn.commit()
            return cursor.rowcount > 0

    def set_budget(self, user_id, category, limit_amount):
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                INSERT INTO budgets (user_id, category, limit_amount)
                VALUES (?, ?, ?)
                ON CONFLICT(user_id, category) DO UPDATE SET limit_amount = excluded.limit_amount
            """,
                (user_id, category, limit_amount),
            )
            conn.commit()

    def get_budgets(self, user_id):
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT category, limit_amount FROM budgets WHERE user_id = ?",
                (user_id,),
            )
            return {row[0]: row[1] for row in cursor.fetchall()}


# --- App Setup ---
db = DatabaseManager("expenses.db")
st.set_page_config(
    page_title="Personal Finance Tracker", page_icon="💰", layout="wide"
)

# Session State Initialization
if "user_id" not in st.session_state:
    st.session_state["user_id"] = None
if "username" not in st.session_state:
    st.session_state["username"] = None

# --- Authentication Screen ---
if st.session_state["user_id"] is None:
    st.title("💰 Personal Finance Tracker")
    tab1, tab2 = st.tabs(["Login", "Register"])

    with tab1:
        st.subheader("Account Login")
        login_user = st.text_input("Username", key="login_user").strip()
        login_pass = st.text_input(
            "Password", type="password", key="login_pass"
        )
        if st.button("Log In", type="primary"):
            user_id = db.authenticate_user(login_user, login_pass)
            if user_id:
                st.session_state["user_id"] = user_id
                st.session_state["username"] = login_user
                st.success(f"Welcome back, {login_user}!")
                st.rerun()
            else:
                st.error("Invalid username or password.")

    with tab2:
        st.subheader("Create New Account")
        reg_user = st.text_input("Choose Username", key="reg_user").strip()
        reg_pass = st.text_input(
            "Choose Password", type="password", key="reg_pass"
        )
        if st.button("Register"):
            if reg_user and reg_pass:
                if db.register_user(reg_user, reg_pass):
                    st.success("Account created successfully! Please log in.")
                else:
                    st.error("Username already exists. Please pick another.")
            else:
                st.error("Please provide both username and password.")

# --- Logged-In App Interface ---
else:
    user_id = st.session_state["user_id"]
    username = st.session_state["username"]

    st.sidebar.write(f"👤 Logged in as: **{username}**")
    if st.sidebar.button("Log Out"):
        st.session_state["user_id"] = None
        st.session_state["username"] = None
        st.rerun()

    st.title("💰 Personal Finance Tracker")

    menu = st.sidebar.radio(
        "Navigation",
        [
            "Add Expense",
            "View Expenses",
            "Visual Analytics",
            "Set Budgets",
            "Delete Expense",
        ],
    )

    if menu == "Add Expense":
        st.subheader("Add New Expense")
        with st.form("add_form", clear_on_submit=True):
            amount = st.number_input(
                "Amount ($)", min_value=0.01, step=0.01, format="%.2f"
            )
            category = (
                st.text_input("Category (e.g., Food, Rent, Transport)")
                .title()
                .strip()
            )
            description = st.text_input("Description").strip()
            date = st.date_input("Date", datetime.now()).strftime("%Y-%m-%d")

            submitted = st.form_submit_button("Save Expense")
            if submitted:
                if not category:
                    st.error("Please enter a category.")
                else:
                    db.add_expense(user_id, amount, category, description, date)
                    st.success(f"Added ${amount:.2f} under '{category}'!")

                    budgets = db.get_budgets(user_id)
                    if category in budgets:
                        breakdown, _ = db.get_category_breakdown(user_id)
                        spent = next(
                            (b[1] for b in breakdown if b[0] == category), 0.0
                        )
                        limit = budgets[category]
                        if spent > limit:
                            st.error(
                                f"🚨 Alert: This entry pushed **{category}** over"
                                f" budget (${spent:.2f} / ${limit:.2f})!"
                            )

    elif menu == "View Expenses":
        st.subheader("Filter & View Expenses")
        col1, col2 = st.columns(2)
        with col1:
            cat_filter = st.text_input("Filter by Category").title().strip()
        with col2:
            month_filter = st.text_input("Filter by Month (YYYY-MM)").strip()

        rows = db.get_expenses(
            user_id,
            category=cat_filter if cat_filter else None,
            month=month_filter if month_filter else None,
        )

        if rows:
            df = pd.DataFrame(
                rows,
                columns=["ID", "Date", "Category", "Amount ($)", "Description"],
            )
            st.dataframe(df, use_container_width=True)

            total = sum(r[3] for r in rows)
            st.metric("Total Spending (Filtered)", f"${total:.2f}")

            csv_data = df.to_csv(index=False).encode("utf-8")
            st.download_button(
                label="📥 Export to CSV",
                data=csv_data,
                file_name=f"expenses_{datetime.now().strftime('%Y%m%d')}.csv",
                mime="text/csv",
            )
        else:
            st.info("No matching expenses found.")

    elif menu == "Visual Analytics":
        st.subheader("Spending Breakdown")
        breakdown, total_all = db.get_category_breakdown(user_id)

        if breakdown:
            col1, col2 = st.columns([1, 1])
            with col1:
                st.metric("Grand Total", f"${total_all:.2f}")
                for cat, amt in breakdown:
                    st.write(
                        f"**{cat}:** ${amt:.2f} ({(amt / total_all) * 100:.1f}%)"
                    )

            with col2:
                categories = [r[0] for r in breakdown]
                amounts = [r[1] for r in breakdown]

                fig, ax = plt.subplots(figsize=(6, 6))
                ax.pie(
                    amounts,
                    labels=categories,
                    autopct="%1.1f%%",
                    startangle=140,
                )
                st.pyplot(fig)
        else:
            st.info("No expenses recorded to analyze yet.")

    elif menu == "Set Budgets":
        st.subheader("🎯 Set Category Budgets")

        with st.form("budget_form"):
            cat = st.text_input("Category (e.g., Food, Rent)").title().strip()
            limit = st.number_input(
                "Monthly Limit ($)", min_value=1.0, step=10.0, format="%.2f"
            )
            if st.form_submit_button("Save Budget"):
                if cat:
                    db.set_budget(user_id, cat, limit)
                    st.success(f"Set budget for **{cat}** to **${limit:.2f}**")
                else:
                    st.error("Please specify a category.")

        st.write("---")
        st.subheader("Current Budget Tracking")
        budgets = db.get_budgets(user_id)
        breakdown, _ = db.get_category_breakdown(user_id)
        spent_dict = {row[0]: row[1] for row in breakdown}

        if not budgets:
            st.info("No budgets set yet.")
        else:
            for cat, limit_amt in budgets.items():
                spent = spent_dict.get(cat, 0.0)
                ratio = min(spent / limit_amt, 1.0)

                st.write(f"**{cat}**: ${spent:.2f} / ${limit_amt:.2f}")
                st.progress(ratio)

                if spent > limit_amt:
                    st.error(f"🚨 Over budget by **${spent - limit_amt:.2f}**!")

    elif menu == "Delete Expense":
        st.subheader("Delete Expense")
        rows = db.get_expenses(user_id)

        if rows:
            df = pd.DataFrame(
                rows,
                columns=["ID", "Date", "Category", "Amount ($)", "Description"],
            )
            st.dataframe(df, use_container_width=True)

            target_id = st.number_input(
                "Enter ID of expense to delete", min_value=1, step=1
            )
            if st.button("Delete Entry", type="primary"):
                if db.delete_expense(user_id, int(target_id)):
                    st.success(f"Expense ID {target_id} deleted!")
                    st.rerun()
                else:
                    st.error(f"ID {target_id} not found.")
        else:
            st.info("No expenses available to delete.")