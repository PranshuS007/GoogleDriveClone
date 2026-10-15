"""FastAPI backend for GoogleDriveClone (sample, no frontend).

Endpoints:
    GET    /health
    POST   /folders              create a folder
    GET    /folders/{id}/contents  list items inside a folder
    POST   /files                upload a file (multipart)
    GET    /files/{id}           download a file
    GET    /files/{id}/metadata  file metadata
    GET    /drive                list the whole drive (optional ?parent_id=)
    PATCH  /items/{id}/move      move an item      {"parent_id": "..."}
    GET    /search?q=...         search by name
    DELETE /items/{id}           delete an item
"""

from __future__ import annotations

from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from pathlib import Path
from typing import Optional
from pydantic import BaseModel

from app.drive_store import DriveItem, DriveStore


def _store_path() -> Path:
    # `uploads` lives next to the backend package so the app works when
    # started from this directory; tests override this via dependency.
    return Path(__file__).resolve().parent.parent / "uploads"


store = DriveStore(_store_path())

app = FastAPI(title="GoogleDriveClone API", version="0.1.0")

# allow tests to swap the store for an isolated temp one
def get_store() -> DriveStore:
    return store


app.dependency_overrides = {}


class CreateFolderRequest(BaseModel):
    name: str
    parent_id: Optional[str] = None


class MoveRequest(BaseModel):
    parent_id: Optional[str] = None


@app.get("/health")
def health() -> dict:
    """Health check endpoint."""
    return {"status": "ok", "service": "googledriveclone-backend"}


@app.post("/folders", status_code=201)
def create_folder(request: CreateFolderRequest) -> DriveItem:
    try:
        return get_store().create_folder(request.name, request.parent_id)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.get("/folders/{folder_id}/contents")
def folder_contents(folder_id: str) -> list[DriveItem]:
    folder = get_store().get(folder_id)
    if folder is None or folder.kind != "folder":
        raise HTTPException(status_code=404, detail="Folder not found")
    return get_store().list_items(folder_id)


@app.post("/files", status_code=201)
async def upload_file(
    file: UploadFile = File(...),
    parent_id: Optional[str] = Form(None),
) -> DriveItem:
    content = await file.read()
    try:
        return get_store().save_file(file.filename or "unnamed", content, parent_id)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.get("/files/{file_id}")
def download_file(file_id: str):
    try:
        from fastapi.responses import Response

        content = get_store().read_file(file_id)
    except KeyError:
        raise HTTPException(status_code=404, detail="File not found")
    item = get_store().get(file_id)
    return Response(content, media_type="application/octet-stream",
                    headers={"Content-Disposition": f'attachment; filename="{item.name}"'})


@app.get("/files/{file_id}/metadata")
def file_metadata(file_id: str) -> DriveItem:
    item = get_store().get(file_id)
    if item is None or item.kind != "file":
        raise HTTPException(status_code=404, detail="File not found")
    return item


@app.get("/drive")
def list_drive(parent_id: Optional[str] = None) -> list[DriveItem]:
    if parent_id is not None and get_store().get(parent_id) is None:
        raise HTTPException(status_code=404, detail="Folder not found")
    return get_store().list_items(parent_id)


@app.patch("/items/{item_id}/move")
def move_item(item_id: str, request: MoveRequest) -> DriveItem:
    try:
        return get_store().move_item(item_id, request.parent_id)
    except KeyError:
        raise HTTPException(status_code=404, detail="Item not found")
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.get("/search")
def search(q: str) -> list[DriveItem]:
    return get_store().search(q)


@app.delete("/items/{item_id}", status_code=204)
def delete_item(item_id: str):
    if not get_store().delete_item(item_id):
        raise HTTPException(status_code=404, detail="Item not found")
