# Single source of truth for the app's version, used both to display it
# and to compare against GitHub's latest release when checking for
# updates. Bump this (and installer/setup.iss's MyAppVersion, kept in
# sync manually) as part of cutting each release - see
# README-PRODUCTION.md's release process.

APP_VERSION = "1.0.0"

# owner/repo on GitHub the update check looks at for new releases.
GITHUB_REPO = "salih-gvt/Company-Library-Management"
