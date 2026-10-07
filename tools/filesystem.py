from pathlib import Path
import shutil


class FileSystemTool:
    name = "filesystem"
    description = "Manage files and directories anywhere Windows allows."

    def __init__(self, workspace):
        self.workspace = Path(workspace).resolve()
        self.workspace.mkdir(parents=True, exist_ok=True)

        self.home = Path.home()
        self.desktop = self.home / "Desktop"
        self.documents = self.home / "Documents"
        self.downloads = self.home / "Downloads"

    def _safe_path(self, path):
        path = str(path or "").strip()
        if not path:
            return self.workspace

        target = Path(path).expanduser()
        if target.is_absolute():
            return target.resolve()

        normalized = path.replace("\\", "/").strip("/")
        lower = normalized.lower()

        aliases = {
            "desktop": self.desktop,
            "سطح المكتب": self.desktop,
            "documents": self.documents,
            "document": self.documents,
            "المستندات": self.documents,
            "downloads": self.downloads,
            "download": self.downloads,
            "التنزيلات": self.downloads,
            "home": self.home,
            "المنزل": self.home,
        }

        if lower in aliases:
            return aliases[lower].resolve()

        for alias, base in aliases.items():
            prefix = alias + "/"
            if lower.startswith(prefix):
                return (base / normalized[len(prefix):]).resolve()

        return (self.workspace / normalized).resolve()

    def create_directory(self, path):
        target = self._safe_path(path)
        if target.exists():
            if target.is_dir():
                return f"Directory already exists: {target}"
            raise FileExistsError(f"A file already exists at: {target}")
        target.mkdir(parents=True, exist_ok=True)
        return f"Directory created: {target}"

    def write_file(self, path, content):
        target = self._safe_path(path)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(str(content), encoding="utf-8")
        return f"File written: {target}"

    def read_file(self, path):
        target = self._safe_path(path)
        if not target.is_file():
            raise FileNotFoundError(f"File not found: {target}")
        return target.read_text(encoding="utf-8")

    def list_directory(self, path="."):
        target = self._safe_path(path)
        if not target.is_dir():
            raise NotADirectoryError(f"Not a directory: {target}")
        return [
            {"name": item.name, "type": "DIR" if item.is_dir() else "FILE"}
            for item in sorted(target.iterdir(), key=lambda x: x.name.lower())
        ]

    def delete(self, path):
        target = self._safe_path(path)
        if not target.exists():
            raise FileNotFoundError(f"Path not found: {target}")
        if target.is_dir():
            shutil.rmtree(target)
            return f"Directory deleted: {target}"
        target.unlink()
        return f"File deleted: {target}"

    def rename(self, path, new_name):
        target = self._safe_path(path)
        if not target.exists():
            raise FileNotFoundError(f"Path not found: {target}")
        new_name = str(new_name).strip()
        if not new_name or Path(new_name).name != new_name:
            raise ValueError("new_name must be a single file/folder name.")
        destination = target.parent / new_name
        target.rename(destination)
        return f"Renamed: {target} -> {destination}"

    def move(self, source, destination):
        source_path = self._safe_path(source)
        destination_path = self._safe_path(destination)
        if not source_path.exists():
            raise FileNotFoundError(f"Source not found: {source_path}")
        destination_path.parent.mkdir(parents=True, exist_ok=True)
        result = shutil.move(str(source_path), str(destination_path))
        return f"Moved: {source_path} -> {result}"

    def copy(self, source, destination):
        source_path = self._safe_path(source)
        destination_path = self._safe_path(destination)
        if not source_path.exists():
            raise FileNotFoundError(f"Source not found: {source_path}")
        destination_path.parent.mkdir(parents=True, exist_ok=True)
        if source_path.is_dir():
            shutil.copytree(source_path, destination_path, dirs_exist_ok=True)
        else:
            shutil.copy2(source_path, destination_path)
        return f"Copied: {source_path} -> {destination_path}"

    def describe(self):
        return {
            "name": self.name,
            "description": self.description,
            "actions": {
                "create_directory": {"description": "Create a directory anywhere.", "parameters": {"path": {"type": "string", "required": True}}},
                "write_file": {"description": "Create or overwrite a UTF-8 text file anywhere.", "parameters": {"path": {"type": "string", "required": True}, "content": {"type": "string", "required": True}}},
                "read_file": {"description": "Read a UTF-8 text file.", "parameters": {"path": {"type": "string", "required": True}}},
                "list_directory": {"description": "List a directory.", "parameters": {"path": {"type": "string", "required": False, "default": "."}}},
                "delete": {"description": "Delete a file or directory.", "parameters": {"path": {"type": "string", "required": True}}},
                "rename": {"description": "Rename a file or directory.", "parameters": {"path": {"type": "string", "required": True}, "new_name": {"type": "string", "required": True}}},
                "move": {"description": "Move a file or directory.", "parameters": {"source": {"type": "string", "required": True}, "destination": {"type": "string", "required": True}}},
                "copy": {"description": "Copy a file or directory.", "parameters": {"source": {"type": "string", "required": True}, "destination": {"type": "string", "required": True}}},
            },
        }
