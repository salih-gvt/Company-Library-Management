"""
Automatic due-date reminder emails.

Reads/writes its own small config file (sender address, SMTP details,
reminder thresholds, fine rate) under DATA_DIR, separate from
library.db. The app password in that config is never stored in
plaintext - it's encrypted with Windows DPAPI (tied to the current
Windows user account), the same mechanism Windows itself uses for
saved credentials, so the encrypted blob is useless outside this
Windows user account.

Reminder stages (each tracked independently per issue record, so a
book overdue long enough to pass several thresholds gets exactly one
email per stage, never one per day, and re-issuing a book after it's
returned starts the tracking over):
  - due_soon: due date is within N days (not yet overdue)
  - stage1:   N days after the due date
  - stage2:   N days after the due date
  - stage3:   N days after the due date (mentions a fine, if configured)
"""

import base64
import ctypes
import json
import smtplib
from ctypes import wintypes
from datetime import date
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

from database import DATA_DIR, get_connection

EMAIL_CONFIG_FILE = DATA_DIR / "email_config.json"

DEFAULT_CONFIG = {
    "enabled": False,
    "sender_email": "info@gravity-bp.com",
    "smtp_server": "smtp.office365.com",
    "smtp_port": 587,
    "due_soon_days": 3,
    "overdue_stage1_days": 3,
    "overdue_stage2_days": 10,
    "overdue_stage3_days": 15,
    "fine_per_day": 0.0,
    "fine_currency": "₹",
}


# =========================================================
# WINDOWS DPAPI (encrypt/decrypt tied to the current Windows user)
# =========================================================

class _DataBlob(ctypes.Structure):
    _fields_ = [("cbData", wintypes.DWORD), ("pbData", ctypes.POINTER(ctypes.c_char))]


def _make_blob(data: bytes):
    buffer = ctypes.create_string_buffer(data, len(data))
    blob = _DataBlob()
    blob.pbData = ctypes.cast(buffer, ctypes.POINTER(ctypes.c_char))
    blob.cbData = len(data)
    return blob, buffer  # buffer must stay alive as long as blob is used


def _dpapi_protect(data: bytes) -> bytes:
    in_blob, _keep_alive = _make_blob(data)
    out_blob = _DataBlob()

    success = ctypes.windll.crypt32.CryptProtectData(
        ctypes.byref(in_blob), None, None, None, None, 0, ctypes.byref(out_blob)
    )
    if not success:
        raise ctypes.WinError()

    try:
        return ctypes.string_at(out_blob.pbData, out_blob.cbData)
    finally:
        ctypes.windll.kernel32.LocalFree(out_blob.pbData)


def _dpapi_unprotect(data: bytes) -> bytes:
    in_blob, _keep_alive = _make_blob(data)
    out_blob = _DataBlob()

    success = ctypes.windll.crypt32.CryptUnprotectData(
        ctypes.byref(in_blob), None, None, None, None, 0, ctypes.byref(out_blob)
    )
    if not success:
        raise ctypes.WinError()

    try:
        return ctypes.string_at(out_blob.pbData, out_blob.cbData)
    finally:
        ctypes.windll.kernel32.LocalFree(out_blob.pbData)


# =========================================================
# CONFIG
# =========================================================

def load_email_config():
    """Returns the full config dict, including a decrypted
    "app_password" key (empty string if none has been saved yet)."""

    config = dict(DEFAULT_CONFIG)

    try:
        saved = json.loads(EMAIL_CONFIG_FILE.read_text())
    except Exception:
        saved = {}

    for key in DEFAULT_CONFIG:
        if key in saved:
            config[key] = saved[key]

    config["app_password"] = ""

    encrypted = saved.get("app_password_encrypted")
    if encrypted:
        try:
            config["app_password"] = _dpapi_unprotect(base64.b64decode(encrypted)).decode("utf-8")
        except Exception:
            pass  # corrupted/foreign blob - treat as no password set

    return config


