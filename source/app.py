import streamlit as st
import sqlite3
import json
import io
import zipfile
import shutil
import webview
import urllib.request
import urllib.error
from pathlib import Path
from datetime import date, timedelta, datetime
import pandas as pd

from database import (
    create_tables,
    get_connection,
    import_excel_to_database,
    export_database_to_excel,
    DATA_DIR,
    DATABASE_NAME
)
from version import APP_VERSION, GITHUB_REPO
import email_reminders


# =========================================================
# PAGE CONFIG
# =========================================================

st.set_page_config(
    page_title="Company Library Management",
    page_icon="📚",
    layout="wide",
    initial_sidebar_state="expanded"
)


# =========================================================
# THEME (Light / Dark toggle)
# =========================================================
# Streamlit's own theme.base setting only affects its native widgets,
# not the raw HTML/CSS this page uses for cards, KPIs etc. below - so
# the toggle drives its own pair of color palettes instead.

THEME_FILE = DATA_DIR / "theme.json"

_LIGHT_PALETTE = dict(
    bg="#f6f8fb",
    surface="#ffffff",
    surface_alt="#f8fafc",
    border="rgba(17, 24, 39, 0.10)",
    text="#111827",
    subtext="#6b7280",
    shadow="rgba(15, 23, 42, 0.06)",
    shadow_hover="rgba(15, 23, 42, 0.10)",
    scrollbar="rgba(17, 24, 39, 0.18)",
)

_DARK_PALETTE = dict(
    bg="#0b1220",
    surface="#151f32",
    surface_alt="#1b2740",
    border="rgba(255, 255, 255, 0.08)",
    text="#f1f5f9",
    subtext="#94a3b8",
    shadow="rgba(0, 0, 0, 0.35)",
    shadow_hover="rgba(0, 0, 0, 0.5)",
    scrollbar="rgba(255, 255, 255, 0.15)",
)

# Brand accent - deliberately identical in both themes so the app reads
# as one product regardless of mode (matches the sidebar's active-nav
# blue and the KPI "issued" accent already used throughout).
_ACCENT = "#2563eb"
_ACCENT_HOVER = "#1d4ed8"

_THEME_MODES = ["Light", "Dark"]


def _load_theme_mode():
    try:
        saved = json.loads(THEME_FILE.read_text()).get("mode")
        if saved in _THEME_MODES:
            return saved
    except Exception:
        pass
    return "Light"


def _save_theme_mode(mode):
    try:
        THEME_FILE.write_text(json.dumps({"mode": mode}))
    except Exception:
        pass


def _theme_css(p):
    return f"""
    .stApp {{ background: {p['bg']}; }}

    .card, .kpi {{
        background: {p['surface']};
        border-color: {p['border']};
        box-shadow: 0 1px 2px {p['shadow']}, 0 8px 24px -12px {p['shadow']};
    }}

    .card:hover {{
        box-shadow: 0 1px 2px {p['shadow']}, 0 12px 28px -12px {p['shadow_hover']};
    }}

    .kpi:hover {{
        box-shadow: 0 4px 10px {p['shadow']}, 0 16px 32px -14px {p['shadow_hover']};
    }}

    .page-title, .card-title, .kpi-value {{ color: {p['text']}; }}

    .page-subtitle, .card-subtitle, .kpi-label, .kpi-small {{
        color: {p['subtext']};
    }}

    hr {{ border-top-color: {p['border']}; }}

    .stTextInput input,
    .stNumberInput input,
    .stDateInput input,
    .stSelectbox div[data-baseweb="select"] > div,
    .stMultiSelect div[data-baseweb="select"] > div {{
        background-color: {p['surface']} !important;
        color: {p['text']} !important;
        border-color: {p['border']} !important;
    }}

    [data-testid="stDataFrame"] {{
        border: 1px solid {p['border']};
        box-shadow: 0 1px 2px {p['shadow']};
    }}

    div[data-testid="stAlert"] {{
        background: {p['surface_alt']};
        border: 1px solid {p['border']};
    }}

    ::-webkit-scrollbar-thumb {{
        background: {p['scrollbar']};
    }}

    .st-key-theme_toggle label[data-testid="stWidgetLabel"] p {{
        color: {p['subtext']};
    }}
    """


if "theme_mode" not in st.session_state:
    st.session_state.theme_mode = _load_theme_mode()

_active_mode = st.session_state.theme_mode

_theme_style = _theme_css(
    _DARK_PALETTE if _active_mode == "Dark" else _LIGHT_PALETTE
)


# =========================================================
# PROFESSIONAL CSS
# =========================================================

st.markdown("""
<style>

/* ---------- FONT ---------- */

html, body, [class*="css"] {
    font-family: 'Inter', -apple-system, BlinkMacSystemFont,
                 'Segoe UI', Roboto, Helvetica, Arial, sans-serif;
}


/* ---------- MAIN PAGE ---------- */

.stApp {
    background: #f6f8fb;
    transition: background-color 0.2s ease;
}

.block-container {
    padding-top: 3rem;
    padding-bottom: 2rem;
    max-width: 1400px;
}

/* Streamlit's fixed top toolbar (Deploy button etc.) sits above the
   content; make sure it doesn't visually collide with our page title. */
header[data-testid="stHeader"] {
    background: transparent;
}


/* ---------- SCROLLBAR ---------- */

::-webkit-scrollbar {
    width: 10px;
    height: 10px;
}

::-webkit-scrollbar-track {
    background: transparent;
}

::-webkit-scrollbar-thumb {
    background: rgba(17, 24, 39, 0.18);
    border-radius: 8px;
}


/* ---------- SIDEBAR ---------- */

section[data-testid="stSidebar"] {
    background: #111827;
}

section[data-testid="stSidebar"] * {
    color: #f9fafb;
}

.sidebar-brand {
    padding: 14px 5px 22px 5px;
}

.sidebar-brand-title {
    font-size: 22px;
    font-weight: 800;
    letter-spacing: -0.01em;
}

.sidebar-brand-subtitle {
    font-size: 12px;
    color: #9ca3af !important;
    margin-top: 4px;
    letter-spacing: 0.01em;
}


/* ---------- SIDEBAR NAVIGATION (button-based) ---------- */

/* We use st.button (not st.radio) for nav items so we have full
   control over the look — no native radio circle to fight with. */

section[data-testid="stSidebar"] div[data-testid="stVerticalBlock"] div[data-testid="stButton"] {
    margin-bottom: 2px;
}

section[data-testid="stSidebar"] .stButton > button {
    width: 100%;
    display: flex;
    text-align: left;
    justify-content: flex-start;
    background: transparent;
    border: none;
    color: #d1d5db !important;
    font-weight: 500;
    padding: 10px 14px;
    border-radius: 10px;
    min-height: 0;
    box-shadow: none;
    transition: background-color 0.15s ease, transform 0.1s ease;
}

/* Streamlit wraps the button's label in its own inner container,
   which some versions center independently of the button's own
   flex/text-align settings above - force it back to the left. */
section[data-testid="stSidebar"] .stButton > button > div,
section[data-testid="stSidebar"] .stButton > button p {
    width: 100%;
    text-align: left !important;
    justify-content: flex-start !important;
}

section[data-testid="stSidebar"] .stButton > button:hover {
    background: #1f2937;
    color: #ffffff !important;
    border: none;
}

section[data-testid="stSidebar"] .stButton > button:active {
    transform: scale(0.98);
}

section[data-testid="stSidebar"] .stButton > button:focus:not(:active) {
    background: #1f2937;
    color: #ffffff !important;
    box-shadow: none;
}

/* Active page — Streamlit renders the primary button with a literal
   kind="primary" attribute on the <button> element itself. */
section[data-testid="stSidebar"] .stButton > button[kind="primary"] {
    background: #2563eb !important;
    color: #ffffff !important;
    font-weight: 600;
    border: none;
    box-shadow: 0 4px 12px rgba(37, 99, 235, 0.35);
}

section[data-testid="stSidebar"] .stButton > button[kind="primary"]:hover,
section[data-testid="stSidebar"] .stButton > button[kind="primary"]:focus {
    background: #2563eb !important;
    color: #ffffff !important;
}


/* ---------- PAGE HEADER ---------- */

.page-title {
    font-size: 30px;
    font-weight: 800;
    letter-spacing: -0.015em;
    color: #111827;
    margin-bottom: 3px;
}

.page-subtitle {
    color: #6b7280;
    font-size: 14px;
    margin-bottom: 25px;
}


/* ---------- CARDS ---------- */

.card {
    background: white;
    border: 1px solid #e5e7eb;
    border-radius: 16px;
    padding: 24px;
    margin-bottom: 20px;
    box-shadow: 0 1px 2px rgba(15,23,42,0.04), 0 8px 24px -12px rgba(15,23,42,0.08);
    transition: box-shadow 0.2s ease, background-color 0.2s ease, border-color 0.2s ease;
}

.card-title {
    font-size: 18px;
    font-weight: 700;
    color: #111827;
    margin-bottom: 4px;
}

.card-subtitle {
    color: #6b7280;
    font-size: 13px;
    margin-bottom: 18px;
}


/* ---------- KPI CARDS ---------- */
/* A colored top accent bar (rather than a left border) carries the
   semantic color - a cleaner, more modern dashboard-card look. Plain
   KPI cards (no semantic class) default to the brand accent. */

.kpi {
    position: relative;
    background: white;
    border: 1px solid #e5e7eb;
    border-radius: 18px;
    padding: 20px 20px 18px 20px;
    min-height: 125px;
    overflow: hidden;
    box-shadow: 0 1px 2px rgba(15,23,42,0.04), 0 8px 24px -12px rgba(15,23,42,0.08);
    transition: box-shadow 0.2s ease, transform 0.15s ease, background-color 0.2s ease, border-color 0.2s ease;
}

.kpi::before {
    content: "";
    position: absolute;
    top: 0;
    left: 0;
    right: 0;
    height: 4px;
    background: #2563eb;
}

.kpi:hover {
    box-shadow: 0 4px 10px rgba(15,23,42,0.06), 0 16px 32px -14px rgba(15,23,42,0.12);
    transform: translateY(-2px);
}

.kpi-overdue::before { background: #dc2626; }
.kpi-due-today::before { background: #d97706; }
.kpi-available::before { background: #059669; }
.kpi-issued::before { background: #2563eb; }

.kpi-label {
    color: #6b7280;
    font-size: 12px;
    font-weight: 600;
    letter-spacing: 0.06em;
    text-transform: uppercase;
}

.kpi-value {
    color: #111827;
    font-size: 32px;
    font-weight: 800;
    letter-spacing: -0.01em;
    margin-top: 8px;
}

.kpi-small {
    color: #6b7280;
    font-size: 12px;
    margin-top: 3px;
}


/* ---------- STATUS ---------- */

.status-available {
    color: #047857;
    font-weight: 600;
}

.status-issued {
    color: #dc2626;
    font-weight: 600;
}


/* ---------- BUTTONS ---------- */
/* Almost every button in the main content area is a primary action
   (Save, Issue, Return, Reserve, Export...) - a solid brand-accent
   fill reads as more modern and confident than the flat gray default,
   and keeps buttons visually consistent with the sidebar's active-nav
   blue and the "Issued" KPI accent. Sidebar buttons keep their own,
   more specific styling above and are unaffected. */

.stButton > button {
    border-radius: 10px;
    font-weight: 600;
    min-height: 42px;
    transition: filter 0.15s ease, box-shadow 0.15s ease, transform 0.1s ease;
}

div[data-testid="stMainBlockContainer"] .stButton > button {
    background-color: #2563eb;
    color: #ffffff;
    border: 1px solid #2563eb;
    box-shadow: 0 2px 6px rgba(37, 99, 235, 0.25);
}

div[data-testid="stMainBlockContainer"] .stButton > button:hover {
    filter: brightness(1.08);
    box-shadow: 0 4px 12px rgba(37, 99, 235, 0.32);
}

div[data-testid="stMainBlockContainer"] .stButton > button:active {
    transform: scale(0.98);
}

div[data-testid="stMainBlockContainer"] .stButton > button:disabled {
    background-color: #9ca3af;
    border-color: #9ca3af;
    color: #f3f4f6;
    box-shadow: none;
}

div[data-testid="stMainBlockContainer"] .stDownloadButton > button {
    background-color: #2563eb;
    color: #ffffff;
    border: 1px solid #2563eb;
}


/* ---------- INPUTS ---------- */

/* Hide the "Press Enter to submit form" hint Streamlit shows under
   every text input inside a form - it's just visual clutter here
   since the Save/submit button is always right there. */
[data-testid="InputInstructions"] {
    display: none;
}

.stTextInput input,
.stNumberInput input,
.stSelectbox div[data-baseweb="select"],
.stDateInput input {
    border-radius: 10px;
    transition: border-color 0.15s ease, box-shadow 0.15s ease;
}

.stTextInput input:focus,
.stNumberInput input:focus,
.stDateInput input:focus,
.stSelectbox div[data-baseweb="select"]:focus-within {
    border-color: #2563eb !important;
    box-shadow: 0 0 0 3px rgba(37, 99, 235, 0.15) !important;
}


/* ---------- TABLE ---------- */

[data-testid="stDataFrame"] {
    border-radius: 12px;
    overflow: hidden;
}


/* ---------- ALERT ---------- */

div[data-testid="stAlert"] {
    border-radius: 12px;
}


/* ---------- HORIZONTAL LINE ---------- */

hr {
    border: none;
    border-top: 1px solid #e5e7eb;
    margin: 25px 0;
}

</style>
""", unsafe_allow_html=True)

