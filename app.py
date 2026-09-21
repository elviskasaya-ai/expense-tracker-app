import base64
from datetime import datetime, date
import hashlib
import matplotlib.pyplot as plt
import pandas as pd
import requests
import streamlit as st

# Import database connection helper
import db
from db import (
    get_db_connection,
    get_pending_bills,
    get_manager_dashboard_stats,
    get_bills_by_category,
    get_manager_dashboard_stats,
    get_bills_by_category,
    authenticate_user,
)


# --- Security Utilities ---
def hash_password(password):
    return hashlib.sha256(password.encode()).hexdigest()


# --- M-Pesa Daraja B2C Integration ---
def get_mpesa_access_token(consumer_key, consumer_secret, env="sandbox"):
    base_url = (
        "https://sandbox.safaricom.co.ke"
        if env == "sandbox"
        else "https://api.safaricom.co.ke"
    )
    url = f"{base_url}/oauth/v1/generate?grant_type=client_credentials"
    try:
        response = requests.get(
            url, auth=(consumer_key, consumer_secret), timeout=10
        )
        if response.status_code == 200:
            return response.json().get("access_token")
    except Exception:
        pass
    return None


def trigger_b2c_payout(
    payee_phone,
    amount,
    account_ref,
    consumer_key,
    consumer_secret,
    initiator_name,
    security_credential,
    shortcode,
    env="sandbox",
):
    token = get_mpesa_access_token(consumer_key, consumer_secret, env)
    if not token:
        return (
            False,
            "Failed to obtain Daraja Access Token. Verify Consumer Key and Secret.",
        )

    # Format phone number to 254...
    phone = str(payee_phone).strip().replace("+", "")
    if phone.startswith("0"):
        phone = "254" + phone[1:]
    elif phone.startswith("7") or phone.startswith("1"):
        phone = "254" + phone

    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
    }

    payload = {
        "InitiatorName": initiator_name,
        "SecurityCredential": security_credential,
        "CommandID": "BusinessPayment",
        "Amount": int(amount),
        "PartyA": shortcode,
        "PartyB": phone,
        "Remarks": f"Payment {account_ref}",
        "QueueTimeOutURL": "https://example.com/api/b2c/timeout",
        "ResultURL": "https://example.com/api/b2c/result",
        "Occasion": account_ref,
    }

    base_url = (
        "https://sandbox.safaricom.co.ke"
        if env == "sandbox"
        else "https://api.safaricom.co.ke"
    )
    url = f"{base_url}/mpesa/b2c/v1/paymentrequest"
    try:
        response = requests.post(url, json=payload, headers=headers, timeout=15)
        res_data = response.json()
        if response.status_code == 200 and res_data.get("ResponseCode") == "0":
            return True, res_data
        else:
            err = (
                res_data.get("errorMessage")
                or res_data.get("ResponseDescription")
                or "B2C Payout failed."
            )
            return False, err
    except Exception as e:
        return False, str(e)


