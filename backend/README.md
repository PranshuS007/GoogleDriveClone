# GoogleDriveClone — backend (sample)

A sample Python backend for a Google Drive clone. **No frontend** — just the API.

## Stack

- **FastAPI** + **Uvicorn** (async API server, auto-generated docs at `/docs`)
- **Pydantic v2** (request/response models)
- File bytes stored on disk under `backend/uploads/`; folder structure
  and file metadata tracked in memory (a `DriveStore`)

## Run

```bash
cd backend
python -m venv .venv                 # first time only
.venv/Scripts/python -m pip install -r requirements.txt   # Windows
.venv/Scripts/python -m uvicorn app.main:app --reload --port 8000
```

Then open <http://127.0.0.1:8000/docs> for the interactive API docs.

## Test

```bash
cd backend
.venv/Scripts/python -m pytest -q
```

## Endpoints

| Method | Path                          | Description                        |
|--------|-------------------------------|------------------------------------|
| GET    | `/health`                     | Health check                       |
| POST   | `/folders`                    | Create a folder `{name, parent_id?}` |
| GET    | `/folders/{id}/contents`      | List items inside a folder         |
| POST   | `/files`                      | Upload a file (multipart, `parent_id?`) |
| GET    | `/files/{id}`                 | Download a file                    |
| GET    | `/files/{id}/metadata`        | File metadata                      |
| GET    | `/drive`                      | List drive (optional `?parent_id=`) |
| PATCH  | `/items/{id}/move`            | Move an item `{parent_id}`         |
| GET    | `/search?q=...`               | Search by name (case-insensitive)  |
| DELETE | `/items/{id}`                 | Delete a file or folder (recursive)|

## Layout

```
backend/
├── app/
│   ├── main.py          # FastAPI routes
│   └── drive_store.py   # in-memory DriveStore + on-disk file blobs
├── tests/
│   └── test_drive.py    # 13 API tests (TestClient, temp dir)
├── uploads/             # created at runtime (gitignored)
├── requirements.txt
└── pytest.ini
```