# Rendered after the stylesheet above so its rules win the cascade
# (same selectors, same specificity - later wins) for whichever theme
# is active.
st.markdown(f"<style>{_theme_style}</style>", unsafe_allow_html=True)


# =========================================================
# THEME TOGGLE (floating, top-right)
# =========================================================

st.markdown("""
<style>
.st-key-theme_toggle {
    margin-bottom: -8px;
}

/* Right-align the single toggle switch within the content area,
   in normal page flow (Streamlit's own layout containers don't
   support alignment props directly, so this is done via CSS). */
.st-key-theme_toggle div[data-testid="stVerticalBlock"] {
    display: flex;
    align-items: center;
}

.st-key-theme_toggle div[data-testid="stElementContainer"] {
    margin-left: auto;
}

.st-key-theme_toggle label[data-testid="stWidgetLabel"] p {
    font-size: 13px;
}
</style>
""", unsafe_allow_html=True)

with st.container(key="theme_toggle"):
    _is_dark_mode = st.toggle(
        "🌙 Dark mode",
        value=(st.session_state.theme_mode == "Dark"),
        key="dark_mode_toggle",
    )

    _new_mode = "Dark" if _is_dark_mode else "Light"

    if _new_mode != st.session_state.theme_mode:
        st.session_state.theme_mode = _new_mode
        _save_theme_mode(_new_mode)
        st.rerun()


# =========================================================
# UPDATE CHECK
# =========================================================
# Checks GitHub's "latest release" once per session (not on every
# rerun) and shows a small notice if a newer version exists. Entirely
# best-effort: any failure (offline, GitHub unreachable, unexpected
# response) is swallowed silently so it can never block using the app.
# Never auto-downloads or auto-installs anything - just links to the
# release for the user to get themselves.

def _parse_version(version_string):
    digits_only = version_string.strip().lstrip("vV")
    parts = []

    for piece in digits_only.split("."):
        number = "".join(ch for ch in piece if ch.isdigit())
        parts.append(int(number) if number else 0)

    return tuple(parts)


def check_for_update():
    try:
        request = urllib.request.Request(
            f"https://api.github.com/repos/{GITHUB_REPO}/releases/latest",
            headers={
                "Accept": "application/vnd.github+json",
                "User-Agent": "CompanyLibraryManagement",
            },
        )

        with urllib.request.urlopen(request, timeout=4) as response:
            payload = json.loads(response.read().decode("utf-8"))

        latest_tag = payload.get("tag_name", "")
        release_url = payload.get(
            "html_url",
            f"https://github.com/{GITHUB_REPO}/releases/latest"
        )

        if latest_tag and _parse_version(latest_tag) > _parse_version(APP_VERSION):
            return {
                "version": latest_tag.lstrip("vV"),
                "url": release_url,
            }

    except Exception:
        pass  # offline, rate-limited, no releases yet, etc. - not an error

    return None


if "update_check_done" not in st.session_state:
    st.session_state.update_check_done = True
    st.session_state.update_info = check_for_update()

if st.session_state.get("update_info"):
    _update = st.session_state.update_info
    st.info(
        f"⬆️ **Update available: v{_update['version']}** "
        f"(you're on v{APP_VERSION}) — [see what's new]({_update['url']})",
        icon="⬆️"
    )


# =========================================================
# DATABASE INITIALIZATION
# =========================================================

create_tables()

# IMPORTANT: only import from Excel once per session (first load), not
# on every rerun. Streamlit reruns this whole script on every click, and
# re-importing every time meant any in-app change (issuing a book,
# deleting a row, etc.) could get silently overwritten back to whatever
# was last successfully written to Excel — which is exactly what caused
# statuses/deletions to "revert" after further clicks.
if "excel_imported" not in st.session_state:

    try:
        import_excel_to_database()

        # The import step also self-heals book availability (derived
        # from IssuedBooks, not the Excel Available column). Push that
        # corrected state back out to Excel immediately, otherwise the
        # fix only ever lives in the database and the spreadsheet keeps
        # showing the old, stale Available/Issued values.
        export_database_to_excel()

    except Exception as e:
        st.warning(f"Excel synchronization warning: {e}")

    st.session_state.excel_imported = True


# Version counters, bumped by every add/edit/delete/issue/return so
# other parts of the app can tell books/employees data just changed.
if "books_version" not in st.session_state:
    st.session_state.books_version = 0

if "employees_version" not in st.session_state:
    st.session_state.employees_version = 0


# Reminder emails: checked once per session (not on every rerun/click),
# same reasoning as the Excel import above. A no-op if the feature
# isn't enabled/configured yet (see email_reminders.check_and_send_reminders).
if "reminders_checked" not in st.session_state:

    try:
        _reminder_result = email_reminders.check_and_send_reminders()

        if _reminder_result["sent"] > 0:
            st.toast(
                f"📧 Sent {_reminder_result['sent']} reminder email(s).",
                icon="📧"
            )

        if _reminder_result["errors"]:
            st.warning(
                "Some reminder emails could not be sent: "
                + "; ".join(_reminder_result["errors"][:3])
            )

    except Exception:
        pass  # reminder emails are best-effort, never block the app

    st.session_state.reminders_checked = True


# =========================================================
# HELPER FUNCTIONS
# =========================================================

def get_all_members():

    connection = get_connection()
    cursor = connection.cursor()

    cursor.execute("""
        SELECT
            employee_id,
            name,
            email,
            department
        FROM employees
        ORDER BY name
    """)

    data = cursor.fetchall()
    connection.close()

    return data


def get_all_books():

    connection = get_connection()
    cursor = connection.cursor()

    cursor.execute("""
        SELECT
            book_id,
            title,
            author,
            category,
            available,
            condition
        FROM books
        ORDER BY title
    """)

    data = cursor.fetchall()
    connection.close()

    return data


def get_currently_issued_books():

    connection = get_connection()
    cursor = connection.cursor()

    cursor.execute("""
        SELECT
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
        FROM issued_books
        WHERE status = 'Issued'
        ORDER BY due_date
    """)

    data = cursor.fetchall()
    connection.close()

    return data