# --- Database Operations (Supabase PostgreSQL) ---
class DatabaseManager:

    def register_user(self, username, password, role="Staff"):
        try:
            conn = get_db_connection()
            cur = conn.cursor()
            cur.execute(
                "INSERT INTO users (username, password, role) VALUES (%s, %s, %s)",
                (username, hash_password(password), role),
            )
            conn.commit()
            cur.close()
            conn.close()
            return True, "Success"
        except Exception as e:
            return False, str(e)

    def authenticate_user(self, username, password):
        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute(
            "SELECT id, role FROM users WHERE username = %s AND password_hash = %s",
            (username, hash_password(password)),
        )
        result = cur.fetchone()
        cur.close()
        conn.close()
        if result:
            return result["id"], result["role"]
        return None, None

    def schedule_bill(
        self,
        user_id,
        payer_phone,
        payee_phone,
        amount,
        category,
        bill_ref,
        due_date,
        requested_by,
    ):
        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute(
            """
            INSERT INTO scheduled_bills 
            (user_id, payer_phone, payee_phone, amount, category, bill_ref, due_date, status, requested_by)
            VALUES (%s, %s, %s, %s, %s, %s, %s, 'PENDING_APPROVAL', %s)
        """,
            (
                user_id,
                payer_phone,
                payee_phone,
                amount,
                category,
                bill_ref,
                due_date,
                requested_by,
            ),
        )
        conn.commit()
        cur.close()
        conn.close()

    def get_pending_bills(self):
        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute(
            "SELECT id, payer_phone, payee_phone, amount, category, bill_ref, due_date, requested_by, user_id "
            "FROM scheduled_bills WHERE status = 'PENDING_APPROVAL' ORDER BY due_date ASC"
        )
        rows = cur.fetchall()
        cur.close()
        conn.close()
        return rows

    def get_user_scheduled_bills(self, user_id):
        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute(
            "SELECT id, payee_phone, amount, category, bill_ref, due_date, status, requested_by "
            "FROM scheduled_bills WHERE user_id = %s ORDER BY due_date ASC",
            (user_id,),
        )
        rows = cur.fetchall()
        cur.close()
        conn.close()
        return rows

    def mark_bill_as_approved_and_paid(self, bill_id, manager_username):
        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute(
            "UPDATE scheduled_bills SET status = 'APPROVED & PAID', approved_by = %s WHERE id = %s",
            (manager_username, bill_id),
        )
        conn.commit()
        cur.close()
        conn.close()

    def reject_bill(self, bill_id):
        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute(
            "UPDATE scheduled_bills SET status = 'REJECTED' WHERE id = %s",
            (bill_id,),
        )
        conn.commit()
        cur.close()
        conn.close()

    def add_expense(self, user_id, amount, category, description, date):
        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute(
            """
            INSERT INTO expenses (user_id, amount, category, description, date)
            VALUES (%s, %s, %s, %s, %s)
        """,
            (user_id, amount, category, description, date),
        )
        conn.commit()
        cur.close()
        conn.close()

    def get_expenses(self, user_id=None):
        conn = get_db_connection()
        cur = conn.cursor()
        if user_id:
            cur.execute(
                "SELECT id, date, category, amount, description FROM expenses WHERE user_id = %s",
                (user_id,),
            )
        else:
            cur.execute("SELECT id, date, category, amount, description FROM expenses")
        rows = cur.fetchall()
        cur.close()
        conn.close()
        return rows

    def get_category_breakdown(self):
        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute(
            "SELECT category, SUM(amount) as total FROM expenses GROUP BY category"
        )
        breakdown = cur.fetchall()

        cur.execute("SELECT SUM(amount) as total FROM expenses")
        total_result = cur.fetchone()
        total_all = (
            float(total_result["total"])
            if total_result and total_result["total"]
            else 0.0
        )
        cur.close()
        conn.close()
        return breakdown, total_all


# --- App Setup ---
db = DatabaseManager()
st.set_page_config(
    page_title="Multi-User Scheduled Bill Approvals",
    page_icon="🏢",
    layout="wide",
)

if "user_id" not in st.session_state:
    st.session_state["user_id"] = None
if "username" not in st.session_state:
    st.session_state["username"] = None
if "role" not in st.session_state:
    st.session_state["role"] = None

# --- Authentication Section ---
if st.session_state["user_id"] is None:
    st.title("🏢 Multi-User Bill Payment & Approval Portal")
    
    # Check if a registration success message is pending display
    if "reg_success" in st.session_state:
        st.success(st.session_state["reg_success"])
        del st.session_state["reg_success"]

    tab1, tab2 = st.tabs(["🔒 Account Login", "📝 Register User"])

    with tab1:
        st.subheader("Login")
        login_user = st.text_input("Username", key="login_user").strip()
        login_pass = st.text_input("Password", type="password", key="login_pass")
        if st.button("Log In", type="primary"):
            u_id, u_role = authenticate_user(login_user, login_pass)
            if u_id:
                st.session_state["user_id"] = u_id
                st.session_state["username"] = login_user
                st.session_state["role"] = u_role
                st.rerun()
            else:
                st.error("Invalid username or password.")

    with tab2:
        st.subheader("Create Account")
        reg_user = st.text_input("Choose Username", key="reg_user").strip()
        reg_pass = st.text_input("Choose Password", type="password", key="reg_pass")
        reg_role = st.selectbox(
            "Role", ["Staff", "Manager"], help="Manager can approve & trigger payouts"
        )
        if st.button("Register"):
            if reg_user and reg_pass:
                # Calls register_user cleanly
                user_id = register_user(reg_user, reg_pass, reg_role)
                if user_id:
                    st.session_state["reg_success"] = f"Account for '{reg_user}' created successfully! Switch to the Login tab to sign in."
                    st.rerun()
                else:
                    st.error("🚨 Registration failed. Username might already be taken.")
            else:
                st.error("Please fill in all fields.")

