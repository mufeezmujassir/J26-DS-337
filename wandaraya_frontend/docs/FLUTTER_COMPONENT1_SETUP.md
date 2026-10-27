# WANDARAYA Component 1 Flutter Setup

## 1. Verify the toolchain

This implementation was validated with Flutter 3.47.7 and Dart 3.13.5.

```powershell
flutter --version
flutter doctor -v
```

Install Android Studio, an Android SDK, platform tools, and accept licenses:

```powershell
flutter doctor --android-licenses
```

## 2. Install dependencies

From `wandaraya_frontend`:

```powershell
flutter pub get
```

## 3. Start the backend stack

The verified backend is the sibling `wandaraya-backend` project and exposes FastAPI on port 8000. Use that repository's existing Compose configuration:

```powershell
Set-Location ..\wandaraya-backend
docker compose up -d postgres redis qdrant
docker compose up -d api
docker compose ps
Invoke-RestMethod http://localhost:8000/health
```

At the time of this handoff, the API container cannot complete its import because `seasonality_scoring.py` imports `ClimateAttractionActivityMapping`, which is unavailable from `app.models.climate`. This is a backend startup blocker, not a Flutter error. The frontend intentionally shows a connection error until the backend team resolves it.

## 4. Research-only configuration

The following backend flags default to `false`. Enable them only in the local research environment; do not enable production reranking.

```dotenv
ENABLE_UNIFIED_CONTEXT_ENGINE=true
ENABLE_UNIFIED_CONTEXT_EXPERIMENTAL_RERANKING=true
ENABLE_UNIFIED_CONTEXT_RESEARCH_API=true
UNIFIED_CONTEXT_RESEARCH_API_TOKEN=<at-least-32-character-local-secret>

ENABLE_LANGGRAPH_RECOMMENDATION_ENGINE=true
ENABLE_LANGGRAPH_RESEARCH_API=true
LANGGRAPH_RESEARCH_API_TOKEN=<at-least-32-character-local-secret>

ENABLE_UNIFIED_CONTEXT_PRODUCTION_RANKING=false
ENABLE_LANGGRAPH_PRODUCTION_ROUTING=false
ENABLE_GROUP_EMOTION_CONTEXT=false
```

Restart the API after changing backend environment values. Never commit either token. In the app, open Settings and enter the token into secure device storage. The UI's Research mode switch changes presentation only and never grants server authorization.

## 5. Run on an Android emulator

Create and start a Pixel-class emulator in Android Studio's Device Manager, then run:

```powershell
Set-Location ..\wandaraya_frontend
flutter devices
flutter run --dart-define=API_BASE_URL=http://10.0.2.2:8000 --dart-define=RESEARCH_OWNER=pp1-local-demo
```

The main Android manifest grants internet access. Cleartext HTTP is enabled only by the debug manifest.

## 6. Run on a physical Android device

Connect the phone and development machine to the same trusted network. Bind FastAPI to `0.0.0.0`, permit port 8000 in the local firewall, and replace the placeholder with the machine's LAN address:

```powershell
flutter run --dart-define=API_BASE_URL=http://<DEVELOPMENT_MACHINE_LAN_IP>:8000 --dart-define=RESEARCH_OWNER=pp1-device-demo
```

Do not hardcode a personal LAN address into source control.

## 7. Desktop and web

```powershell
flutter run -d windows --dart-define=API_BASE_URL=http://localhost:8000
flutter run -d chrome --dart-define=API_BASE_URL=http://localhost:8000
```

Flutter Web additionally requires a narrowly scoped backend CORS origin for the exact development web origin. Review the backend security policy before changing CORS; do not use a broad wildcard for protected research routes.

## 8. Quality checks

```powershell
dart format --output=none --set-exit-if-changed lib test
flutter analyze
flutter test
flutter build apk --debug --dart-define=API_BASE_URL=http://10.0.2.2:8000
```

## 9. Troubleshooting

- **Unable to connect:** verify `/health`, the port, emulator address `10.0.2.2`, and container logs.
- **401:** store the correct runtime research token in Settings.
- **403:** keep a stable `RESEARCH_OWNER`; LangGraph sessions are owner-isolated.
- **503:** verify the research flags, token length, and that the context/LangGraph engines are enabled.
- **422:** check the chosen date/time, district ID, and request fields against the current Pydantic schema.
- **No images:** the verified attraction API has no image URL field. The app uses a deliberate visual fallback instead of unrelated imagery.
- **No activities selector:** the inspected API has no activity-taxonomy listing route. Category interests remain functional; no category-to-activity mapping is invented.

## 10. PP1 sequence

After the backend is healthy: open Discover, run semantic search, submit preferences, inspect ranked evidence, open Research Insights for ranking and pipeline views, then use AI Assistant with an incomplete request to demonstrate clarification. See `COMPONENT1_PP1_DEMO_GUIDE.md` for the controlled sequence.