def get_waiting_list(book_id=None):

    connection = get_connection()
    cursor = connection.cursor()

    if book_id:

        cursor.execute("""
            SELECT id, book_id, book_title, employee_id, employee_name,
                   employee_email, request_date, notified
            FROM waiting_list
            WHERE book_id = ?
            ORDER BY request_date
        """, (book_id,))

    else:

        cursor.execute("""
            SELECT id, book_id, book_title, employee_id, employee_name,
                   employee_email, request_date, notified
            FROM waiting_list
            ORDER BY request_date
        """)

    data = cursor.fetchall()
    connection.close()

    return data


def add_to_waiting_list(
    book_id,
    book_title,
    employee_id,
    employee_name,
    employee_email
):

    connection = get_connection()
    cursor = connection.cursor()

    # Don't let the same employee queue twice for the same book.
    cursor.execute("""
        SELECT id FROM waiting_list
        WHERE book_id = ? AND employee_id = ?
    """, (book_id, employee_id))

    if cursor.fetchone():
        connection.close()
        raise ValueError(
            "This employee is already on the waiting list for this book."
        )

    cursor.execute("""
        INSERT INTO waiting_list
        (book_id, book_title, employee_id, employee_name, employee_email, request_date)
        VALUES (?, ?, ?, ?, ?, ?)
    """, (
        book_id,
        book_title,
        employee_id,
        employee_name,
        employee_email,
        date.today().isoformat()
    ))

    connection.commit()
    connection.close()


def remove_from_waiting_list(entry_id):

    connection = get_connection()
    cursor = connection.cursor()

    cursor.execute(
        "DELETE FROM waiting_list WHERE id = ?",
        (entry_id,)
    )

    connection.commit()
    connection.close()


def add_employee(
    employee_id,
    employee_name,
    employee_email,
    department
):

    connection = get_connection()
    cursor = connection.cursor()

    cursor.execute("""
        INSERT INTO employees
        (
            employee_id,
            name,
            email,
            department
        )
        VALUES (?, ?, ?, ?)
    """, (
        employee_id,
        employee_name,
        employee_email,
        department
    ))

    connection.commit()
    connection.close()

    st.session_state.employees_version += 1

    try:
        excel_path = export_database_to_excel()
        st.toast(f"Synced to Excel: {excel_path}", icon="✅")
    except Exception as e:
        st.warning(f"Employee saved, but couldn't sync to Excel: {e}")


def add_book(
    book_id,
    title,
    author,
    category,
    available=1
):

    connection = get_connection()
    cursor = connection.cursor()

    cursor.execute("""
        INSERT INTO books
        (
            book_id,
            title,
            author,
            category,
            available
        )
        VALUES (?, ?, ?, ?, ?)
    """, (
        book_id,
        title,
        author,
        category,
        available
    ))

    connection.commit()
    connection.close()

    st.session_state.books_version += 1

    try:
        excel_path = export_database_to_excel()
        st.toast(f"Synced to Excel: {excel_path}", icon="✅")
    except Exception as e:
        st.warning(f"Book saved, but couldn't sync to Excel: {e}")


def update_employee(
    original_employee_id,
    employee_id,
    employee_name,
    employee_email,
    department
):

    connection = get_connection()
    cursor = connection.cursor()

    cursor.execute("""
        UPDATE employees
        SET
            employee_id = ?,
            name = ?,
            email = ?,
            department = ?
        WHERE employee_id = ?
    """, (
        employee_id,
        employee_name,
        employee_email,
        department,
        original_employee_id
    ))

# Update email in existing issue records also
    cursor.execute("""
       UPDATE issued_books
       SET
        employee_id = ?,
        employee_name = ?,
        employee_email = ?
       WHERE employee_id = ?
    """, (
       employee_id,
       employee_name,
       employee_email,
       original_employee_id
))
    connection.commit()
    connection.close()

    st.session_state.employees_version += 1

    try:
        excel_path = export_database_to_excel()
        st.toast(f"Synced to Excel: {excel_path}", icon="✅")
    except Exception as e:
        st.warning(f"Employee updated, but couldn't sync to Excel: {e}")


def update_book(
    original_book_id,
    book_id,
    title,
    author,
    category
):

    connection = get_connection()
    cursor = connection.cursor()

    cursor.execute("""
        UPDATE books
        SET
            book_id = ?,
            title = ?,
            author = ?,
            category = ?
        WHERE book_id = ?
    """, (
        book_id,
        title,
        author,
        category,
        original_book_id
    ))

    connection.commit()
    connection.close()

    st.session_state.books_version += 1

    try:
        excel_path = export_database_to_excel()
        st.toast(f"Synced to Excel: {excel_path}", icon="✅")
    except Exception as e:
        st.warning(f"Book updated, but couldn't sync to Excel: {e}")


def delete_employee(employee_id):
    """
    Delete an employee. Blocked if they currently have any book
    issued to them (status = 'Issued') so we never lose track of
    an outstanding loan.
    """

    connection = get_connection()
    cursor = connection.cursor()

    cursor.execute(
        "SELECT COUNT(*) FROM issued_books "
        "WHERE employee_id = ? AND status = 'Issued'",
        (employee_id,)
    )

    outstanding = cursor.fetchone()[0]

    if outstanding > 0:
        connection.close()
        raise ValueError(
            f"Cannot delete: this employee still has {outstanding} "
            "book(s) issued. Return them first."
        )

    cursor.execute(
        "DELETE FROM employees WHERE employee_id = ?",
        (employee_id,)
    )

    connection.commit()
    connection.close()

    st.session_state.employees_version += 1

    try:
        excel_path = export_database_to_excel()
        st.toast(f"Synced to Excel: {excel_path}", icon="✅")
    except Exception as e:
        st.warning(f"Employee deleted, but couldn't sync to Excel: {e}")


def delete_book(book_id):
    """
    Delete a book. Blocked if it's currently issued (available = 0)
    so we never delete a book that's still out with an employee.
    """

    connection = get_connection()
    cursor = connection.cursor()

    cursor.execute(
        "SELECT available FROM books WHERE book_id = ?",
        (book_id,)
    )

    row = cursor.fetchone()

    if row is not None and row[0] == 0:
        connection.close()
        raise ValueError(
            "Cannot delete: this book is currently issued. "
            "Return it first."
        )

    cursor.execute(
        "DELETE FROM books WHERE book_id = ?",
        (book_id,)
    )

    connection.commit()
    connection.close()

    st.session_state.books_version += 1

    try:
        excel_path = export_database_to_excel()
        st.toast(f"Synced to Excel: {excel_path}", icon="✅")
    except Exception as e:
        st.warning(f"Book deleted, but couldn't sync to Excel: {e}")


# =========================================================
# EDIT / DELETE DIALOGS (Members & Books)
# =========================================================

@st.dialog("Edit Employee")
def edit_employee_dialog(original_employee_id, name, email, department):

    new_employee_id = st.text_input("Employee ID", value=original_employee_id)
    new_name = st.text_input("Employee Name", value=name)
    new_email = st.text_input("Email", value=email)
    new_department = st.text_input("Department", value=department or "")

    col1, col2 = st.columns(2)

    with col1:
        if st.button("Cancel", use_container_width=True, key="cancel_edit_employee"):
            st.rerun()

    with col2:
        if st.button(
            "💾 Save Changes",
            type="primary",
            use_container_width=True,
            key="save_edit_employee"
        ):
            if not new_employee_id.strip() or not new_name.strip() or not new_email.strip():
                st.error("Employee ID, Name and Email cannot be empty.")
            else:
                try:
                    update_employee(
                        original_employee_id,
                        new_employee_id.strip(),
                        new_name.strip(),
                        new_email.strip(),
                        new_department.strip()
                    )
                    st.success("Employee updated successfully.")
                    st.rerun()
                except sqlite3.IntegrityError:
                    st.error(f"Employee ID '{new_employee_id}' is already used by another employee.")
                except Exception as e:
                    st.error(f"Error: {e}")


@st.dialog("Delete Employee")
def delete_employee_dialog(employee_id, name):

    st.warning(
        f"Delete employee **{name}** ({employee_id})? This cannot be undone."
    )

    col1, col2 = st.columns(2)

    with col1:
        if st.button("Cancel", use_container_width=True, key="cancel_delete_employee"):
            st.rerun()

    with col2:
        if st.button(
            "🗑️ Delete",
            type="primary",
            use_container_width=True,
            key="confirm_delete_employee"
        ):
            try:
                delete_employee(employee_id)
                st.success("Employee deleted successfully.")
                st.rerun()
            except ValueError as e:
                st.error(str(e))
            except Exception as e:
                st.error(f"Error: {e}")


@st.dialog("Edit Book")
def edit_book_dialog(original_book_id, title, author, category):

    new_book_id = st.text_input("Book ID", value=original_book_id)
    new_title = st.text_input("Book Title", value=title)
    new_author = st.text_input("Author", value=author or "")
    new_category = st.text_input("Category", value=category or "")

    col1, col2 = st.columns(2)

    with col1:
        if st.button("Cancel", use_container_width=True, key="cancel_edit_book"):
            st.rerun()

    with col2:
        if st.button(
            "💾 Save Changes",
            type="primary",
            use_container_width=True,
            key="save_edit_book"
        ):
            if not new_book_id.strip() or not new_title.strip():
                st.error("Book ID and Title cannot be empty.")
            else:
                try:
                    update_book(
                        original_book_id,
                        new_book_id.strip(),
                        new_title.strip(),
                        new_author.strip(),
                        new_category.strip()
                    )
                    st.success("Book updated successfully.")
                    st.rerun()
                except sqlite3.IntegrityError:
                    st.error(f"Book ID '{new_book_id}' is already used by another book.")
                except Exception as e:
                    st.error(f"Error: {e}")


@st.dialog("Delete Book")
def delete_book_dialog(book_id, title):

    st.warning(
        f"Delete book **{title}** ({book_id})? This cannot be undone."
    )

    col1, col2 = st.columns(2)

    with col1:
        if st.button("Cancel", use_container_width=True, key="cancel_delete_book"):
            st.rerun()

    with col2:
        if st.button(
            "🗑️ Delete",
            type="primary",
            use_container_width=True,
            key="confirm_delete_book"
        ):
            try:
                delete_book(book_id)
                st.success("Book deleted successfully.")
                st.rerun()
            except ValueError as e:
                st.error(str(e))
            except Exception as e:
                st.error(f"Error: {e}")


