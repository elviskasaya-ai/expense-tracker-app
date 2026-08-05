import sqlite3
from datetime import datetime
import matplotlib.pyplot as plt


class DatabaseManager:
    """Handles all interaction with the SQLite database."""

    def __init__(self, db_file="expenses.db"):
        self.db_file = db_file
        self.init_db()

    def _get_connection(self):
        return sqlite3.connect(self.db_file)

    def init_db(self):
        """Creates the expenses table if it does not exist."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS expenses (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    amount REAL NOT NULL,
                    category TEXT NOT NULL,
                    description TEXT,
                    date TEXT NOT NULL
                )
            ''')
            conn.commit()

    def add_expense(self, amount, category, description, date):
        """Inserts a new expense record."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('''
                INSERT INTO expenses (amount, category, description, date)
                VALUES (?, ?, ?, ?)
            ''', (amount, category, description, date))
            conn.commit()

    def get_expenses(self, category=None, month=None):
        """Fetches expenses, applying optional category and month filters."""
        query = "SELECT id, date, category, amount, description FROM expenses WHERE 1=1"
        params = []

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

    def get_category_breakdown(self):
        """Calculates category totals and overall spending grand total."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT category, SUM(amount) FROM expenses GROUP BY category")
            breakdown = cursor.fetchall()

            cursor.execute("SELECT SUM(amount) FROM expenses")
            total_result = cursor.fetchone()[0]
            total_all = total_result if total_result else 0.0

            return breakdown, total_all

    def delete_expense(self, expense_id):
        """Deletes a record matching the provided ID."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("DELETE FROM expenses WHERE id = ?", (expense_id,))
            conn.commit()
            return cursor.rowcount > 0


class ExpenseApp:
    """Manages the user interface, terminal menu, and visual outputs."""

    def __init__(self, db_manager):
        self.db = db_manager

    def add_expense(self):
        try:
            amount = float(input("Enter amount ($): "))
        except ValueError:
            print("Invalid amount. Please enter a number.")
            return

        category = input("Enter category (e.g., Food, Rent, Transport): ").title().strip()
        description = input("Enter description: ").strip()
        
        date_input = input("Enter date (YYYY-MM-DD) or press Enter for today: ").strip()
        if not date_input:
            date = datetime.now().strftime("%Y-%m-%d")
        else:
            try:
                datetime.strptime(date_input, "%Y-%m-%d")
                date = date_input
            except ValueError:
                print("Invalid date format. Using today's date instead.")
                date = datetime.now().strftime("%Y-%m-%d")

        self.db.add_expense(amount, category, description, date)
        print("Expense saved to database successfully!")

    def view_summary(self):
        filter_cat = input("\nEnter category to filter by (or press Enter for all): ").title().strip()
        month_filter = input("Enter month to filter by (YYYY-MM, or press Enter for all): ").strip()

        rows = self.db.get_expenses(filter_cat, month_filter)
        if not rows:
            print("\nNo matching expenses found.")
            return

        print("\n--- Expense List ---")
        total = 0.0
        for row in rows:
            exp_id, date, cat, amount, desc = row
            print(f"ID {exp_id} | {date} | {cat} - ${amount:.2f} ({desc})")
            total += amount

        print(f"\nFiltered Spending Total: ${total:.2f}")

    def view_category_breakdown(self):
        breakdown, total_all = self.db.get_category_breakdown()
        if not breakdown or total_all == 0:
            print("\nNo expenses recorded yet.")
            return

        print("\n--- Spending Breakdown by Category ---")
        for category, cat_total in breakdown:
            percentage = (cat_total / total_all) * 100
            print(f"- {category}: ${cat_total:.2f} ({percentage:.1f}%)")
        print(f"Grand Total: ${total_all:.2f}")

    def plot_expenses_pie_chart(self):
        breakdown, _ = self.db.get_category_breakdown()
        if not breakdown:
            print("\nNo expenses recorded yet to plot.")
            return

        categories = [row[0] for row in breakdown]
        amounts = [row[1] for row in breakdown]

        plt.figure(figsize=(7, 7))
        plt.pie(amounts, labels=categories, autopct='%1.1f%%', startangle=140)
        plt.title("Spending by Category")
        plt.tight_layout()
        print("\nOpening pie chart window...")
        plt.show()

    def delete_expense(self):
        rows = self.db.get_expenses()
        if not rows:
            print("\nNo expenses recorded to delete.")
            return

        print("\n--- All Expenses ---")
        for row in rows:
            print(f"ID {row[0]} | {row[1]} | {row[2]} - ${row[3]:.2f} ({row[4]})")

        try:
            target_id = int(input("\nEnter the ID of the expense to delete: "))
            if self.db.delete_expense(target_id):
                print(f"Expense with ID {target_id} deleted successfully!")
            else:
                print(f"No expense found with ID {target_id}.")
        except ValueError:
            print("Please enter a valid ID number.")

    def run(self):
        while True:
            print("\n=== Personal Finance Tracker (OOP + SQLite) ===")
            print("1. Add Expense")
            print("2. View Filtered Summary")
            print("3. View Category Breakdown")
            print("4. Plot Spending Pie Chart")
            print("5. Delete an Expense by ID")
            print("6. Quit")
            
            choice = input("Choose an option (1-6): ").strip()

            if choice == "1":
                self.add_expense()
            elif choice == "2":
                self.view_summary()
            elif choice == "3":
                self.view_category_breakdown()
            elif choice == "4":
                self.plot_expenses_pie_chart()
            elif choice == "5":
                self.delete_expense()
            elif choice == "6":
                print("Goodbye!")
                break
            else:
                print("Invalid choice. Please enter a number between 1 and 6.")


if __name__ == "__main__":
    db = DatabaseManager("expenses.db")
    app = ExpenseApp(db)
    app.run()