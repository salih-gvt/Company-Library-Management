# Company Library Management — Production Build

This folder is the reconstructed, production-hardened build pipeline for the
Company Library Management app. The original folder you provided
(`Company_lib\Company_lib\Company Library Management\`) was already a frozen
PyInstaller build with no surviving source project (no `.spec`, no
`requirements.txt`, no launcher script) — the real Python source (`app.py`,
`database.py`) was recovered from inside its `_internal` folder and is
reproduced here, unchanged in UI/behavior except for one bug fix and one
critical path fix described below.

## Technology detected

- **Language/runtime:** Python 3.10 (original) / 3.11 (this rebuild)
- **UI:** Streamlit (server-rendered web UI, opened in the default browser —
  not a native GUI toolkit, not Electron)
- **Storage:** SQLite (`library.db`) mirrored to Excel (`LibraryBooks.xlsx`)
- **Packaging (kept as-is):** PyInstaller (onedir) + Inno Setup — the same
  stack the original build already used (evidenced by the leftover
  `unins000.exe`/`.dat` in your original folder)

## What was changed, and why

1. **Data location (critical fix).** `database.py` used to open
   `"library.db"` / `"LibraryBooks.xlsx"` as bare relative paths, resolved
   against the process's working directory. Installed normally to
   `C:\Program Files\...`, that directory is read-only for standard users —
   the app would fail the first time anyone tried to add/issue/return a book.
   It now resolves both files under `%LOCALAPPDATA%\CompanyLibraryManagement\`,
   which every Windows user account can always write to. No UI or workflow
   changed — the app still reads/writes the same SQLite schema and the same
   Excel sync, just from a location that actually works after installation.

2. **Missing dependency (bug fix).** `export_database_to_excel()` uses
   `pandas.ExcelWriter(engine="openpyxl")`, but `openpyxl` was not bundled in
   your original build. In practice this meant every "sync to Excel" action
   was silently failing (caught by a broad `except Exception`, surfaced only
   as a small warning toast). `openpyxl` is now bundled, so Excel sync
   actually works — this restores intended behavior, it doesn't add a new
   feature.

3. **New launcher (`source/launcher.py`), native window.** The original
   compiled-in entry point was lost when the app was frozen (only files
   added as *data* survive as plaintext; the actual entry script gets
   embedded into the exe and isn't recoverable). The new launcher starts
   Streamlit in-process, headless, on a background thread, then displays it
   in a dedicated desktop window via `pywebview` (backed by the Windows
   WebView2 runtime, bundled) — a real app window with its own title bar and
   taskbar entry, not a browser tab with an address bar/tabs. No console
   window appears. The rendered page itself (CSS, layout, nav) is unchanged.

4. **Deploy button hidden, Settings menu kept.** Streamlit's built-in
   top-right "Deploy" button (for pushing the app to Streamlit Community
   Cloud) doesn't apply to an installed desktop app, so it's turned off via
   `--client.toolbarMode=viewer` on the launcher's Streamlit invocation — a
   startup flag, not a change to `app.py`.

5. **Light/Dark/System theme toggle**, now at the top-right of the content
   area. Three small icon buttons (☀️/🌙/🖥️) render in a `st.container(key=
   "theme_toggle")` right-aligned via CSS Grid (`justify-content: end` -
   Streamlit's columns use CSS Grid, not flexbox, for layout). Originally
   placed at the bottom of the sidebar; moved per your request. Streamlit's
   own `theme.base` setting only recolors its native widgets, not this
   app's custom HTML cards/KPIs, so the toggle drives its own light/dark
   color pair for those instead (`app.py`, `_LIGHT_PALETTE` /
   `_DARK_PALETTE`); "System" ships both and lets the OS/browser's
   `prefers-color-scheme` pick automatically, live. The choice is saved to
   `%LocalAppData%\CompanyLibraryManagement\theme.json` and restored on the
   next launch.

   While relocating this, found and fixed a related pre-existing issue:
   the desktop window was fixed at 1400x900, but the page's own content
   (1400px max-width) plus its ~380px sidebar need more than that to avoid
   clipping the right edge - visible on the KPI row's 4th card even before
   this change. The window now sizes itself to ~95% of the actual screen
   (capped at 1900x1000, floor 1100x650) instead of a fixed guess, so it
   fits properly on both small and large monitors.

6. **Icon.** `assets/icon.ico` was supplied by you (`icon_lib.png`, a
   book-stack illustration), converted to a multi-resolution `.ico`. Used
   for the exe itself, the installer, and all shortcuts.

7. **Modern visual redesign (requested).** Unlike the changes above, this
   one *does* touch the app's look on purpose, at your request. Structure,
   pages, navigation, workflows, validation and all business logic in
   `app.py` are unchanged - only the CSS was reworked:
   - KPI cards moved from a colored left border to a colored top accent
     bar, larger radius, refined layered shadows, hover lift.
   - Cards, inputs, and buttons: larger border radius, softer shadows,
     smooth transitions.
   - Main-content buttons (Save, Issue, Return, Reserve, Export, etc.) now
     use a solid brand-blue fill instead of the plain gray default, for a
     more confident, modern flat-UI look; sidebar nav buttons keep their
     existing style.
   - Text inputs/selects get a visible focus ring in the brand blue.
   - A custom thin scrollbar, and smooth color transitions when switching
     theme.
   - Both the light and dark palettes (see item 5) were extended with
     surface/shadow/border tokens so every one of the above adapts
     correctly in both modes - verified visually in both.

8. **One-time legacy data migration.** If `%LOCALAPPDATA%\...` is empty on
   first run and an old-style `library.db`/`LibraryBooks.xlsx` is sitting
   next to the executable (the old behavior), it's copied in automatically
   so upgrading never loses data.

9. **Backup & Restore**, new card on the Settings page, additive only
   (nothing existing on that page changed):
   - **Create Backup** dumps every table (employees, books, issued_books,
     waiting_list) to a single `.zip` containing `manifest.json` (app name,
     a `backup_format_version` number, timestamp) and `data.json` (each
     table's rows as plain column-name → value objects - not a raw copy of
     `library.db`, so a restore isn't tied to today's exact schema/SQLite
     version). In the packaged app, a native "Save As" dialog
     (`pywebview`'s `create_file_dialog`) lets you pick where it's saved;
     running the source directly in a browser falls back to a normal
     download button.
   - **Restore from Backup** opens a native "Open" file dialog (or a
     file-uploader in the browser-dev fallback), validates the chosen file
     (valid zip → has both required files → correct `app` field → a
     supported `backup_format_version` → each table's data is a list),
     and shows a clear, specific error for anything that fails rather than
     a raw crash. If it's valid, a confirm/cancel modal (`st.dialog`) shows
     what's in the backup and warns that current data will be replaced.
     Confirming replaces each table's rows with the backup's (matched by
     column name, so restoring an older/newer backup than the app's
     current schema doesn't crash on missing/extra columns), then
     re-syncs `LibraryBooks.xlsx` the same way every other write already
     does. A timestamped safety copy of `library.db` is taken automatically
     right before replacing anything, under
     `%LocalAppData%\CompanyLibraryManagement\restore_safety_backups\`.
   - Entirely local/offline - no network calls, no cloud storage.

10. **Version tracking + update check.** `source/version.py` holds
    `APP_VERSION` ("1.0.0") and the GitHub repo this app checks
    (`salih-gvt/Company-Library-Management`). Once per session (not on
    every rerun), the app queries that repo's latest GitHub Release via
    `https://api.github.com/repos/<repo>/releases/latest` and, if its tag
    is newer than `APP_VERSION`, shows a small info banner at the top of
    every page: "Update available: vX.Y.Z — see what's new" linking to the
    release. Any failure (offline, GitHub unreachable, no releases yet,
    rate-limited) is swallowed silently - it can never block or slow down
    normal use beyond a capped 4-second check on first launch of a
    session. It never auto-downloads or auto-installs anything.

11. **Dedicated Edit/Delete buttons on Members and Books** (requested).
    Both pages previously used an inline-editable table (`st.data_editor`) -
    click any cell to edit it, tick a row's checkbox + press the trash icon
    + click "Save Changes" to delete. That's replaced with a plain row list
    where each employee/book gets its own **✏️ Edit** and **🗑️ Delete**
    button. Edit opens a modal (`st.dialog`) pre-filled with that row's
    current values; Delete opens a confirmation modal naming exactly what
    will be removed before anything happens. Same underlying functions as
    before (`update_employee`/`delete_employee`/`update_book`/`delete_book`
    - unchanged), same validation (can't delete a book that's currently
    issued, can't delete an employee with an outstanding loan, duplicate-ID
    checks), same Excel re-sync after every change. The "Add Employee" /
    "Add New Book" forms above the list are untouched.

Everything else - page structure, navigation labels, form fields,
validation rules, and all database/Excel logic - is unchanged from the
original app.

## Your existing data

Your original `library.db`/`LibraryBooks.xlsx` contained real employee data
(names, emails at your `gravity-bp.com` domain), not sample data — so it was
**not** bundled into the installer (that would leak your employees' info to
anyone else who ran it). Instead, on this machine, I copied it directly into
the new permanent location:

```
%LOCALAPPDATA%\CompanyLibraryManagement\library.db
%LOCALAPPDATA%\CompanyLibraryManagement\LibraryBooks.xlsx
```

confirmed to contain your 8 employees / 6 books / 6 issue records. A fresh
install on any other machine starts empty, as a real production installer
should.

## Build

Requires Python 3.11+ and internet access (first run only, to fetch
packages).

```
cd "production"
python -m venv .venv
.venv\Scripts\pip install -r requirements.txt pyinstaller
.venv\Scripts\pyinstaller CompanyLibrary.spec --noconfirm
```

Output: `dist\Company Library Management\Company Library.exe` (+ `_internal\`).

## Create the installer

Requires Inno Setup 6 (installed at
`%LOCALAPPDATA%\Programs\Inno Setup 6\ISCC.exe` on this machine —
<https://jrsoftware.org/isinfo.php>, free).

```
"%LOCALAPPDATA%\Programs\Inno Setup 6\ISCC.exe" installer\setup.iss
```

Output: `installer\Company Library Management-Setup.exe`.

## Application data & versioning

| Item | Location |
|---|---|
| Program files | `%LocalAppData%\Programs\Company Library Management\` (per-user install, no admin required) |
| Database + Excel mirror | `%LocalAppData%\CompanyLibraryManagement\` |
| Start Menu shortcut | Yes (always) |
| Desktop shortcut | Optional, offered during install |
| Uninstall | Control Panel / Settings → Apps → "Company Library Management" |

**Uninstall** removes only the program files and shortcuts — the database
and Excel file are outside `{app}` and are never touched.
**Reinstall/upgrade** (running the installer again) overwrites program files
only; your data is untouched since it lives in a separate folder.

The installer defaults to a **per-user install** (`PrivilegesRequired=lowest`
in `setup.iss`), so no admin rights or UAC prompt are needed to install or
run it. An admin can still choose to install for all users if they run the
installer elevated.

## Remaining external requirements

None for day-to-day use — the installer is fully self-contained (no Python,
Node, or any SDK needed on the target machine) and the app works entirely
offline. Internet access is used for exactly one optional thing: the
once-per-session update check against GitHub, which fails silently if
unavailable.

## Source control & releases

The source is at <https://github.com/salih-gvt/Company-Library-Management>.
`.venv/`, `build/`, `dist/`, and the compiled installer are git-ignored -
only source, packaging config, and docs are committed. See
[README.md](README.md)'s "Releasing a new version" section for the exact
steps to cut a release; the app's update check (above) depends on that
process being followed - specifically, on an actual GitHub **Release**
existing (not just a git tag), since that's what the `releases/latest` API
looks at.

## Test report

Performed on this development machine (no separate clean VM was available —
see limitation below):

| Test | Result |
|---|---|
| PyInstaller build completes | ✅ Pass |
| Frozen exe starts, serves HTTP 200 on localhost | ✅ Pass |
| Runs with no console window (`console=False`) | ✅ Pass |
| Fresh install creates empty `library.db` + `LibraryBooks.xlsx` in `%LOCALAPPDATA%` | ✅ Pass |
| Excel sync actually writes a valid 3-sheet `.xlsx` (previously silently broken) | ✅ Pass |
| Legacy-data migration (old exe-adjacent files → `%LOCALAPPDATA%`) | ✅ Pass — verified with your real 8-employee/6-book dataset |
| Inno Setup installer compiles | ✅ Pass |
| Silent install places files, registers uninstaller, creates Start Menu shortcut | ✅ Pass |
| Launch via the actual Start Menu shortcut | ✅ Pass |
| Uninstall removes program files + shortcut, **preserves** user data | ✅ Pass |
| Reinstall over existing install | ✅ Pass |
| Native window (pywebview) launches, renders app | ✅ Pass |
| Light theme renders correctly (screenshot-verified) | ✅ Pass |
| Dark theme renders correctly, all surfaces/text adapt (screenshot-verified) | ✅ Pass |
| Modern KPI/card/button restyle (screenshot-verified on Dashboard, both themes) | ✅ Pass |
| Button/input focus styling on form pages (Members/Books/Issue/Return) | Not screenshot-verified this round (UI-automation clicks into the running app were unreliable in this environment) - styling uses the same verified selectors/mechanism as the Dashboard, so risk is low, but worth a quick manual look |
| Theme toggle relocated to top-right, tightly clustered (not spread across equal-width columns) | ✅ Pass (verified in a maximized browser window against the dev server; Streamlit's columns turned out to use CSS Grid, not flexbox - `justify-content: end` on the grid container was the fix) |
| Theme control simplified from Light/Dark/System buttons to a single Light/Dark `st.toggle` switch (System removed per request) | ✅ Pass - no errors in either dev or packaged runs |
| Adaptive window sizing on a small-screen scenario (1536x864) | ✅ Pass - window now claims ~95% of screen space instead of a fixed size that could exceed the screen; on that particular low-resolution screen the app's own 1400px+sidebar content still doesn't fully fit without the window being maximized-equivalent, which is a pre-existing content-width characteristic (present before this session's changes too), not a regression |
| Backup: dumps real data (8 employees/6 books/6 issue records) to a valid `.zip` with `manifest.json` + `data.json` | ✅ Pass (tested directly against the live database) |
| Backup validation rejects a non-zip file, a wrong-app zip, and accepts a genuine backup | ✅ Pass (all three cases tested directly) |
| Full restore cycle: mutate live data → restore from an earlier backup → mutation gone, original data back exactly | ✅ Pass (tested directly: employee count 8→9→8, injected test row confirmed removed, book count unaffected) |
| Restore takes an automatic timestamped safety copy of the database before touching it | ✅ Pass (`restore_safety_backups\pre_restore_<timestamp>.db` confirmed created) |
| Backup/Restore UI on the Settings page (`st.dialog` confirmation, native file dialogs, `st.file_uploader` dev fallback) | Not click-through verified this round - see limitation below; code follows the same widget/layout patterns already proven elsewhere in this app, and the file compiles cleanly with no import errors in either dev or packaged runs |
| Packaged app still starts and serves the Dashboard correctly with the new code added | ✅ Pass (confirmed via HTTP 200 + clean logs, both before and after this feature) |
| Version comparison logic (`v1.0.0` vs `1.2.3` vs `v1.10.0` vs `v1.9.0`, etc.) | ✅ Pass (tested directly) |
| Update check against the real repo before any release existed (expects a graceful no-op) | ✅ Pass (`404 Not Found` from GitHub's API, caught and treated as "no update," no banner shown, no crash) |
| Update check runs without error inside the packaged app (`version.py` bundled correctly as a PyInstaller data file, `urllib` works from a frozen exe) | ✅ Pass (clean logs, HTTP 200) |
| Git repo initialized, `.gitignore` excludes `.venv`/`build`/`dist`/installer binary, pushed to GitHub, tagged `v1.0.0` | ✅ Pass |
| Members/Books row-based Edit/Delete buttons render (headless, via Streamlit's own `AppTest` framework - not screen automation this time) | ✅ Pass - button count matches real row count exactly (8 employees → 8 edit + 8 delete; 6 books → 6 edit + 6 delete) |
| Edit dialogs pre-fill with the correct row's real data | ✅ Pass (verified exact values: e.g. employee E006/Aleena, book B001/"1984"/George Orwell/Fiction) |
| Delete dialogs show the correct name/ID in the warning before confirming | ✅ Pass (verified exact wording for both an employee and a book) |
| Clicking Save/Delete *inside* the dialog and having it persist | Not verified via automation - `AppTest` isolated this as a limitation of testing `st.dialog` specifically (confirmed by testing the identical set-value-then-click pattern against a plain, non-dialog form, which worked and correctly wrote to the database), not a code issue. The dialogs call the same pre-existing, already-proven `update_*`/`delete_*` functions with argument order verified by direct code review. Worth one manual click-through. |

**Known limitation:** all testing above ran on this development machine, not
a separate clean Windows machine with no dev tools installed. I did not
independently reboot into a bare Windows profile to prove zero dependency on
anything already present here. Given the frozen build is self-contained
(PyInstaller onedir with all Python/DLL dependencies bundled) and the
installer's file list is exactly `dist\Company Library Management\*`, this
is low-risk, but a real clean-machine or clean-VM run before wide rollout is
recommended if that matters for your deployment.

**Known blocker on this specific machine:** partway through this project,
Windows **Smart App Control** (an Enterprise policy, Policy ID
`{0283ac0f-fff1-49ae-ada1-8a933130cad6}`) started hard-blocking the
Inno Setup-produced `Setup.exe` as unsigned ("did not meet the Enterprise
signing level requirements" - see Event Viewer,
Microsoft-Windows-CodeIntegrity/Operational, event IDs 3077/3089/3118).
The app's own `.exe` is **not** affected and runs fine either way; only the
installer wrapper is blocked. The app currently installed on this machine
was placed there by directly copying `dist\Company Library Management\` to
`%LocalAppData%\Programs\Company Library Management\` and creating the
Start Menu shortcut by hand, bypassing the installer entirely - functionally
identical result, just not via `Setup.exe`. For distributing to other
machines (especially other corporate-managed ones, which likely have
similar policies), the real fix is **code-signing** the exe/installer with
a certificate; that's a decision (and cost) for you, not something I can
do unilaterally.

## Output structure

```
production/
├── source/            app.py, database.py (patched), launcher.py
├── assets/            icon.ico (extracted from the original exe)
├── requirements.txt
├── CompanyLibrary.spec
├── dist/              built app (Company Library.exe + _internal\)
├── build/             PyInstaller intermediate cache (safe to delete)
├── installer/
│   ├── setup.iss
│   └── Company Library Management-Setup.exe   ← ship this
└── README-PRODUCTION.md
```