def get_all_issue_records():

    connection = get_connection()
    cursor = connection.cursor()

    cursor.execute("""
        SELECT
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
        FROM issued_books
        ORDER BY issue_date DESC, id DESC
    """)

    data = cursor.fetchall()
    connection.close()

    return data


def get_reservation_list():
    return get_waiting_list()


# =========================================================
# BACKUP / RESTORE
# =========================================================
# The backup file is a plain .zip containing:
#   manifest.json - format version + metadata, so future app versions
#                   can tell whether/how to read older backups
#   data.json     - every table's rows, as plain column-name -> value
#                   dicts (not a raw copy of library.db) so a restore
#                   isn't tied to today's exact schema/SQLite version.

BACKUP_FORMAT_VERSION = 1
BACKUP_TABLES = ["employees", "books", "issued_books", "waiting_list"]


def _get_webview_window():
    """The pywebview window this app is running in, or None if it's
    being run directly in a browser (e.g. during development) - used to
    show native Save/Open file dialogs instead of browser downloads."""

    try:
        if webview.windows:
            return webview.windows[0]
    except Exception:
        pass

    return None


def build_backup_bytes():
    """Dump every table into a versioned backup .zip, returned as bytes."""

    connection = get_connection()
    cursor = connection.cursor()

    data = {}

    for table in BACKUP_TABLES:

        cursor.execute(f"SELECT * FROM {table}")
        columns = [description[0] for description in cursor.description]
        data[table] = [dict(zip(columns, row)) for row in cursor.fetchall()]

    connection.close()

    manifest = {
        "app": "Company Library Management",
        "backup_format_version": BACKUP_FORMAT_VERSION,
        "created_at": datetime.now().isoformat(timespec="seconds"),
        "tables": BACKUP_TABLES,
    }

    buffer = io.BytesIO()

    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as zip_file:
        zip_file.writestr("manifest.json", json.dumps(manifest, indent=2))
        zip_file.writestr("data.json", json.dumps(data, indent=2, default=str))

    return buffer.getvalue()


def validate_backup_bytes(raw_bytes):
    """Check a backup file is actually ours and readable before touching
    the database. Returns (True, {"manifest":..., "data":..., "summary":...})
    on success, or (False, "human-readable reason") on failure."""

    try:
        with zipfile.ZipFile(io.BytesIO(raw_bytes)) as zip_file:
            names = zip_file.namelist()

            if "manifest.json" not in names or "data.json" not in names:
                return False, (
                    "This doesn't look like a Company Library backup file "
                    "(required files are missing)."
                )

            manifest = json.loads(zip_file.read("manifest.json"))
            data = json.loads(zip_file.read("data.json"))

    except zipfile.BadZipFile:
        return False, (
            "This file isn't a valid backup archive - it may be corrupted "
            "or not a backup file at all."
        )

    except json.JSONDecodeError:
        return False, "The backup file's data is corrupted and can't be read."

    except Exception as e:
        return False, f"Could not read the backup file: {e}"

    if not isinstance(manifest, dict) or manifest.get("app") != "Company Library Management":
        return False, "This backup file was not created by Company Library Management."

    backup_version = manifest.get("backup_format_version")

    if not isinstance(backup_version, int) or backup_version < 1:
        return False, "The backup file's version information is missing or invalid."

    if backup_version > BACKUP_FORMAT_VERSION:
        return False, (
            "This backup was created by a newer version of the app and "
            "can't be restored here. Please update the application first."
        )

    if not isinstance(data, dict) or not data:
        return False, "The backup file's data is in an unexpected format."

    summary = {}

    for table, rows in data.items():

        if table not in BACKUP_TABLES or not isinstance(rows, list):
            return False, f"The backup file's '{table}' data is in an unexpected format."

        summary[table] = len(rows)

    return True, {"manifest": manifest, "data": data, "summary": summary}


def restore_from_backup(data):
    """Replace all current data with the given backup data. A timestamped
    safety copy of the current database is kept first, in case of
    mistakes - restoring is otherwise irreversible."""

    try:
        safety_dir = DATA_DIR / "restore_safety_backups"
        safety_dir.mkdir(parents=True, exist_ok=True)

        safety_name = f"pre_restore_{datetime.now():%Y%m%d_%H%M%S}.db"
        shutil.copy2(DATABASE_NAME, safety_dir / safety_name)

    except Exception:
        pass  # best-effort safety net - must not block the restore itself

    connection = get_connection()
    cursor = connection.cursor()

    try:
        for table in BACKUP_TABLES:

            rows = data.get(table)

            if not isinstance(rows, list):
                continue

            cursor.execute(f"PRAGMA table_info({table})")
            live_columns = [row[1] for row in cursor.fetchall()]

            cursor.execute(f"DELETE FROM {table}")

            for row in rows:

                if not isinstance(row, dict):
                    continue

                # Only columns that exist in both the backup row and the
                # live table are used - this keeps restoring an older or
                # newer backup from crashing on schema drift.
                use_columns = [c for c in live_columns if c in row]

                if not use_columns:
                    continue

                column_list = ", ".join(use_columns)
                placeholders = ", ".join(["?"] * len(use_columns))
                values = [row[c] for c in use_columns]

                cursor.execute(
                    f"INSERT INTO {table} ({column_list}) VALUES ({placeholders})",
                    values
                )

        connection.commit()

    except Exception:
        connection.rollback()
        connection.close()
        raise

    connection.close()

    try:
        export_database_to_excel()
    except Exception:
        pass  # restore itself already succeeded; Excel sync is secondary

    st.session_state.books_version = st.session_state.get("books_version", 0) + 1
    st.session_state.employees_version = st.session_state.get("employees_version", 0) + 1


@st.dialog("Confirm Restore")
def confirm_restore_dialog(backup_info, filename):

    st.warning(
        "Restoring will **replace all current data** - employees, books, "
        "issue records and reservations - with the contents of this "
        "backup. This cannot be undone from within the app (though a "
        "safety copy of your current data is kept automatically)."
    )

    st.caption(f"Backup file: `{filename}`")

    created_at = backup_info["manifest"].get("created_at", "unknown")
    st.caption(f"Created: {created_at}")

    summary = backup_info["summary"]

    st.write(
        f"Contains **{summary.get('employees', 0)}** employees, "
        f"**{summary.get('books', 0)}** books, "
        f"**{summary.get('issued_books', 0)}** issue records, "
        f"**{summary.get('waiting_list', 0)}** reservations."
    )

    col1, col2 = st.columns(2)

    with col1:
        if st.button("Cancel", use_container_width=True, key="cancel_restore_btn"):
            st.rerun()

    with col2:
        if st.button(
            "⚠️ Restore Now",
            type="primary",
            use_container_width=True,
            key="confirm_restore_btn"
        ):
            try:
                restore_from_backup(backup_info["data"])
                st.success("Restore complete. Your data has been replaced with the backup.")
                st.rerun()
            except Exception as e:
                st.error(f"Restore failed: {e}")


# =========================================================
# PAGE HEADER FUNCTION
# =========================================================

def page_header(title, subtitle):

    st.markdown(
        f"""
        <div class="page-title">{title}</div>
        <div class="page-subtitle">{subtitle}</div>
        """,
        unsafe_allow_html=True
    )


# =========================================================
# SIDEBAR
# =========================================================

with st.sidebar:

    st.markdown(
        """
        <div class="sidebar-brand">
            <div class="sidebar-brand-title">
                📚 Company Library
            </div>
            <div class="sidebar-brand-subtitle">
                Library Management System
            </div>
        </div>
        """,
        unsafe_allow_html=True
    )

    st.divider()

    NAV_ITEMS = [
        "🏠 Dashboard",
        "📖 Issue Book",
        "↩️ Return Book",
        "📚 Books",
        "👥 Members",
        "📅 Book Reservation",
        "🔎 Track",
        "📊 Export Report",
        "⚙️ Settings"
    ]

    if "current_page" not in st.session_state:
        st.session_state.current_page = NAV_ITEMS[0]

    for nav_label in NAV_ITEMS:

        is_active = st.session_state.current_page == nav_label

        if st.button(
            nav_label,
            key=f"nav_{nav_label}",
            use_container_width=True,
            type="primary" if is_active else "secondary"
        ):
            st.session_state.current_page = nav_label
            st.rerun()

    page = st.session_state.current_page

    st.divider()

    st.caption("Library Management System")



# =========================================================
# DASHBOARD
# =========================================================

