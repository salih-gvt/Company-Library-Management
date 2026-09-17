import os
import sys
import shutil
import sqlite3
from pathlib import Path
import pandas as pd

# The database and its Excel mirror must live somewhere a standard,
# non-admin user can always write to. They cannot sit next to the
# installed program (e.g. under Program Files), which is read-only for
# normal users once installed.
DATA_DIR = Path(os.environ.get("LOCALAPPDATA", Path.home())) / "CompanyLibraryManagement"
DATA_DIR.mkdir(parents=True, exist_ok=True)

DATABASE_NAME = DATA_DIR / "library.db"
EXCEL_FILE = DATA_DIR / "LibraryBooks.xlsx"


def _legacy_install_dir() -> Path:
    """Folder the running program lives in - where older builds of this
    app kept library.db/LibraryBooks.xlsx alongside the executable."""
    if getattr(sys, "frozen", False):
        return Path(sys.executable).parent
    return Path(__file__).resolve().parent


def _migrate_legacy_data():
    """One-time migration on first run: if nothing exists yet in
    DATA_DIR and an older, pre-upgrade copy of the database/spreadsheet
    is sitting next to the executable, bring that data along instead of
    starting empty."""
    legacy_dir = _legacy_install_dir()

    legacy_db = legacy_dir / "library.db"
    if not DATABASE_NAME.exists() and legacy_db.exists():
        shutil.copy2(legacy_db, DATABASE_NAME)

    legacy_excel = legacy_dir / "LibraryBooks.xlsx"
    if not EXCEL_FILE.exists() and legacy_excel.exists():
        shutil.copy2(legacy_excel, EXCEL_FILE)


_migrate_legacy_data()


def get_connection():
    return sqlite3.connect(DATABASE_NAME)


def create_tables():

    connection = get_connection()
    cursor = connection.cursor()

    # Employees table
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS employees (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            employee_id TEXT UNIQUE NOT NULL,
            name TEXT NOT NULL,
            email TEXT NOT NULL,
            department TEXT
        )
    """)

    # Books table
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS books (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            book_id TEXT UNIQUE NOT NULL,
            title TEXT NOT NULL,
            author TEXT,
            category TEXT,
            available INTEGER DEFAULT 1,
            condition TEXT DEFAULT 'Good'
        )
    """)

    # Migration: add `condition` column for databases created before
    # this feature existed.
    cursor.execute("PRAGMA table_info(books)")
    existing_columns = [row[1] for row in cursor.fetchall()]

    if "condition" not in existing_columns:
        cursor.execute(
            "ALTER TABLE books ADD COLUMN condition TEXT DEFAULT 'Good'"
        )

    # Issued books table
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS issued_books (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            employee_id TEXT NOT NULL,
            employee_name TEXT NOT NULL,
            employee_email TEXT NOT NULL,
            book_id TEXT NOT NULL,
            book_title TEXT NOT NULL,
            issue_date TEXT NOT NULL,
            due_date TEXT NOT NULL,
            return_date TEXT,
            status TEXT DEFAULT 'Issued',
            reminder_sent INTEGER DEFAULT 0
        )
    """)

    # Waiting list table - lets an employee register interest in a
    # book that's currently issued to someone else.
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS waiting_list (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            book_id TEXT NOT NULL,
            book_title TEXT NOT NULL,
            employee_id TEXT NOT NULL,
            employee_name TEXT NOT NULL,
            employee_email TEXT NOT NULL,
            request_date TEXT NOT NULL,
            notified INTEGER DEFAULT 0
        )
    """)

    connection.commit()
    connection.close()


# =========================================================
# EXCEL → DATABASE
# =========================================================

