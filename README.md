# AI Dietary System

## Overview

This repository contains:
- `backend/` — Python FastAPI backend for food recognition, nutrition lookup, and model inference.
- `mobile/ai_dietary_app/` — Flutter mobile app for interacting with the backend.
- `models/last.pt` — trained YOLO model used by the backend.
- `requirements.txt` — Python dependency list for the backend.

## Prerequisites

### Required tools
- Python 3.10 or newer
- `pip` package manager
- `virtualenv` support (built into Python)
- Flutter SDK installed and configured
- Device or emulator available for Flutter
- Git (optional, if cloning the repo)

## Setup

### 1) Create a Python virtual environment

From the repository root:

```bash
cd /Ai-Dietary-System
python3 -m venv .venv
source .venv/bin/activate
```

> If `python3` is not available, use `python` or the full path to your Python 3 installation.

### 2) Install Python requirements

```bash
pip install --upgrade pip
pip install -r requirements.txt
```

### 3) Prepare the model file

The backend expects the YOLO model at `backend/models/last.pt`.
If that file is missing, copy it from the repo root:

```bash
mkdir -p backend/models
cp models/last.pt backend/models/last.pt
```

### 4) Seed the database

The database seed script is in `backend/seed_food.py`.
Run it once before starting the backend, or if seed data is missing:

```bash
python backend/seed_food.py
```

This creates or updates the local SQLite database and inserts the default food entries.

## Running the backend

From the repository root:

```bash
cd backend
uvicorn main:app --reload --host 0.0.0.0 --port 8000
```

Then open:

- `http://127.0.0.1:8000`
- `http://127.0.0.1:8000/docs` for FastAPI interactive docs

### Local hosting note

If you run the backend locally, update the mobile app base URL in `mobile/ai_dietary_app/lib/main.dart`.
The current value is:

```dart
const String kBaseUrl = 'https://jfantra-ai-dietary-backend.hf.space';
```

For local testing, change it to your backend URL, for example:

```dart
const String kBaseUrl = 'http://127.0.0.1:8000';
```

If you use an Android emulator, you may need `http://10.0.2.2:8000`.
If you use a physical device, use your machine IP on the same network, e.g. `http://192.168.1.100:8000`.

## Running the mobile app

From the Flutter app folder:

```bash
cd mobile/ai_dietary_app
flutter pub get
flutter run
```

If you need a specific device:

```bash
flutter devices
flutter run -d <device_id>
```

## Notes

- Start the backend before starting the mobile app.
- The backend entrypoint is `backend/main.py`.
- The Flutter entrypoint is `mobile/ai_dietary_app/lib/main.dart`.
- If the backend fails to seed automatically, run `python backend/seed_food.py` manually.
