# OmniAgent Mobile

Flutter client for OmniAgent. It talks to the FastAPI backend over REST
(`/api/v1`). Screens fall back to mock data when the backend returns nothing;
login and settings are still placeholders.

## Screens

- Welcome / Login
- Home
- Devices
- Task Execution
- Live Monitoring
- Task Result
- History
- Settings

Bottom tabs: **Home, Devices, History, Settings**. Execution, Live, and
Result open as stack screens.

## Live updates

After login the app keeps one WebSocket open to `/api/v1/events` (`lib/api/events.dart`). The
Home, Devices, History, Execution and Live screens update from it; a task's progress, a new
step screenshot, a PC going offline and a cancel all show up within milliseconds. If the
connection drops it reconnects with growing waits (1s up to 30s), reloads what it missed, and
meanwhile the screens fall back to slow polling. An expired login signs you out.

## Run

```powershell
cd mobile
flutter pub get
flutter run --dart-define=API_BASE=http://10.0.2.2:8000 --dart-define=APP_TOKEN=dev-app-token
```

`10.0.2.2` is the host machine as seen from the Android emulator.

Web:

```powershell
flutter run -d chrome
```
