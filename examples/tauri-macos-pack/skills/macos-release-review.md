# macOS Release Review

Use this skill before shipping a signed desktop release.

Check:

- app starts from a clean data directory
- packaged app uses isolated local storage
- updater endpoint points to the intended channel
- signing and notarization gates are explicit
- local-only data is not bundled or uploaded
- first-run onboarding works without developer tools installed