# --- Logged-In System Dashboard ---
else:
    user_id = st.session_state["user_id"]
    username = st.session_state["username"]
    role = st.session_state["role"]

    st.sidebar.write(f"👤 Logged in as: **{username}**")
    st.sidebar.caption(f"Role: **{role}**")
    if st.sidebar.button("Log Out"):
        st.session_state["user_id"] = None
        st.session_state["username"] = None
        st.session_state["role"] = None
        st.rerun()

    st.sidebar.write("---")

    # ==========================================
    # STAFF WORKFLOW
    # ==========================================
    if role == "Staff":
        tab1, tab2 = st.tabs(["📝 Request Bill Payment", "📋 My Requested Bills"])
        
        with tab1:
            st.subheader("Submit Bill for Approval")
            with st.form("staff_request_form"):
                payee_phone = st.text_input("Payee Phone Number (e.g., 254712345678)")
                amount = st.number_input("Amount (KES)", min_value=1.0, step=10.0)
                category = st.selectbox("Category", ["Utilities", "Supplies", "Rent", "Services", "Other"])
                bill_ref = st.text_input("Bill Reference / Account No.")
                due_date = st.date_input("Due Date")
                
                submit_req = st.form_submit_button("Submit Request")
                if submit_req:
                    if payee_phone and amount > 0:
                        create_scheduled_bill(
                            user_id, username, payee_phone, amount, category, bill_ref, due_date
                        )
                        st.success("Payment request submitted successfully for Manager review!")
                    else:
                        st.error("Please enter a valid phone number and amount.")

        with tab2:
            st.subheader("My Submissions")
            my_bills = get_user_bills(user_id)
            if my_bills:
                st.dataframe(my_bills, use_container_width=True)
            else:
                st.info("You have not submitted any bill requests yet.")

    # ==========================================
    # MANAGER WORKFLOW
    # ==========================================
    elif role == "Manager":
        tab1, tab2 = st.tabs(["🛡️ Approvals & Disbursal", "📊 Analytics & Reports"])
        
        # TAB 1: Pending Approvals & M-Pesa Disbursal
        with tab1:
            st.subheader("Pending Bill Approvals")
            pending_bills = get_pending_bills() # Ensure function returns pending bills
            
            if pending_bills:
                for bill in pending_bills:
                    with st.expander(f"Bill #{bill['id']} - KES {bill['amount']} ({bill['category']})"):
                        st.write(f"**Requested by:** {bill['requested_by']}")
                        st.write(f"**Payee Phone:** {bill['payee_phone']}")
                        st.write(f"**Reference:** {bill['bill_ref']}")
                        st.write(f"**Due Date:** {bill['due_date']}")
                        
                        col1, col2 = st.columns(2)
                        with col1:
                            if st.button(f"Approve & Disburse M-Pesa", key=f"pay_{bill['id']}", type="primary"):
                                # Trigger M-Pesa B2C Payout Logic Here
                                update_bill_status(bill['id'], "PAID")
                                st.success(f"Payment of KES {bill['amount']} disbursed to {bill['payee_phone']}!")
                                st.rerun()
                        with col2:
                            if st.button(f"Reject Bill", key=f"reject_{bill['id']}"):
                                update_bill_status(bill['id'], "REJECTED")
                                st.warning(f"Bill #{bill['id']} rejected.")
                                st.rerun()
            else:
                st.info("No pending bill requests requiring approval.")

        # TAB 2: Executive Analytics
        with tab2:
            st.subheader("Financial Overview")
            stats = get_manager_dashboard_stats()
            
            # Key Metric Cards
            m1, m2, m3, m4 = st.columns(4)
            m1.metric("Total Disbursed", f"KES {stats['total_paid']:,.2f}")
            m2.metric("Bills Paid", stats['paid_count'])
            m3.metric("Pending Approval", f"KES {stats['total_pending']:,.2f}")
            m4.metric("Pending Count", stats['pending_count'])

            st.write("---")
            st.subheader("Expenditure by Category")
            category_data = get_bills_by_category()
            
            if category_data:
                st.bar_chart(
                    data=category_data, 
                    x="category", 
                    y="total", 
                    use_container_width=True
                )
            else:
                st.info("No payment data available yet to display category charts.")

    # M-Pesa Settings available to Managers
    c_key, c_secret, shortcode, initiator, sec_cred, env_mode = "", "", "", "", "", "sandbox"
    if role == "Manager":
        with st.sidebar.expander("🔑 Manager B2C Credentials", expanded=True):
            env_mode = st.radio("Environment", ["sandbox", "production"])
            c_key = st.text_input("Consumer Key", type="password", key="c_key").strip()
            c_secret = st.text_input("Consumer Secret", type="password", key="c_secret").strip()
            shortcode = st.text_input("Shortcode (Paybill/Till)", value="600000" if env_mode == "sandbox" else "").strip()
            initiator = st.text_input("Initiator Name", value="testapi" if env_mode == "sandbox" else "").strip()
            sec_cred = st.text_input("Security Credential", type="password", key="sec_cred").strip()

    st.title("FIT Scheduled Bill Payment System")

    # --- MANAGER APPROVAL DASHBOARD ---
    if role == "Manager":
        pending_bills = get_pending_bills()
        st.subheader("🛡️ Manager Approval Queue")

        if pending_bills:
            st.warning(
                f"🔔 **{len(pending_bills)} Request(s)** awaiting approval & payout execution."
            )
            for bill in pending_bills:
                b_id = bill["id"]
                p_payee = bill["payee_phone"]
                amt = bill["amount"]
                cat = bill["category"]
                ref = bill["bill_ref"]
                due = bill["due_date"]
                req_by = bill["requested_by"]
                req_uid = bill["user_id"]

                col_a, col_b, col_c = st.columns([3, 1, 1])
                with col_a:
                    st.info(
                        f"📌 **Bill #{ref}** | KES **{amt:,.2f}** | Due: **{due}**\n\n"
                        f"• **Recipient Phone:** `{p_payee}` | **Category:** `{cat}` | **Requested By:** `{req_by}`"
                    )
                with col_b:
                    if st.button(
                        f"💸 Approve & Disburse",
                        key=f"app_{b_id}",
                        type="primary",
                    ):
                        if not c_key or not c_secret or not sec_cred:
                            st.error("Enter all B2C credentials in sidebar first!")
                        else:
                            with st.spinner("Disbursing funds via B2C..."):
                                success, res = trigger_b2c_payout(
                                    p_payee,
                                    amt,
                                    ref,
                                    c_key,
                                    c_secret,
                                    initiator,
                                    sec_cred,
                                    shortcode,
                                    env=env_mode,
                                )

                            if success:
                                mark_bill_as_approved_and_paid(b_id, username)
                                today_str = date.today().strftime("%Y-%m-%d")
                                add_expense(
                                    req_uid,
                                    amt,
                                    cat,
                                    f"[B2C PAYOUT EXECUTED - {ref}] Sent to {p_payee} (Approved by {username})",
                                    today_str,
                                )
                                st.success(f"✅ KES {amt:,.2f} disbursed to `{p_payee}`!")
                                st.rerun()
                            else:
                                st.error(f"🚨 M-Pesa B2C Error: {res}")
                with col_c:
                    if st.button(f"❌ Reject", key=f"rej_{b_id}"):
                        reject_bill(b_id)
                        st.warning(f"Request #{ref} rejected.")
                        st.rerun()
            st.write("---")
        else:
            st.success("✅ Approval Queue is empty!")

    # --- MENU NAVIGATION ---
    menu_options = [
        "📅 Schedule / Request Bill Payment",
        "📋 My Scheduled Requests",
        "📊 All Settled Expenses",
        "📈 Analytics",
    ]
    menu = st.sidebar.radio("Navigation Menu", menu_options)

    # 1. Schedule/Request Bill Form
    if menu == "📅 Schedule / Request Bill Payment":
        st.subheader("📅 Schedule / Submit Bill Payment Request")
        st.caption(
            "Submit bill details. Once approved by a manager, funds will be disbursed via B2C to the payee."
        )

        with st.form("request_form"):
            col1, col2 = st.columns(2)
            with col1:
                payee_phone = st.text_input(
                    "Payee M-Pesa Phone (Recipient)",
                    placeholder="0712345678",
                )
                amount = st.number_input(
                    "Amount (KES)", min_value=1.0, step=10.0, format="%.2f"
                )
            with col2:
                category = st.selectbox(
                    "Expense Category",
                    [
                        "Rent & Utilities",
                        "Supplier Payment",
                        "Salaries",
                        "Internet & Subscriptions",
                        "Other",
                    ],
                )
                bill_ref = st.text_input(
                    "Bill Reference / Invoice No.", value="INV-2026-001"
                )
                due_date = st.date_input(
                    "Payment Due Date", min_value=date.today()
                ).strftime("%Y-%m-%d")

            submit = st.form_submit_button(
                "📌 Submit Payment Request", type="primary"
            )

        if submit:
            if not payee_phone:
                st.error("Please enter payee phone number.")
            else:
                schedule_bill(
                    user_id,
                    "0700000000",
                    payee_phone,
                    amount,
                    category,
                    bill_ref,
                    due_date,
                    username,
                )
                st.success(
                    f"✅ Request #{bill_ref} created! Status: **PENDING APPROVAL**."
                )

    # 2. View My Requests
    elif menu == "📋 My Scheduled Requests":
        st.subheader("📋 My Submitted Payment Requests")
        bills = get_user_scheduled_bills(user_id)

        if bills:
            df = pd.DataFrame(bills)
            st.dataframe(df, use_container_width=True)
        else:
            st.info("You have not submitted any bill payment requests yet.")

    # 3. View Settled Expenses Log
    elif menu == "📊 All Settled Expenses":
        st.subheader("📊 Settled Expense History")
        expenses = (
            get_expenses() if role == "Manager" else get_expenses(user_id)
        )

        if expenses:
            df = pd.DataFrame(expenses)
            st.dataframe(df, use_container_width=True)
            total = sum(float(e["amount"]) for e in expenses)
            st.metric("Total Executed Payouts", f"KES {total:,.2f}")
        else:
            st.info("No approved/settled expenses recorded yet.")

    # 4. Analytics
    elif menu == "📈 Analytics":
        st.subheader("📈 Expenditure Analytics")
        breakdown, total_all = get_category_breakdown()

        if breakdown:
            col1, col2 = st.columns([1, 1])
            with col1:
                st.metric("Total Organization Expenditure", f"KES {total_all:,.2f}")
                for row in breakdown:
                    cat = row["category"]
                    amt = float(row["total"])
                    percentage = (amt / total_all * 100) if total_all > 0 else 0
                    st.write(f"**{cat}:** KES {amt:,.2f} ({percentage:.1f}%)")

            with col2:
                categories = [r["category"] for r in breakdown]
                amounts = [float(r["total"]) for r in breakdown]

                fig, ax = plt.subplots(figsize=(6, 6))
                ax.pie(
                    amounts,
                    labels=categories,
                    autopct="%1.1f%%",
                    startangle=140,
                )
                st.pyplot(fig)
        else:
            st.info("No paid data available for analytics.")