def save_email_config(config, new_app_password=None):
    """Saves settings. `new_app_password`: pass a non-empty string to
    change the stored password, or None/"" to leave whatever password
    is already saved untouched (the UI's password field is always
    shown blank, so "no input" must mean "keep the existing one")."""

    to_save = {key: config[key] for key in DEFAULT_CONFIG}

    try:
        existing_encrypted = json.loads(EMAIL_CONFIG_FILE.read_text()).get("app_password_encrypted")
    except Exception:
        existing_encrypted = None

    if new_app_password:
        encrypted = _dpapi_protect(new_app_password.encode("utf-8"))
        to_save["app_password_encrypted"] = base64.b64encode(encrypted).decode("ascii")
    elif existing_encrypted:
        to_save["app_password_encrypted"] = existing_encrypted

    EMAIL_CONFIG_FILE.write_text(json.dumps(to_save, indent=2))


# =========================================================
# SENDING
# =========================================================

def send_email(config, to_email, subject, html_body):
    message = MIMEMultipart("alternative")
    message["Subject"] = subject
    message["From"] = config["sender_email"]
    message["To"] = to_email
    message.attach(MIMEText(html_body, "html"))

    with smtplib.SMTP(config["smtp_server"], int(config["smtp_port"]), timeout=15) as server:
        server.starttls()
        server.login(config["sender_email"], config["app_password"])
        server.sendmail(config["sender_email"], [to_email], message.as_string())


def send_test_email(config):
    subject = "Company Library - Test Email"
    html_body = """
    <div style="font-family: Segoe UI, Arial, sans-serif; padding:20px;">
        <p>This is a test email from Company Library Management.</p>
        <p>If you received this, reminder emails are configured correctly.</p>
    </div>
    """
    send_email(config, config["sender_email"], subject, html_body)


# =========================================================
# EMAIL CONTENT
# =========================================================

_STAGE_TEXT = {
    "due_soon": (
        "Book Return Reminder",
        "This is a friendly reminder that the book below is due for "
        "return soon.",
    ),
    "stage1": (
        "Overdue Book Notice",
        "The book below is now overdue. Please return it at the "
        "earliest opportunity.",
    ),
    "stage2": (
        "Second Overdue Notice",
        "This is a second reminder that the book below is still "
        "overdue and has not been returned.",
    ),
    "stage3": (
        "Final Overdue Notice",
        "This is a final reminder regarding the overdue book below. "
        "Please return it as soon as possible.",
    ),
}


def build_email(reminder_type, employee_name, book_title, book_id, due_date_display, days_overdue, fine_amount, fine_currency):

    heading, message_line = _STAGE_TEXT[reminder_type]
    subject = f"{heading}: {book_title}"

    detail_rows = f"""
        <tr><td style="padding:6px 0; color:#6b7280;">Book Title</td>
            <td style="padding:6px 0; font-weight:600;">{book_title}</td></tr>
        <tr><td style="padding:6px 0; color:#6b7280;">Book ID</td>
            <td style="padding:6px 0;">{book_id}</td></tr>
        <tr><td style="padding:6px 0; color:#6b7280;">Due Date</td>
            <td style="padding:6px 0;">{due_date_display}</td></tr>
    """

    if reminder_type != "due_soon":
        detail_rows += f"""
        <tr><td style="padding:6px 0; color:#6b7280;">Days Overdue</td>
            <td style="padding:6px 0; color:#dc2626; font-weight:600;">{days_overdue}</td></tr>
        """

    if reminder_type == "stage3" and fine_amount and fine_amount > 0:
        detail_rows += f"""
        <tr><td style="padding:6px 0; color:#dc2626; font-weight:600;">Fine Applicable</td>
            <td style="padding:6px 0; color:#dc2626; font-weight:600;">{fine_currency}{fine_amount:.2f}</td></tr>
        """

    html = f"""
    <html>
    <body style="font-family: 'Segoe UI', Arial, sans-serif; color:#111827; background:#f6f8fb; padding:24px; margin:0;">
      <div style="max-width:560px; margin:0 auto; background:#ffffff; border-radius:12px; padding:32px; border:1px solid #e5e7eb;">
        <div style="font-size:20px; font-weight:700; color:#2563eb; margin-bottom:2px;">📚 Company Library</div>
        <div style="font-size:13px; color:#6b7280; margin-bottom:24px;">Library Management System</div>

        <h2 style="font-size:18px; color:#111827; margin:0 0 16px 0;">{heading}</h2>

        <p style="font-size:14px; line-height:1.6; margin:0 0 12px 0;">Dear {employee_name},</p>
        <p style="font-size:14px; line-height:1.6; margin:0 0 20px 0;">{message_line}</p>

        <table style="width:100%; border-collapse:collapse; font-size:14px; margin-bottom:20px;">
          {detail_rows}
        </table>

        <p style="font-size:14px; line-height:1.6; margin:0 0 24px 0;">
            Please return the book to the Company Library at your earliest convenience.
        </p>

        <p style="font-size:14px; line-height:1.6; color:#6b7280;">
            Regards,<br/>Company Library Management
        </p>
      </div>
    </body>
    </html>
    """

    return subject, html