if page == "🏠 Dashboard":

    page_header(
        "Library Dashboard",
        "Overview of books, employees and current library activity"
    )

    members = get_all_members()
    books = get_all_books()
    issued_books = get_currently_issued_books()

    total_members = len(members)
    total_books = len(books)

    available_books = sum(
        1 for book in books
        if book[4] == 1
    )

    issued_count = len(issued_books)

    today = date.today()

    due_today_count = 0
    overdue_count = 0

    for book in issued_books:

        due_date = date.fromisoformat(
            str(book[7])[:10]
        )

        if due_date == today:

            due_today_count += 1

        elif due_date < today:

            overdue_count += 1


    # -----------------------------------------------------
    # KPI CARDS
    # -----------------------------------------------------

    col1, col2, col3, col4 = st.columns(4)

    with col1:

        st.markdown(
            f"""
            <div class="kpi">
                <div class="kpi-label">TOTAL BOOKS</div>
                <div class="kpi-value">{total_books}</div>
                <div class="kpi-small">Books in library</div>
            </div>
            """,
            unsafe_allow_html=True
        )

    with col2:

        st.markdown(
            f"""
            <div class="kpi kpi-available">
                <div class="kpi-label">AVAILABLE</div>
                <div class="kpi-value">{available_books}</div>
                <div class="kpi-small">Ready to issue</div>
            </div>
            """,
            unsafe_allow_html=True
        )

    with col3:

        st.markdown(
            f"""
            <div class="kpi kpi-issued">
                <div class="kpi-label">ISSUED</div>
                <div class="kpi-value">{issued_count}</div>
                <div class="kpi-small">Currently issued</div>
            </div>
            """,
            unsafe_allow_html=True
        )

    with col4:

        st.markdown(
            f"""
            <div class="kpi">
                <div class="kpi-label">EMPLOYEES</div>
                <div class="kpi-value">{total_members}</div>
                <div class="kpi-small">Registered members</div>
            </div>
            """,
            unsafe_allow_html=True
        )


    st.write("")


    # -----------------------------------------------------
    # DUE / OVERDUE
    # -----------------------------------------------------

    col1, col2 = st.columns(2)

    with col1:

        st.markdown(
            f"""
            <div class="kpi kpi-due-today">
                <div class="kpi-label">DUE TODAY</div>
                <div class="kpi-value">{due_today_count}</div>
                <div class="kpi-small">
                    Books that must be returned today
                </div>
            </div>
            """,
            unsafe_allow_html=True
        )

    with col2:

        st.markdown(
            f"""
            <div class="kpi kpi-overdue">
                <div class="kpi-label">OVERDUE</div>
                <div class="kpi-value">{overdue_count}</div>
                <div class="kpi-small">
                    Books past their due date
                </div>
            </div>
            """,
            unsafe_allow_html=True
        )


    st.write("")


    # -----------------------------------------------------
    # SEARCH
    # -----------------------------------------------------

    st.markdown(
        '<div class="card">',
        unsafe_allow_html=True
    )

    st.markdown(
        '<div class="card-title">🔍 Search Issued Books</div>',
        unsafe_allow_html=True
    )

    st.markdown(
        '<div class="card-subtitle">Search currently issued books by book or by employee</div>',
        unsafe_allow_html=True
    )

    search_col1, search_col2 = st.columns([1, 2])

    with search_col1:

        search_mode = st.selectbox(
            "Search by",
            ["Book", "Employee"],
            label_visibility="collapsed"
        )

    with search_col2:

        search_query = st.text_input(
            "Search",
            placeholder=(
                "Search by book title or ID..."
                if search_mode == "Book"
                else "Search by employee name or ID..."
            ),
            label_visibility="collapsed"
        )

    filtered_issued_books = issued_books

    if search_query:

        query_lower = search_query.lower()

        if search_mode == "Book":

            filtered_issued_books = [
                book for book in issued_books
                if query_lower in str(book[4]).lower()
                or query_lower in str(book[5]).lower()
            ]

        else:

            filtered_issued_books = [
                book for book in issued_books
                if query_lower in str(book[1]).lower()
                or query_lower in str(book[2]).lower()
            ]

    st.markdown("</div>", unsafe_allow_html=True)


    st.write("")


    # -----------------------------------------------------
    # DUE TODAY / OVERDUE / UPCOMING (merged from Due Books)
    # -----------------------------------------------------

    due_today_list = []
    overdue_list = []
    upcoming_list = []

    for book in filtered_issued_books:

        due_date_value = date.fromisoformat(
            str(book[7])[:10]
        )

        if due_date_value == today:

            due_today_list.append(book)

        elif due_date_value < today:

            overdue_list.append(book)

        else:

            upcoming_list.append(book)

    def render_issued_table(book_list):

        if not book_list:
            return False

        data = []

        for book in book_list:

            data.append([
                book[1],
                book[2],
                book[3],
                book[4],
                book[5],
                book[7]
            ])

        df = pd.DataFrame(
            data,
            columns=[
                "Employee ID",
                "Employee Name",
                "Email",
                "Book ID",
                "Book Title",
                "Due Date"
            ]
        )

        st.dataframe(
            df,
            use_container_width=True,
            hide_index=True
        )

        return True

    st.markdown("### 🔔 Due Today")

    if not render_issued_table(due_today_list):
        st.success("No books are due today.")

    st.markdown("### ⚠️ Overdue")

    if not render_issued_table(overdue_list):
        st.success("No overdue books.")

    st.markdown("### 📆 Upcoming")

    if not render_issued_table(upcoming_list):
        st.info("No upcoming books.")


# =========================================================
# MEMBERS
# =========================================================

elif page == "👥 Members":

    page_header(
        "Members",
        "Manage employees registered with the company library"
    )

    # -----------------------------------------------------
    # ADD EMPLOYEE
    # -----------------------------------------------------

    st.markdown(
        '<div class="card">',
        unsafe_allow_html=True
    )

    st.markdown(
        '<div class="card-title">➕ Add Employee</div>',
        unsafe_allow_html=True
    )

    st.markdown(
        '<div class="card-subtitle">Enter employee information</div>',
        unsafe_allow_html=True
    )

    with st.form("add_employee_form"):

        col1, col2 = st.columns(2)

        with col1:

            employee_id_input = st.text_input(
                "Employee ID"
            )

            employee_name_input = st.text_input(
                "Employee Name"
            )

        with col2:

            employee_email_input = st.text_input(
                "Email"
            )

            department_input = st.text_input(
                "Department"
            )

        submit = st.form_submit_button(
            "💾 Save",
            use_container_width=True
        )

        if submit:

            if not employee_id_input.strip():

                st.error("Please enter Employee ID.")

            elif not employee_name_input.strip():

                st.error("Please enter Employee Name.")

            elif not employee_email_input.strip():

                st.error("Please enter Email.")

            else:

                try:

                    add_employee(
                        employee_id_input.strip(),
                        employee_name_input.strip(),
                        employee_email_input.strip(),
                        department_input.strip()
                    )

                    st.success(
                        "Employee added successfully."
                    )

                except sqlite3.IntegrityError:

                    st.error(
                        "Employee ID already exists."
                    )

                except Exception as e:

                    st.error(
                        f"Error: {e}"
                    )

    st.markdown("</div>", unsafe_allow_html=True)


    # -----------------------------------------------------
    # EMPLOYEE DIRECTORY (Edit / Delete buttons per row)
    # -----------------------------------------------------

    members = get_all_members()

    if members:

        search = st.text_input(
            "🔎 Search employee",
            placeholder="Search by ID, name or department..."
        )

        filtered_members = members

        if search:

            search_lower = search.lower()

            filtered_members = [
                member
                for member in members
                if search_lower in str(member[0]).lower()
                or search_lower in str(member[1]).lower()
                or search_lower in str(member[3]).lower()
            ]

        if filtered_members:

            header_cols = st.columns([2, 2, 3, 2, 1, 1])

            for header_col, header_label in zip(
                header_cols,
                ["Employee ID", "Name", "Email", "Department", "", ""]
            ):
                header_col.markdown(f"**{header_label}**")

            for employee_id, name, email, department in filtered_members:

                row_cols = st.columns([2, 2, 3, 2, 1, 1])

                row_cols[0].write(employee_id)
                row_cols[1].write(name)
                row_cols[2].write(email)
                row_cols[3].write(department)

                if row_cols[4].button(
                    "✏️",
                    key=f"edit_employee_{employee_id}",
                    help="Edit this employee",
                    use_container_width=True
                ):
                    edit_employee_dialog(employee_id, name, email, department)

                if row_cols[5].button(
                    "🗑️",
                    key=f"delete_employee_{employee_id}",
                    help="Delete this employee",
                    use_container_width=True
                ):
                    delete_employee_dialog(employee_id, name)

        else:

            st.info("No employees match your search.")

    else:

        st.info(
            "No employees found."
        )


# =========================================================
# BOOKS
# =========================================================

elif page == "📚 Books":

    page_header(
        "Books",
        "Manage and monitor the company library catalogue"
    )

    # -----------------------------------------------------
    # ADD BOOK
    # -----------------------------------------------------

    st.markdown(
        '<div class="card">',
        unsafe_allow_html=True
    )

    st.markdown(
        '<div class="card-title">➕ Add New Book</div>',
        unsafe_allow_html=True
    )

    st.markdown(
        '<div class="card-subtitle">Add a new book to the library</div>',
        unsafe_allow_html=True
    )

    BOOK_CATEGORIES = [
        "Fiction",
        "Non-Fiction",
        "Self Help",
        "Programming",
        "Biography",
        "Fantasy",
        "Science",
        "History",
        "Business",
        "Other"
    ]

    with st.form("add_book_form"):

        col1, col2 = st.columns(2)

        with col1:

            book_id_input = st.text_input(
                "Book ID"
            )

            title_input = st.text_input(
                "Book Title"
            )

            author_input = st.text_input(
                "Author"
            )

        with col2:

            category_choice = st.selectbox(
                "Category",
                BOOK_CATEGORIES
            )

            category_other_input = st.text_input(
                "Category (if 'Other')",
                placeholder="Type a custom category"
            )

            status_choice = st.selectbox(
                "Status",
                ["Available", "Issued"]
            )

        submit = st.form_submit_button(
            "💾 Save",
            use_container_width=True
        )

        if submit:

            category_input = (
                category_other_input.strip()
                if category_choice == "Other"
                else category_choice
            )

            if not book_id_input.strip():

                st.error(
                    "Please enter Book ID."
                )

            elif not title_input.strip():

                st.error(
                    "Please enter Book Title."
                )

            elif category_choice == "Other" and not category_other_input.strip():

                st.error(
                    "Please type a custom category."
                )

            else:

                try:

                    add_book(
                        book_id_input.strip(),
                        title_input.strip(),
                        author_input.strip(),
                        category_input,
                        available=1 if status_choice == "Available" else 0
                    )

                    st.success(
                        "Book added successfully."
                    )

                except sqlite3.IntegrityError:

                    st.error(
                        "Book ID already exists."
                    )

                except Exception as e:

                    st.error(
                        f"Error: {e}"
                    )

    st.markdown("</div>", unsafe_allow_html=True)


    # -----------------------------------------------------
    # BOOK CATALOGUE (Edit / Delete buttons per row)
    # -----------------------------------------------------

    books = get_all_books()

    if books:

        search = st.text_input(
            "🔎 Search books",
            placeholder="Search by book ID, title, author or category..."
        )

        filtered_books = books

        if search:

            search_lower = search.lower()

            filtered_books = [
                book
                for book in books
                if search_lower in str(book[0]).lower()
                or search_lower in str(book[1]).lower()
                or search_lower in str(book[2]).lower()
                or search_lower in str(book[3]).lower()
            ]

        if filtered_books:

            column_widths = [1.3, 2, 1.6, 1.3, 1, 1, 0.7, 0.7]

            header_cols = st.columns(column_widths)

            for header_col, header_label in zip(
                header_cols,
                ["Book ID", "Title", "Author", "Category", "Status", "Condition", "", ""]
            ):
                header_col.markdown(f"**{header_label}**")

            for book_id, title, author, category, available, condition in filtered_books:

                status = "Available" if available == 1 else "Issued"

                row_cols = st.columns(column_widths)

                row_cols[0].write(book_id)
                row_cols[1].write(title)
                row_cols[2].write(author)
                row_cols[3].write(category)

                if status == "Available":
                    row_cols[4].markdown(f'<span class="status-available">{status}</span>', unsafe_allow_html=True)
                else:
                    row_cols[4].markdown(f'<span class="status-issued">{status}</span>', unsafe_allow_html=True)

                row_cols[5].write(condition)

                if row_cols[6].button(
                    "✏️",
                    key=f"edit_book_{book_id}",
                    help="Edit this book",
                    use_container_width=True
                ):
                    edit_book_dialog(book_id, title, author, category)

                if row_cols[7].button(
                    "🗑️",
                    key=f"delete_book_{book_id}",
                    help="Delete this book",
                    use_container_width=True
                ):
                    delete_book_dialog(book_id, title)

        else:

            st.info("No books match your search.")

    else:

        st.info(
            "No books found."
        )


