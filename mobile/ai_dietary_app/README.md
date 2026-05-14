# ai_dietary_app

Flutter mobile app for the AI Dietary System.

## Required tools

- Flutter SDK installed and configured
- A connected device or emulator
- Python 3.10+ for backend setup

## Setup

From the repository root:

```bash
cd /Ai-Dietary-System
```

1. Create and activate the backend Python virtual environment:

```bash
python3 -m venv .venv
source .venv/bin/activate
```

2. Install Python dependencies:

```bash
pip install --upgrade pip
pip install -r requirements.txt
```


3. Seed the backend database if needed:

```bash
python backend/seed_food.py
```

## Run the backend

```bash
cd backend
uvicorn main:app --reload --host 0.0.0.0 --port 8000
```

## Update the mobile host URL

The Flutter app uses `mobile/ai_dietary_app/lib/main.dart` and the `kBaseUrl` constant.
If the app is pointing to the hosted backend, update it for local testing:

```dart
const String kBaseUrl = 'http://127.0.0.1:8000';
```

If you use an Android emulator, use `http://10.0.2.2:8000` instead.
On a physical device, use your computer IP address on the same network.

## Run the Flutter app

```bash
cd mobile/ai_dietary_app
flutter pub get
flutter run
```

If you want to target a specific device:

```bash
flutter devices
flutter run -d <device_id>
```

## Notes

- Start the backend before launching the mobile app.
- The backend entrypoint is `backend/main.py`.
- The Flutter entrypoint is `mobile/ai_dietary_app/lib/main.dart`.
- The backend does not seed automatically, run `python backend/seed_food.py` manually.
