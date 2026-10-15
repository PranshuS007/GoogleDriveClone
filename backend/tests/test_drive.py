"""End-to-end API tests for the GoogleDriveClone backend.

Uses FastAPI's TestClient against a DriveStore rooted in a temp dir,
so nothing touches real disk outside the tmp path.
"""

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.drive_store import DriveStore
from app import main as app_module


@pytest.fixture()
def client(tmp_path: Path):
    test_store = DriveStore(tmp_path / "drive")
    app_module.store = test_store
    app_module.app.dependency_overrides.clear()
    with TestClient(app_module.app) as c:
        yield c


def test_health(client):
    resp = client.get("/health")
    assert resp.status_code == 200
    assert resp.json()["status"] == "ok"


def test_create_folder_and_list_contents(client):
    folder = client.post("/folders", json={"name": "Docs"}).json()
    assert folder["kind"] == "folder"
    assert folder["name"] == "Docs"
    assert folder["parent_id"] is None

    contents = client.get("/folders/{}/contents".format(folder["id"])).json()
    assert contents == []


def test_create_nested_folder(client):
    parent = client.post("/folders", json={"name": "A"}).json()
    child = client.post("/folders", json={"name": "B", "parent_id": parent["id"]}).json()
    assert child["parent_id"] == parent["id"]

    contents = client.get("/folders/{}/contents".format(parent["id"])).json()
    assert [c["id"] for c in contents] == [child["id"]]


def test_create_folder_empty_name_returns_400(client):
    resp = client.post("/folders", json={"name": "   "})
    assert resp.status_code == 400


def test_upload_download_delete_roundtrip(client):
    resp = client.post(
        "/files",
        files={"file": ("hello.txt", b"hello world", "text/plain")},
    )
    assert resp.status_code == 201
    meta = resp.json()
    assert meta["kind"] == "file"
    assert meta["name"] == "hello.txt"
    assert meta["size"] == 11

    dl = client.get("/files/{}".format(meta["id"]))
    assert dl.status_code == 200
    assert dl.content == b"hello world"

    metadata = client.get("/files/{}/metadata".format(meta["id"])).json()
    assert metadata["name"] == "hello.txt"

    resp = client.delete("/items/{}".format(meta["id"]))
    assert resp.status_code == 204
    assert client.get("/files/{}".format(meta["id"])).status_code == 404


def test_upload_into_folder(client):
    folder = client.post("/folders", json={"name": "Pics"}).json()
    resp = client.post(
        "/files",
        files={"file": ("pic.png", b"\x89PNG\r\n", "image/png")},
        data={"parent_id": folder["id"]},
    )
    assert resp.status_code == 201
    assert resp.json()["parent_id"] == folder["id"]

    contents = client.get("/folders/{}/contents".format(folder["id"])).json()
    assert len(contents) == 1


def test_move_file_between_folders(client):
    a = client.post("/folders", json={"name": "A"}).json()
    b = client.post("/folders", json={"name": "B"}).json()
    f = client.post("/files", files={"file": ("f.txt", b"x", "text/plain")},
                    data={"parent_id": a["id"]}).json()

    moved = client.patch(
        "/items/{}/move".format(f["id"]),
        json={"parent_id": b["id"]},
    ).json()
    assert moved["parent_id"] == b["id"]

    assert len(client.get("/folders/{}/contents".format(a["id"])).json()) == 0
    assert len(client.get("/folders/{}/contents".format(b["id"])).json()) == 1


def test_move_into_missing_folder_returns_400(client):
    f = client.post("/files", files={"file": ("f.txt", b"x", "text/plain")}).json()
    resp = client.patch("/items/{}/move".format(f["id"]), json={"parent_id": "nope"})
    assert resp.status_code == 400


def test_search_finds_by_name_case_insensitive(client):
    client.post("/folders", json={"name": "Tax Documents"})
    client.post("/folders", json={"name": "Photos"})
    results = client.get("/search", params={"q": "tax"}).json()
    assert [r["name"] for r in results] == ["Tax Documents"]


def test_list_drive_root(client):
    folder = client.post("/folders", json={"name": "Root Folder"}).json()
    f = client.post("/files", files={"file": ("r.txt", b"r", "text/plain")}).json()
    items = client.get("/drive").json()
    assert {i["id"] for i in items} == {folder["id"], f["id"]}


def test_delete_folder_removes_children(client):
    folder = client.post("/folders", json={"name": "Trash Me"}).json()
    client.post("/files", files={"file": ("a.txt", b"a", "text/plain")},
                data={"parent_id": folder["id"]})

    resp = client.delete("/items/{}".format(folder["id"]))
    assert resp.status_code == 204

    assert client.get("/folders/{}/contents".format(folder["id"])).status_code == 404
    assert len(client.get("/drive").json()) == 0


def test_download_missing_file_returns_404(client):
    assert client.get("/files/does-not-exist").status_code == 404


def test_create_folder_bad_parent_returns_400(client):
    resp = client.post("/folders", json={"name": "X", "parent_id": "missing"})
    assert resp.status_code == 400