# =========================================================
# BOOK RESERVATION
# =========================================================

elif page == "📅 Book Reservation":

    page_header(
        "Book Reservation",
        "Reserve an issued book and manage the waiting list"
    )

    books = get_all_books()
    members = get_all_members()

    unavailable_books = [book for book in books if book[4] == 0]

    st.markdown('<div class="card">', unsafe_allow_html=True)
    st.markdown(
        '<div class="card-title">📅 Reserve a Book</div>',
        unsafe_allow_html=True
    )
    st.markdown(
        '<div class="card-subtitle">Add an employee to the waiting list for a currently issued book</div>',
        unsafe_allow_html=True
    )

    if not unavailable_books:
        st.info("No books are currently issued, so there are no books available for reservation.")
    elif not members:
        st.info("Add an employee first before making a reservation.")
    else:
        col1, col2 = st.columns(2)

        with col1:
            reservation_book_options = {
                f"{book[0]} — {book[1]}": book
                for book in unavailable_books
            }
            selected_reservation_book_label = st.selectbox(
                "Book",
                list(reservation_book_options.keys()),
                index=None,
                placeholder="Select a book",
                key="reservation_book_select"
            )

        with col2:
            reservation_employee_options = {
                f"{member[0]} — {member[1]}": member
                for member in members
            }
            selected_reservation_employee_label = st.selectbox(
                "Employee",
                list(reservation_employee_options.keys()),
                index=None,
                placeholder="Select an employee",
                key="reservation_employee_select"
            )

        if st.button(
            "📅 Reserve Book",
            use_container_width=True,
            key="reserve_book_btn",
            disabled=(
                selected_reservation_book_label is None
                or selected_reservation_employee_label is None
            )
        ):
            reservation_book = reservation_book_options[selected_reservation_book_label]
            reservation_employee = reservation_employee_options[selected_reservation_employee_label]

            try:
                add_to_waiting_list(
                    reservation_book[0],
                    reservation_book[1],
                    reservation_employee[0],
                    reservation_employee[1],
                    reservation_employee[2]
                )
                st.success(
                    f"{reservation_employee[1]} reserved '{reservation_book[1]}'."
                )
                st.rerun()
            except ValueError as e:
                st.error(str(e))
            except Exception as e:
                st.error(f"Error creating reservation: {e}")

    st.markdown('</div>', unsafe_allow_html=True)

    st.markdown('<div class="card">', unsafe_allow_html=True)
    st.markdown(
        '<div class="card-title">🕒 Current Reservations</div>',
        unsafe_allow_html=True
    )
    st.markdown(
        '<div class="card-subtitle">Employees waiting for books that are currently issued</div>',
        unsafe_allow_html=True
    )

    reservations = get_reservation_list()

    if reservations:
        reservation_df = pd.DataFrame(
            [
                [entry[1], entry[2], entry[3], entry[4], entry[6], entry[7]]
                for entry in reservations
            ],
            columns=[
                "Book ID",
                "Book Title",
                "Employee ID",
                "Employee Name",
                "Requested On",
                "Notified"
            ]
        )
        st.dataframe(reservation_df, use_container_width=True, hide_index=True)

        remove_options = {
            f"{entry[4]} — {entry[2]}": entry[0]
            for entry in reservations
        }
        remove_col1, remove_col2 = st.columns([3, 1])
        with remove_col1:
            selected_remove = st.selectbox(
                "Remove reservation",
                list(remove_options.keys()),
                key="reservation_remove_select"
            )
        with remove_col2:
            if st.button(
                "🗑️ Remove",
                use_container_width=True,
                key="reservation_remove_btn"
            ):
                remove_from_waiting_list(remove_options[selected_remove])
                st.success("Reservation removed.")
                st.rerun()
    else:
        st.info("No active reservations.")

    st.markdown('</div>', unsafe_allow_html=True)


# =========================================================
# TRACK
# =========================================================

elif page == "🔎 Track":

    page_header(
        "Track Books",
        "Track book activity by book name or employee"
    )

    records = get_all_issue_records()

    st.markdown('<div class="card">', unsafe_allow_html=True)
    st.markdown(
        '<div class="card-title">🔎 Track Records</div>',
        unsafe_allow_html=True
    )
    st.markdown(
        '<div class="card-subtitle">Search current and returned book records</div>',
        unsafe_allow_html=True
    )

    if not records:
        st.info("No issue or return records found.")
    else:
        track_mode = st.selectbox(
            "Track By",
            ["Book Name", "Employee"],
            key="track_mode"
        )

        if track_mode == "Book Name":
            search_text = st.text_input(
                "Book Name",
                placeholder="Enter book name",
                key="track_book_search"
            ).strip().lower()

            filtered_records = [
                row for row in records
                if search_text in str(row[5]).lower()
            ] if search_text else records
        else:
            search_text = st.text_input(
                "Employee",
                placeholder="Enter employee name or ID",
                key="track_employee_search"
            ).strip().lower()

            filtered_records = [
                row for row in records
                if search_text in str(row[2]).lower()
                or search_text in str(row[1]).lower()
            ] if search_text else records

        track_df = pd.DataFrame(
            [
                [
                    row[1], row[2], row[4], row[5],
                    row[6], row[7], row[8] or "—", row[9]
                ]
                for row in filtered_records
            ],
            columns=[
                "Employee ID",
                "Employee Name",
                "Book ID",
                "Book Name",
                "Issue Date",
                "Due Date",
                "Return Date",
                "Status"
            ]
        )

        st.caption(f"Showing {len(track_df)} record(s).")
        st.dataframe(track_df, use_container_width=True, hide_index=True)

    st.markdown('</div>', unsafe_allow_html=True)


# =========================================================
# EXPORT REPORT
# =========================================================

elif page == "📊 Export Report":

    page_header(
        "Export Report",
        "Download library reports for analysis and sharing"
    )

    records = get_all_issue_records()
    members = get_all_members()
    books = get_all_books()

    report_df = pd.DataFrame(
        [
            [
                row[0], row[1], row[2], row[3], row[4], row[5],
                row[6], row[7], row[8] or "", row[9]
            ]
            for row in records
        ],
        columns=[
            "Record ID", "Employee ID", "Employee Name", "Employee Email",
            "Book ID", "Book Name", "Issue Date", "Due Date",
            "Return Date", "Status"
        ]
    )

    members_df = pd.DataFrame(
        members,
        columns=["Employee ID", "Employee Name", "Email", "Department"]
    )

    books_df = pd.DataFrame(
        [
            [book[0], book[1], book[2], book[3],
             "Available" if book[4] == 1 else "Issued", book[5]]
            for book in books
        ],
        columns=["Book ID", "Title", "Author", "Category", "Status", "Condition"]
    )

    reservations = get_reservation_list()
    reservations_df = pd.DataFrame(
        [
            [entry[1], entry[2], entry[3], entry[4], entry[6], entry[7]]
            for entry in reservations
        ],
        columns=[
            "Book ID", "Book Title", "Employee ID", "Employee Name",
            "Requested On", "Notified"
        ]
    )

    st.markdown('<div class="card">', unsafe_allow_html=True)
    st.markdown(
        '<div class="card-title">📊 Reports</div>',
        unsafe_allow_html=True
    )

    st.write("Choose a report to download.")

    report_choice = st.selectbox(
        "Report",
        ["Issue & Return Records", "Books", "Members", "Book Reservations"],
        key="export_report_choice"
    )

    selected_report = {
        "Issue & Return Records": report_df,
        "Books": books_df,
        "Members": members_df,
        "Book Reservations": reservations_df
    }[report_choice]

    csv_data = selected_report.to_csv(index=False).encode("utf-8")

    st.download_button(
        "⬇️ Download CSV",
        data=csv_data,
        file_name=f"{report_choice.lower().replace(' ', '_').replace('&', 'and')}.csv",
        mime="text/csv",
        use_container_width=True,
        key="download_report_csv"
    )

    st.markdown('</div>', unsafe_allow_html=True)

    st.markdown('<div class="card">', unsafe_allow_html=True)
    st.markdown(
        '<div class="card-title">📁 Sync Database to Excel</div>',
        unsafe_allow_html=True
    )
    st.write("Update the main LibraryBooks.xlsx file with the latest application data.")

    if st.button(
        "📤 Export All Data to Excel",
        use_container_width=True,
        key="export_all_excel"
    ):
        try:
            excel_path = export_database_to_excel()
            st.success(f"Excel report updated successfully: {excel_path}")
        except Exception as e:
            st.error(f"Could not export to Excel: {e}")

    st.markdown('</div>', unsafe_allow_html=True)


