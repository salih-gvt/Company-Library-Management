import sys
import os

# In a windowed (console-less) Windows build, sys.stdout/sys.stderr are
# None. Any library call that does print()/logging before this is fixed
# will crash the whole app with "'NoneType' object has no attribute
# 'write'" - so this must happen before anything else is imported.
if sys.stdout is None:
    sys.stdout = open(os.devnull, "w")
if sys.stderr is None:
    sys.stderr = open(os.devnull, "w")

import socket
import threading
import time
from pathlib import Path

PORT = 8501
URL = f"http://localhost:{PORT}"


def _bundle_dir() -> Path:
    """Folder holding the bundled app files (app.py, database.py) -
    PyInstaller's extraction folder when frozen, this folder otherwise."""
    if getattr(sys, "frozen", False):
        return Path(getattr(sys, "_MEIPASS", Path(sys.executable).parent))
    return Path(__file__).resolve().parent


def _port_is_open(port: int) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        return sock.connect_ex(("127.0.0.1", port)) == 0


def _run_streamlit(app_path: str):
    sys.argv = [
        "streamlit",
        "run",
        app_path,
        "--global.developmentMode=false",
        f"--server.port={PORT}",
        "--server.headless=true",
        "--server.fileWatcherType=none",
        "--browser.gatherUsageStats=false",
        # This is an installed desktop app, not a hosted Streamlit site -
        # the whole hamburger menu (Deploy, Print, Record screen, its
        # own Light/Dark/System picker, "Made with Streamlit") is
        # dev-site chrome that doesn't apply here and can't be trimmed
        # item-by-item, only shown or hidden as a whole. The app has its
        # own working Light/Dark/System toggle in the sidebar already
        # (this native one only recolors Streamlit's own widgets, not
        # this app's cards), so hiding it entirely is strictly better.
        "--client.toolbarMode=minimal",
    ]

    from streamlit.web import cli as stcli
    from streamlit.web import bootstrap as st_bootstrap

    # bootstrap normally installs SIGINT/SIGTERM handlers, which only
    # works on the main thread - this runs on a worker thread since the
    # main thread is reserved for the desktop window's message loop.
    # The app's lifecycle is controlled by that window closing instead.
    st_bootstrap._set_up_signal_handler = lambda *a, **kw: None

    stcli.main()


def _run_reminder_check_only():
    """Headless path for the daily Scheduled Task: just check due dates
    and send whatever reminder emails are due, then exit - no window,
    no Streamlit server. Lets the reminder feature run once a day
    whether or not anyone has the app open (see setup.iss, which
    registers the scheduled task pointing back at this same exe with
    --check-reminders-only)."""

    bundle_dir = _bundle_dir()
    sys.path.insert(0, str(bundle_dir))

    try:
        import database
        database.create_tables()

        import email_reminders
        email_reminders.check_and_send_reminders()
    except Exception:
        pass  # scheduled/unattended run - nothing to surface this to


def main():
    if "--check-reminders-only" in sys.argv:
        _run_reminder_check_only()
        return

    bundle_dir = _bundle_dir()
    app_path = str(bundle_dir / "app.py")

    # Lets app.py's `from database import ...` resolve.
    sys.path.insert(0, str(bundle_dir))

    if not _port_is_open(PORT):
        # Streamlit's server blocks on its own event loop, so it needs
        # its own thread - the main thread is reserved for the desktop
        # window's message loop (required on Windows).
        threading.Thread(
            target=_run_streamlit,
            args=(app_path,),
            daemon=True,
        ).start()

        # Wait for the server to actually be up instead of guessing a
        # fixed delay before pointing the window at it.
        for _ in range(150):
            if _port_is_open(PORT):
                break
            time.sleep(0.1)

    import webview

    # The page content area is capped at 1400px wide (see app.py's
    # .block-container) plus the ~380px sidebar next to it, so the
    # window needs to be wide to avoid clipping the right edge of
    # every page - but a fixed size that assumes a large monitor would
    # itself get clipped by Windows on a smaller screen. Size relative
    # to the actual screen instead, so it fits either way.
    try:
        screen = webview.screens[0]
        win_width = max(1100, min(1900, int(screen.width * 0.95)))
        win_height = max(650, min(1000, int(screen.height * 0.9)))
    except Exception:
        win_width, win_height = 1400, 900

    webview.create_window(
        "Company Library Management",
        URL,
        width=win_width,
        height=win_height,
        min_size=(1100, 650),
    )
    webview.start()

    # The window is this process's only reason to exist - once it's
    # closed, drop the (daemon) server thread along with the process.
    os._exit(0)


if __name__ == "__main__":
    main()