# =========================================================
# CHECK & SEND
# =========================================================

def check_and_send_reminders(config=None):
    """Looks at every currently-issued book and sends whichever
    reminder stage newly applies, per the configured thresholds.
    Returns a summary dict: {"checked": N, "sent": N, "errors": [...]}.
    Safe to call repeatedly (e.g. once per app launch) - already-sent
    stages are never re-sent."""

    if config is None:
        config = load_email_config()

    summary = {"checked": 0, "sent": 0, "errors": []}

    if not config.get("enabled"):
        return summary

    if not config.get("sender_email") or not config.get("app_password"):
        return summary

    connection = get_connection()
    cursor = connection.cursor()

    cursor.execute("""
        SELECT
            id, employee_name, employee_email, book_id, book_title, due_date,
            reminder_due_soon_sent, reminder_stage1_sent,
            reminder_stage2_sent, reminder_stage3_sent
        FROM issued_books
        WHERE status = 'Issued'
    """)

    rows = cursor.fetchall()
    summary["checked"] = len(rows)

    today = date.today()

    for (
        issue_id, employee_name, employee_email, book_id, book_title, due_date_str,
        due_soon_sent, stage1_sent, stage2_sent, stage3_sent
    ) in rows:

        if not employee_email:
            continue

        due_date_obj = date.fromisoformat(str(due_date_str)[:10])
        days_overdue = (today - due_date_obj).days
        days_remaining = (due_date_obj - today).days

        # Highest applicable, not-yet-sent stage wins - if the app
        # wasn't opened for weeks and a book is already far overdue,
        # this sends the final notice rather than working through
        # every earlier stage retroactively.
        if days_overdue >= config["overdue_stage3_days"] and not stage3_sent:
            reminder_type, column_name = "stage3", "reminder_stage3_sent"
        elif days_overdue >= config["overdue_stage2_days"] and not stage2_sent:
            reminder_type, column_name = "stage2", "reminder_stage2_sent"
        elif days_overdue >= config["overdue_stage1_days"] and not stage1_sent:
            reminder_type, column_name = "stage1", "reminder_stage1_sent"
        elif 0 <= days_remaining <= config["due_soon_days"] and not due_soon_sent:
            reminder_type, column_name = "due_soon", "reminder_due_soon_sent"
        else:
            continue

        fine_amount = 0.0
        if reminder_type == "stage3" and config.get("fine_per_day", 0) > 0:
            fine_amount = config["fine_per_day"] * days_overdue

        subject, html_body = build_email(
            reminder_type,
            employee_name,
            book_title,
            book_id,
            due_date_obj.strftime("%d %b %Y"),
            days_overdue,
            fine_amount,
            config.get("fine_currency", ""),
        )

        try:
            send_email(config, employee_email, subject, html_body)
            cursor.execute(
                f"UPDATE issued_books SET {column_name} = 1 WHERE id = ?",
                (issue_id,)
            )
            connection.commit()
            summary["sent"] += 1
        except Exception as e:
            summary["errors"].append(f"{book_title} -> {employee_email}: {e}")

    connection.close()
    return summary
