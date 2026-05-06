# macOS Release Checklist

- Build frontend assets.
- Build native sidecar.
- Build `.app`.
- Sign sidecar and app.
- Notarize release artifact.
- Build DMG with `/Applications` link.
- Mount read-only and smoke launch.
- Verify updater metadata.
- Verify no user DB, chats, logs, or local paths are bundled.