# =========================================================
# SETTINGS
# =========================================================

elif page == "⚙️ Settings":

    page_header(
        "Settings",
        "Application maintenance and cache controls"
    )

    st.markdown('<div class="card">', unsafe_allow_html=True)
    st.markdown(
        '<div class="card-title">⚙️ Application Settings</div>',
        unsafe_allow_html=True
    )
    st.markdown(
        '<div class="card-subtitle">Use this section for maintenance actions</div>',
        unsafe_allow_html=True
    )

    st.markdown("### 🧹 Clear Cache")
    st.write("Clear Streamlit cached data and resources without deleting your library database or Excel data.")

    if st.button(
        "🧹 Clear Cache",
        use_container_width=True,
        key="clear_cache_btn"
    ):
        try:
            st.cache_data.clear()
            st.cache_resource.clear()
        except Exception:
            pass

        st.success("Cache cleared successfully. Your library data was not deleted.")

    st.markdown('</div>', unsafe_allow_html=True)


    # -----------------------------------------------------
    # BACKUP & RESTORE
    # -----------------------------------------------------

    st.markdown('<div class="card">', unsafe_allow_html=True)
    st.markdown(
        '<div class="card-title">💾 Backup &amp; Restore</div>',
        unsafe_allow_html=True
    )
    st.markdown(
        '<div class="card-subtitle">Save a local backup of all library data, '
        'or restore from a previous backup. Fully offline - nothing leaves '
        'this computer.</div>',
        unsafe_allow_html=True
    )

    _webview_window = _get_webview_window()

    backup_col, restore_col = st.columns(2)

    with backup_col:

        st.markdown("#### ⬇️ Create Backup")
        st.write(
            "Saves employees, books, issue records and reservations to a "
            "single file you choose."
        )

        _default_backup_name = f"CompanyLibrary_Backup_{datetime.now():%Y-%m-%d_%H%M%S}.zip"

        if st.button(
            "⬇️ Create Backup",
            use_container_width=True,
            key="create_backup_btn"
        ):
            try:
                _backup_bytes = build_backup_bytes()
            except Exception as e:
                st.error(f"Could not create backup: {e}")
                _backup_bytes = None

            if _backup_bytes is not None:

                if _webview_window is not None:

                    _save_path = _webview_window.create_file_dialog(
                        webview.SAVE_DIALOG,
                        directory=str(Path.home() / "Downloads"),
                        save_filename=_default_backup_name,
                        file_types=("Backup files (*.zip)", "All files (*.*)")
                    )

                    if _save_path:
                        _target = Path(
                            _save_path[0] if isinstance(_save_path, (list, tuple))
                            else _save_path
                        )
                        try:
                            _target.write_bytes(_backup_bytes)
                            st.success(f"Backup saved to {_target}")
                        except Exception as e:
                            st.error(f"Could not save backup to that location: {e}")
                    else:
                        st.info("Backup cancelled.")

                else:
                    # No native window (e.g. running in a plain browser
                    # during development) - fall back to a normal
                    # browser download, which still lets the user pick
                    # where it's saved.
                    st.download_button(
                        "⬇️ Download Backup File",
                        data=_backup_bytes,
                        file_name=_default_backup_name,
                        mime="application/zip",
                        use_container_width=True,
                        key="download_backup_btn"
                    )

    with restore_col:

        st.markdown("#### ⬆️ Restore from Backup")
        st.write(
            "Choose a previously created backup file. You'll be asked to "
            "confirm before anything is replaced."
        )

        _restore_bytes = None
        _restore_filename = None

        if _webview_window is not None:

            if st.button(
                "⬆️ Choose Backup File...",
                use_container_width=True,
                key="restore_pick_btn"
            ):
                _open_path = _webview_window.create_file_dialog(
                    webview.OPEN_DIALOG,
                    directory=str(Path.home()),
                    file_types=("Backup files (*.zip)", "All files (*.*)"),
                    allow_multiple=False,
                )

                if _open_path:
                    _chosen = Path(
                        _open_path[0] if isinstance(_open_path, (list, tuple))
                        else _open_path
                    )
                    try:
                        _restore_bytes = _chosen.read_bytes()
                        _restore_filename = _chosen.name
                    except Exception as e:
                        st.error(f"Could not read that file: {e}")

        else:
            # No native window - use a normal file uploader instead, so
            # restore is still testable from a plain browser.
            _uploaded = st.file_uploader(
                "Choose a backup file",
                type=["zip"],
                key="restore_uploader",
                label_visibility="collapsed"
            )

            if _uploaded is not None:
                _restore_bytes = _uploaded.getvalue()
                _restore_filename = _uploaded.name

        if _restore_bytes is not None:

            _is_valid, _result = validate_backup_bytes(_restore_bytes)

            if _is_valid:
                confirm_restore_dialog(_result, _restore_filename)
            else:
                st.error(f"Invalid backup file: {_result}")

    st.markdown('</div>', unsafe_allow_html=True)


    # -----------------------------------------------------
    # REMINDER EMAILS
    # -----------------------------------------------------

    st.markdown('<div class="card">', unsafe_allow_html=True)
    st.markdown(
        '<div class="card-title">📧 Reminder Emails</div>',
        unsafe_allow_html=True
    )
    st.markdown(
        '<div class="card-subtitle">Automatically email employees about books '
        'due soon or overdue. Checked once each time the app starts, or on '
        'demand below.</div>',
        unsafe_allow_html=True
    )

    _email_config = email_reminders.load_email_config()

    _reminder_enabled = st.checkbox(
        "Enable reminder emails",
        value=_email_config["enabled"],
        key="reminder_enabled_checkbox"
    )

    with st.form("reminder_settings_form"):

        st.markdown("**Sender account**")

        col1, col2 = st.columns(2)

        with col1:
            _sender_email_input = st.text_input(
                "Sender email address",
                value=_email_config["sender_email"]
            )

        with col2:
            _app_password_input = st.text_input(
                "App password",
                value="",
                type="password",
                placeholder=(
                    "Leave blank to keep current password"
                    if _email_config["app_password"]
                    else "Enter app password"
                )
            )

        st.caption(
            "If sending fails with an authentication error, your Microsoft "
            "365 tenant may have SMTP AUTH (basic authentication) disabled "
            "- check with IT."
        )

        col3, col4 = st.columns(2)

        with col3:
            _smtp_server_input = st.text_input(
                "SMTP server",
                value=_email_config["smtp_server"]
            )

        with col4:
            _smtp_port_input = st.number_input(
                "SMTP port",
                value=int(_email_config["smtp_port"]),
                min_value=1,
                max_value=65535,
                step=1
            )

        st.markdown("**Reminder timing (days)**")

        col5, col6, col7, col8 = st.columns(4)

        with col5:
            _due_soon_input = st.number_input(
                "Due within",
                value=int(_email_config["due_soon_days"]),
                min_value=1,
                max_value=30,
                step=1,
                help="Send a reminder when a book's due date is this many days away."
            )

        with col6:
            _stage1_input = st.number_input(
                "1st overdue notice",
                value=int(_email_config["overdue_stage1_days"]),
                min_value=1,
                max_value=90,
                step=1,
                help="Days after the due date."
            )

        with col7:
            _stage2_input = st.number_input(
                "2nd overdue notice",
                value=int(_email_config["overdue_stage2_days"]),
                min_value=1,
                max_value=90,
                step=1,
                help="Days after the due date."
            )

        with col8:
            _stage3_input = st.number_input(
                "Final overdue notice",
                value=int(_email_config["overdue_stage3_days"]),
                min_value=1,
                max_value=180,
                step=1,
                help="Days after the due date. This notice can mention a fine."
            )

        st.markdown("**Fine (mentioned only in the final overdue notice)**")

        col9, col10 = st.columns(2)

        with col9:
            _fine_per_day_input = st.number_input(
                "Fine per day overdue",
                value=float(_email_config["fine_per_day"]),
                min_value=0.0,
                step=1.0,
                help="0 = no fine mentioned in the email."
            )

        with col10:
            _fine_currency_input = st.text_input(
                "Currency symbol",
                value=_email_config["fine_currency"]
            )

        _save_settings = st.form_submit_button(
            "💾 Save Settings",
            use_container_width=True
        )

        if _save_settings:

            if not _sender_email_input.strip():
                st.error("Sender email address cannot be empty.")
            elif not (_stage1_input < _stage2_input < _stage3_input):
                st.error(
                    "Overdue notice days must increase in order "
                    "(1st < 2nd < Final)."
                )
            else:
                _new_config = {
                    "enabled": _reminder_enabled,
                    "sender_email": _sender_email_input.strip(),
                    "smtp_server": _smtp_server_input.strip(),
                    "smtp_port": int(_smtp_port_input),
                    "due_soon_days": int(_due_soon_input),
                    "overdue_stage1_days": int(_stage1_input),
                    "overdue_stage2_days": int(_stage2_input),
                    "overdue_stage3_days": int(_stage3_input),
                    "fine_per_day": float(_fine_per_day_input),
                    "fine_currency": _fine_currency_input.strip(),
                }

                email_reminders.save_email_config(
                    _new_config,
                    new_app_password=_app_password_input.strip() or None
                )

                st.success("Reminder email settings saved.")
                st.rerun()

    st.write("")

    _test_col, _send_now_col = st.columns(2)

    with _test_col:

        if st.button(
            "✉️ Send Test Email",
            use_container_width=True,
            key="send_test_email_btn"
        ):
            _current_config = email_reminders.load_email_config()

            if not _current_config["sender_email"] or not _current_config["app_password"]:
                st.error("Set a sender email and app password first, then save.")
            else:
                try:
                    email_reminders.send_test_email(_current_config)
                    st.success(f"Test email sent to {_current_config['sender_email']}.")
                except Exception as e:
                    st.error(f"Could not send test email: {e}")

    with _send_now_col:

        if st.button(
            "📧 Check & Send Reminders Now",
            use_container_width=True,
            key="send_reminders_now_btn"
        ):
            _current_config = email_reminders.load_email_config()

            if not _current_config["enabled"]:
                st.warning("Reminder emails are disabled - enable and save above first.")
            elif not _current_config["sender_email"] or not _current_config["app_password"]:
                st.error("Set a sender email and app password first, then save.")
            else:
                _result = email_reminders.check_and_send_reminders(_current_config)

                st.success(
                    f"Checked {_result['checked']} issued book(s), "
                    f"sent {_result['sent']} reminder email(s)."
                )

                for _err in _result["errors"]:
                    st.error(_err)

    st.markdown('</div>', unsafe_allow_html=True)