def import_excel_to_database():

    excel_path = Path(EXCEL_FILE)

    if not excel_path.exists():
        print("LibraryBooks.xlsx not found")
        return

    try:
        employees = pd.read_excel(
            excel_path,
            sheet_name="Employees"
        ).fillna("")

        books = pd.read_excel(
            excel_path,
            sheet_name="Books"
        ).fillna("")

        issued = pd.read_excel(
            excel_path,
            sheet_name="IssuedBooks"
        ).fillna("")

    except Exception as e:
        print("Error reading Excel:", e)
        return

    connection = get_connection()
    cursor = connection.cursor()

    # =====================================================
    # EMPLOYEES
    # =====================================================

    for _, row in employees.iterrows():

        employee_id = str(row["EmployeeID"]).strip()

        if not employee_id:
            continue

        name = str(row["Name"]).strip()
        email = str(row["Email"]).strip()
        department = str(row["Department"]).strip()

        cursor.execute(
            "SELECT id FROM employees WHERE employee_id = ?",
            (employee_id,)
        )

        existing = cursor.fetchone()

        if existing:

            cursor.execute("""
                UPDATE employees
                SET name = ?,
                    email = ?,
                    department = ?
                WHERE employee_id = ?
            """, (
                name,
                email,
                department,
                employee_id
            ))

        else:

            cursor.execute("""
                INSERT INTO employees
                (employee_id, name, email, department)
                VALUES (?, ?, ?, ?)
            """, (
                employee_id,
                name,
                email,
                department
            ))

    # =====================================================
    # BOOKS
    # =====================================================

    for _, row in books.iterrows():

        book_id = str(row["BookID"]).strip()

        if not book_id:
            continue

        title = str(row["Title"]).strip()
        author = str(row["Author"]).strip()
        category = str(row["Category"]).strip()

        available_value = str(
            row["Available"]
        ).strip().lower()

        if available_value in (
            "0",
            "false",
            "no",
            "issued"
        ):
            available = 0
        else:
            available = 1

        cursor.execute(
            "SELECT id FROM books WHERE book_id = ?",
            (book_id,)
        )

        existing = cursor.fetchone()

        if existing:

            cursor.execute("""
                UPDATE books
                SET title = ?,
                    author = ?,
                    category = ?,
                    available = ?
                WHERE book_id = ?
            """, (
                title,
                author,
                category,
                available,
                book_id
            ))

        else:

            cursor.execute("""
                INSERT INTO books
                (book_id, title, author, category, available)
                VALUES (?, ?, ?, ?, ?)
            """, (
                book_id,
                title,
                author,
                category,
                available
            ))




                # =====================================================
    # ISSUED BOOKS
    # =====================================================

    for _, row in issued.iterrows():

        issue_id = row["IssueID"]

        if pd.isna(issue_id) or str(issue_id).strip() == "":
            continue

        issue_id = int(issue_id)

        employee_id = str(row["EmployeeID"]).strip()
        employee_name = str(row["EmployeeName"]).strip()
        employee_email = str(row["EmployeeEmail"]).strip()
        book_id = str(row["BookID"]).strip()
        book_title = str(row["BookTitle"]).strip()

        # Convert Excel dates to YYYY-MM-DD
        issue_date = pd.to_datetime(row["IssueDate"]).strftime("%Y-%m-%d")
        due_date = pd.to_datetime(row["DueDate"]).strftime("%Y-%m-%d")

        return_date = row["ReturnDate"]

        if pd.isna(return_date) or str(return_date).strip() == "":
            return_date = None
        else:
            return_date = pd.to_datetime(return_date).strftime("%Y-%m-%d")

        status = str(row["Status"]).strip()

        reminder_sent = str(
            row["ReminderSent"]
        ).strip().lower()

        reminder_sent = 1 if reminder_sent in (
            "1", "true", "yes"
        ) else 0

        cursor.execute(
            "SELECT id FROM issued_books WHERE id = ?",
            (issue_id,)
        )

        existing = cursor.fetchone()

        if existing:

            cursor.execute("""
                UPDATE issued_books
                SET employee_id = ?,
                    employee_name = ?,
                    employee_email = ?,
                    book_id = ?,
                    book_title = ?,
                    issue_date = ?,
                    due_date = ?,
                    return_date = ?,
                    status = ?,
                    reminder_sent = ?
                WHERE id = ?
            """, (
                employee_id,
                employee_name,
                employee_email,
                book_id,
                book_title,
                issue_date,
                due_date,
                return_date,
                status,
                reminder_sent,
                issue_id
            ))

        else:

            cursor.execute("""
                INSERT INTO issued_books
                (
                    id,
                    employee_id,
                    employee_name,
                    employee_email,
                    book_id,
                    book_title,
                    issue_date,
                    due_date,
                    return_date,
                    status,
                    reminder_sent
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                issue_id,
                employee_id,
                employee_name,
                employee_email,
                book_id,
                book_title,
                issue_date,
                due_date,
                return_date,
                status,
                reminder_sent
            ))

    # =====================================================
    # RECONCILE AVAILABILITY (self-healing)
    # =====================================================
    # A book's availability must always be derived from whether it
    # has an active, unreturned loan in issued_books - never trusted
    # separately from the Excel "Available" column, which can go
    # stale (e.g. if an app session started before a book's issue
    # was fully round-tripped back to Excel). This step corrects
    # any book whose stored `available` flag disagrees with reality.

    cursor.execute("""
        UPDATE books
        SET available = 0
        WHERE book_id IN (
            SELECT book_id FROM issued_books WHERE status = 'Issued'
        )
    """)

    cursor.execute("""
        UPDATE books
        SET available = 1
        WHERE book_id NOT IN (
            SELECT book_id FROM issued_books WHERE status = 'Issued'
        )
    """)

    connection.commit()
    connection.close()

    print("Excel data synchronized successfully.")


# =========================================================
# DATABASE → EXCEL
# =========================================================

def export_database_to_excel():
    """
    Write the current contents of the SQLite database back out to
    LibraryBooks.xlsx, so changes made in the app (Add/Edit employee
    or book) are reflected in the Excel file, not just the database.

    Raises on failure (e.g. the Excel file is currently open and
    locked) so the caller can decide how to surface that to the user.
    """

    connection = get_connection()

    employees_df = pd.read_sql_query(
        """
        SELECT
            employee_id AS EmployeeID,
            name AS Name,
            email AS Email,
            department AS Department
        FROM employees
        ORDER BY name
        """,
        connection
    )

    books_df = pd.read_sql_query(
        """
        SELECT
            book_id AS BookID,
            title AS Title,
            author AS Author,
            category AS Category,
            CASE WHEN available = 1 THEN 'Yes' ELSE 'No' END AS Available
        FROM books
        ORDER BY title
        """,
        connection
    )

    issued_df = pd.read_sql_query(
        """
        SELECT
            id AS IssueID,
            employee_id AS EmployeeID,
            employee_name AS EmployeeName,
            employee_email AS EmployeeEmail,
            book_id AS BookID,
            book_title AS BookTitle,
            issue_date AS IssueDate,
            due_date AS DueDate,
            return_date AS ReturnDate,
            status AS Status,
            reminder_sent AS ReminderSent
        FROM issued_books
        ORDER BY issue_date
        """,
        connection
    )

    connection.close()

    excel_path = Path(EXCEL_FILE)

    with pd.ExcelWriter(excel_path, engine="openpyxl", mode="w") as writer:
        employees_df.to_excel(writer, sheet_name="Employees", index=False)
        books_df.to_excel(writer, sheet_name="Books", index=False)
        issued_df.to_excel(writer, sheet_name="IssuedBooks", index=False)

    return str(excel_path.resolve())