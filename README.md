# Company Library Management

A desktop app for managing a company's internal book library — issuing and
returning books, tracking employees, reservations, and due dates.

Runs as a normal Windows desktop app (its own window, Start Menu entry,
installer) with **no external services, no cloud storage, and no internet
requirement** for day-to-day use. Data is stored locally in SQLite, mirrored
to an Excel file for easy sharing/reporting.

## Features

- Dashboard with live KPIs (books, availability, overdue/due-today)
- Issue / return books, with condition tracking on return
- Employee (member) management
- Book reservations / waiting list for issued books
- Search and track issue/return history
- CSV export of any table; full Excel mirror of the database
- Local backup & restore (Settings page) — export all data to a single
  file, restore it later with validation and a confirmation step
- Light / Dark theme toggle
- Update check on launch (see below)

## Technology

- **Language:** Python
- **UI:** [Streamlit](https://streamlit.io) (server-rendered), displayed in
  a native desktop window via [pywebview](https://pywebview.flowrl.com/)
  (Windows WebView2)
- **Storage:** SQLite (`library.db`) + an Excel mirror (`LibraryBooks.xlsx`),
  both under `%LocalAppData%\CompanyLibraryManagement\`
- **Packaging:** PyInstaller + Inno Setup

## Running from source

```
python -m venv .venv
.venv\Scripts\pip install -r requirements.txt
.venv\Scripts\streamlit run source\app.py
```

## Building the installer

See [README-PRODUCTION.md](README-PRODUCTION.md) for the full build,
packaging, and release process, plus a detailed log of production-hardening
decisions made along the way.

## Releasing a new version

1. Bump `APP_VERSION` in `source/version.py` and `MyAppVersion` in
   `installer/setup.iss` to match.
2. Rebuild (`README-PRODUCTION.md` has the exact commands) and smoke-test.
3. Commit, tag the commit `vX.Y.Z`, push both:
   ```
   git tag vX.Y.Z
   git push origin main --tags
   ```
4. Create a GitHub Release from that tag (Releases → Draft a new release),
   attaching the built `Setup.exe` as a release asset.

Once published, running copies of the app check this repo's latest release
on launch and show a small in-app notice if a newer version is available
(never auto-downloads or auto-installs — just links to the release).
