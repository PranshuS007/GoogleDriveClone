"""In-memory storage: the metadata index for files and folders.

A sample Google Drive clone backend. Actual file bytes are stored on disk
under the upload directory; this module only tracks the structure
(folders, file metadata) so the "drive" behaves like Google Drive:
folders, paths, moving items, searching by name.

Not thread-safe by design; a single uvicorn worker is assumed.
"""

from __future__ import annotations

import shutil
from pathlib import Path
from typing import List, Optional

from pydantic import BaseModel


class DriveItem(BaseModel):
    """Metadata for one file or folder in the drive."""

    id: str
    name: str
    kind: str  # "file" or "folder"
    parent_id: Optional[str] = None  # None = root
    size: int = 0  # bytes, only meaningful for files
    created_at: str = ""


class DriveStore:
    """Tracks folder structure and file metadata; file bytes live on disk."""

    def __init__(self, root: str | Path):
        root = Path(root)
        root.mkdir(parents=True, exist_ok=True)
        self.root = root
        self.files_dir = root / "files"
        self.files_dir.mkdir(parents=True, exist_ok=True)
        self.items: List[DriveItem] = []
        self.next_id = 1

    # ------------------------- helpers -------------------------

    def _new_id(self) -> str:
        i = self.next_id
        self.next_id += 1
        return f"item-{i}"

    def get(self, item_id: str) -> Optional[DriveItem]:
        for item in self.items:
            if item.id == item_id:
                return item
        return None

    def _path_for(self, item: DriveItem) -> Path:
        """Absolute on-disk path for an item (folder = dir, file = blob)."""
        return self.files_dir / item.id

    # ------------------------- folders -------------------------

    def create_folder(self, name: str, parent_id: Optional[str] = None) -> DriveItem:
        name = name.strip()
        if not name:
            raise ValueError("Folder name cannot be empty")
        if parent_id is not None and not self.get(parent_id):
            raise ValueError(f"Parent folder {parent_id!r} does not exist")
        folder = DriveItem(
            id=self._new_id(),
            name=name,
            kind="folder",
            parent_id=parent_id,
        )
        self.items.append(folder)
        self._path_for(folder).mkdir(parents=True, exist_ok=True)
        return folder

    # ------------------------- files -------------------------

    def save_file(
        self,
        name: str,
        content: bytes,
        parent_id: Optional[str] = None,
    ) -> DriveItem:
        name = name.strip()
        if not name:
            raise ValueError("File name cannot be empty")
        if parent_id is not None and not self.get(parent_id):
            raise ValueError(f"Parent folder {parent_id!r} does not exist")
        item = DriveItem(
            id=self._new_id(),
            name=name,
            kind="file",
            parent_id=parent_id,
            size=len(content),
        )
        self.items.append(item)
        (self.files_dir / item.id).write_bytes(content)
        return item

    def read_file(self, item_id: str) -> bytes:
        """Return the raw bytes of a stored file."""
        item = self.get(item_id)
        if item is None or item.kind != "file":
            raise KeyError("File not found")
        return (self.files_dir / item.id).read_bytes()

    # ------------------------- layout -------------------------

    def list_items(self, parent_id: Optional[str] = None) -> List[DriveItem]:
        """All items directly inside a folder (None = root)."""
        return [i for i in self.items if i.parent_id == parent_id]

    def list_all(self) -> List[DriveItem]:
        return list(self.items)

    def move_item(self, item_id: str, new_parent_id: Optional[str]) -> DriveItem:
        """Move an item to another folder (None = root)."""
        item = self.get(item_id)
        if item is None:
            raise KeyError("Item not found")
        if item.parent_id == new_parent_id:
            return item
        if new_parent_id is not None:
            target = self.get(new_parent_id)
            if target is None or target.kind != "folder":
                raise ValueError("Destination is not a folder")
        if new_parent_id == item_id:
            raise ValueError("Cannot move an item into itself")
        item.parent_id = new_parent_id
        return item

    # ------------------------- searching -------------------------

    def search(self, query: str) -> List[DriveItem]:
        """Case-insensitive name match across the whole drive."""
        q = query.strip().lower()
        if not q:
            return []
        return [i for i in self.items if q in i.name.lower()]

    # ------------------------- delete -------------------------

    def delete_item(self, item_id: str) -> bool:
        item = self.get(item_id)
        if item is None:
            return False
        path = self._path_for(item)
        if item.kind == "folder":
            # remove descendants from the index first
            self.items = [i for i in self.items if not i.id == item_id]
            self._delete_descendants(item_id)
            shutil.rmtree(path, ignore_errors=True)
        else:
            self.items.remove(item)
            path.unlink(missing_ok=True)
        return True

    def _delete_descendants(self, parent_id: str) -> None:
        children = self.list_items(parent_id)
        for child in children:
            if child.kind == "folder":
                self._delete_descendants(child.id)
            self.items = [i for i in self.items if not i.id == child.id]
            self._path_for(child).unlink(missing_ok=True)