# =========================================================
# ISSUE BOOK
# =========================================================

elif page == "📖 Issue Book":

    page_header(
        "Issue Book",
        "Issue an available book to an employee"
    )

    members = get_all_members()
    books = get_all_books()

    available_books = [
        book
        for book in books
        if book[4] == 1
    ]

    if not members:

        st.warning(
            "Please add employees before issuing a book."
        )

    elif not available_books:

        st.warning(
            "There are currently no available books."
        )

    else:

        st.markdown(
            '<div class="card">',
            unsafe_allow_html=True
        )

        st.markdown(
            '<div class="card-title">📖 Issue Book</div>',
            unsafe_allow_html=True
        )

        st.markdown(
            '<div class="card-subtitle">Select employee, book and issue dates</div>',
            unsafe_allow_html=True
        )

        # -------------------------------------------------
        # EMPLOYEE
        # -------------------------------------------------

        employee_options = {
            f"{member[0]} — {member[1]}": member
            for member in members
        }

        selected_employee_text = st.selectbox(
            "Select Employee",
            list(employee_options.keys()),
            index=None,
            placeholder="Select an employee",
            key="issue_employee_select"
        )

        employee = employee_options.get(selected_employee_text) if selected_employee_text else None

        employee_id = employee[0] if employee else None
        employee_name = employee[1] if employee else None
        employee_email = employee[2] if employee else None

        # -------------------------------------------------
        # BOOK
        # -------------------------------------------------

        book_options = {
            f"{book[0]} — {book[1]}": book
            for book in available_books
        }

        selected_book_text = st.selectbox(
            "Select Book",
            list(book_options.keys()),
            index=None,
            placeholder="Select a book",
            key="issue_book_select"
        )

        book = book_options.get(selected_book_text) if selected_book_text else None

        book_id = book[0] if book else None
        book_title = book[1] if book else None

        # -------------------------------------------------
        # DATES
        # -------------------------------------------------

        col1, col2 = st.columns(2)

        with col1:

            issue_date = st.date_input(
                "Issue Date",
                value=None,
                key="issue_date_input"
            )

        with col2:

            due_date = st.date_input(
                "Due Date",
                value=None,
                key="due_date_input"
            )

        st.divider()

        # -------------------------------------------------
        # PREVIEW
        # -------------------------------------------------

        st.markdown("### Issue Summary")

        col1, col2, col3 = st.columns(3)

        with col1:

            st.write("**Employee**")
            st.write(employee_name or "—")

        with col2:

            st.write("**Book**")
            st.write(book_title or "—")

        with col3:

            st.write("**Due Date**")
            st.write(due_date or "—")

        st.write("")

        # -------------------------------------------------
        # ISSUE
        # -------------------------------------------------

        if st.button(
            "📖 Issue Book",
            use_container_width=True,
            disabled=(
                employee is None
                or book is None
                or issue_date is None
                or due_date is None
            )
        ):

            if due_date < issue_date:

                st.error(
                    "Due Date cannot be before Issue Date."
                )

            else:

                connection = get_connection()
                cursor = connection.cursor()

                try:

                    cursor.execute("""
                        INSERT INTO issued_books
                        (
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
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """, (
                        employee_id,
                        employee_name,
                        employee_email,
                        book_id,
                        book_title,
                        issue_date.isoformat(),
                        due_date.isoformat(),
                        None,
                        "Issued",
                        0
                    ))

                    cursor.execute("""
                        UPDATE books
                        SET available = 0
                        WHERE book_id = ?
                    """, (
                        book_id,
                    ))

                    connection.commit()

                    st.session_state.books_version += 1

                    st.success(
                        f"'{book_title}' has been issued to {employee_name}."
                    )

                    try:
                        export_database_to_excel()
                    except Exception as sync_error:
                        st.warning(
                            f"Book issued, but couldn't sync to Excel: {sync_error}"
                        )

                except Exception as e:

                    connection.rollback()

                    st.error(
                        f"Error issuing book: {e}"
                    )

                finally:

                    connection.close()

        st.markdown("</div>", unsafe_allow_html=True)


# =========================================================
# RETURN BOOK
# =========================================================

elif page == "↩️ Return Book":

    page_header(
        "Return Book",
        "Process a book returned by an employee"
    )

    issued_books = get_currently_issued_books()

    if not issued_books:

        st.success(
            "There are currently no issued books."
        )

    else:

        st.markdown(
            '<div class="card">',
            unsafe_allow_html=True
        )

        st.markdown(
            '<div class="card-title">↩️ Return Book</div>',
            unsafe_allow_html=True
        )

        st.markdown(
            '<div class="card-subtitle">Select the book being returned</div>',
            unsafe_allow_html=True
        )

        # -------------------------------------------------
        # SELECT BOOK
        # -------------------------------------------------

        book_options = {
            f"{book[5]} — {book[2]} (Due: {book[7]})": book
            for book in issued_books
        }

        selected_text = st.selectbox(
            "Select Issued Book",
            list(book_options.keys()),
            index=None,
            placeholder="Select an issued book",
            key="return_book_select"
        )

        selected_book = book_options.get(selected_text) if selected_text else None

        if selected_book is None:
            st.info("Select an issued book to view its return details.")
        else:

            # -------------------------------------------------
            # GET DETAILS
            # -------------------------------------------------

            issue_record_id = selected_book[0]
            employee_id = selected_book[1]
            employee_name = selected_book[2]
            employee_email = selected_book[3]
            book_id = selected_book[4]
            book_title = selected_book[5]
            issue_date = selected_book[6]
            due_date = selected_book[7]

            # -------------------------------------------------
            # EMPLOYEE DETAILS
            # -------------------------------------------------

            st.markdown("### 👤 Employee Details")

            col1, col2, col3 = st.columns(3)

            with col1:
                st.caption("Employee ID")
                st.write(employee_id)

            with col2:
                st.caption("Employee Name")
                st.write(employee_name)

            with col3:
                st.caption("Email")
                st.write(employee_email)

            st.divider()

            # -------------------------------------------------
            # BOOK DETAILS
            # -------------------------------------------------

            st.markdown("### 📚 Book Details")

            col1, col2, col3 = st.columns(3)

            with col1:
                st.caption("Book ID")
                st.write(book_id)

            with col2:
                st.caption("Book Title")
                st.write(book_title)

            with col3:
                st.caption("Issue Date")
                st.write(issue_date)

            col1, col2 = st.columns(2)

            with col1:
                st.caption("Due Date")
                st.write(due_date)

            with col2:
                return_date = st.date_input(
                    "Return Date",
                    value=None,
                    key="return_date_input"
                )

            book_condition = st.selectbox(
                "Book Condition",
                ["Good", "Fair", "Damaged", "Lost"],
                index=None,
                placeholder="Select book condition",
                key="return_book_condition"
            )

            confirm_return = st.checkbox(
                f"I confirm '{book_title}' has been returned by {employee_name} "
                f"in {(book_condition or 'selected').lower()} condition."
            )

            st.divider()

            # -------------------------------------------------
            # RETURN BUTTON
            # -------------------------------------------------

            if st.button(
                "↩️ Confirm Return",
                use_container_width=True,
                disabled=(
                    not confirm_return
                    or return_date is None
                    or book_condition is None
                )
            ):

                connection = get_connection()
                cursor = connection.cursor()

                try:

                    cursor.execute("""
                        UPDATE issued_books
                        SET
                            return_date = ?,
                            status = 'Returned'
                        WHERE id = ?
                    """, (
                        return_date.isoformat(),
                        issue_record_id
                    ))

                    # A lost/damaged book shouldn't go straight back into
                    # the "Available" pool for others to borrow.
                    new_available = 1 if book_condition in ("Good", "Fair") else 0

                    cursor.execute("""
                        UPDATE books
                        SET available = ?,
                            condition = ?
                        WHERE book_id = ?
                    """, (
                        new_available,
                        book_condition,
                        book_id,
                    ))

                    connection.commit()

                    st.session_state.books_version += 1

                    st.toast(
                        f"'{book_title}' returned by {employee_name} "
                        f"({book_condition}).",
                        icon="✅"
                    )

                    waiting_for_this_book = get_waiting_list(book_id)

                    if waiting_for_this_book and new_available == 1:
                        next_in_line = waiting_for_this_book[0]
                        st.toast(
                            f"📋 {next_in_line[4]} is next on the waiting list "
                            f"for '{book_title}'.",
                            icon="🕒"
                        )

                    try:
                        export_database_to_excel()
                    except Exception as sync_error:
                        st.warning(
                            f"Book returned, but couldn't sync to Excel: {sync_error}"
                        )

                    connection.close()

                    st.rerun()

                except Exception as e:

                    connection.rollback()
                    connection.close()

                    st.error(
                        f"Error returning book: {e}"
                    )

        st.markdown("</div>", unsafe_allow_html=True)

