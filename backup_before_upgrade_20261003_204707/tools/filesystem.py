from pathlib import Path
import shutil


class FileSystemTool:

    name = "filesystem"
    description = "Manage files and directories anywhere on the computer."

    def __init__(self, workspace):

        self.workspace = Path(workspace).resolve()
        self.workspace.mkdir(
            parents=True,
            exist_ok=True
        )

        self.home = Path.home()
        self.desktop = self.home / "Desktop"
        self.documents = self.home / "Documents"
        self.downloads = self.home / "Downloads"

    # =========================================================
    # PATH RESOLUTION
    # =========================================================

    def _safe_path(self, path):

        path = str(path).strip()

        if not path:
            return self.workspace

        target = Path(path).expanduser()

        # Absolute Windows path
        if target.is_absolute():
            return target.resolve()

        normalized = path.replace("\\", "/").strip("/")
        lower = normalized.lower()

        special_locations = {

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

        # Exact special location
        if lower in special_locations:

            return special_locations[
                lower
            ].resolve()

        # Special location + subpath
        for alias, base in special_locations.items():

            prefix = alias + "/"

            if lower.startswith(prefix):

                relative_part = normalized[
                    len(prefix):
                ]

                return (
                    base / relative_part
                ).resolve()

        # Normal relative path
        return (
            self.workspace / normalized
        ).resolve()

    # =========================================================
    # CREATE DIRECTORY
    # =========================================================

    def create_directory(self, path):

        target = self._safe_path(path)

        if target.exists():

            if target.is_dir():

                return (
                    f"Directory already exists: {target}"
                )

            raise FileExistsError(
                f"A file already exists at: {target}"
            )

        target.mkdir(
            parents=True,
            exist_ok=True
        )

        return f"Directory created: {target}"

    # =========================================================
    # WRITE FILE
    # =========================================================

    def write_file(self, path, content):

        target = self._safe_path(path)

        target.parent.mkdir(
            parents=True,
            exist_ok=True
        )

        target.write_text(
            str(content),
            encoding="utf-8"
        )

        return f"File written: {target}"

    # =========================================================
    # READ FILE
    # =========================================================

    def read_file(self, path):

        target = self._safe_path(path)

        if not target.is_file():

            raise FileNotFoundError(
                f"File not found: {target}"
            )

        return target.read_text(
            encoding="utf-8"
        )

    # =========================================================
    # LIST DIRECTORY
    # =========================================================

    def list_directory(self, path="."):

        target = self._safe_path(path)

        if not target.is_dir():

            raise NotADirectoryError(
                f"Not a directory: {target}"
            )

        items = []

        for item in sorted(
            target.iterdir(),
            key=lambda x: x.name.lower()
        ):

            items.append({
                "name": item.name,
                "type":
                    "DIR"
                    if item.is_dir()
                    else "FILE"
            })

        return items

    # =========================================================
    # DELETE
    # =========================================================

    def delete(self, path):

        target = self._safe_path(path)

        if not target.exists():

            raise FileNotFoundError(
                f"Path not found: {target}"
            )

        if target.is_dir():

            shutil.rmtree(target)

            return (
                f"Directory deleted: {target}"
            )

        target.unlink()

        return f"File deleted: {target}"

    # =========================================================
    # RENAME
    # =========================================================

    def rename(self, path, new_name):

        target = self._safe_path(path)

        if not target.exists():

            raise FileNotFoundError(
                f"Path not found: {target}"
            )

        new_name = str(
            new_name
        ).strip()

        if not new_name:

            raise ValueError(
                "New name cannot be empty."
            )

        destination = (
            target.parent / new_name
        )

        target.rename(destination)

        return (
            f"Renamed: {target} -> {destination}"
        )

    # =========================================================
    # MOVE
    # =========================================================

    def move(self, source, destination):

        source_path = self._safe_path(
            source
        )

        destination_path = self._safe_path(
            destination
        )

        if not source_path.exists():

            raise FileNotFoundError(
                f"Source not found: {source_path}"
            )

        destination_path.parent.mkdir(
            parents=True,
            exist_ok=True
        )

        result = shutil.move(
            str(source_path),
            str(destination_path)
        )

        return (
            f"Moved: {source_path} -> {result}"
        )

    # =========================================================
    # COPY
    # =========================================================

    def copy(self, source, destination):

        source_path = self._safe_path(
            source
        )

        destination_path = self._safe_path(
            destination
        )

        if not source_path.exists():

            raise FileNotFoundError(
                f"Source not found: {source_path}"
            )

        destination_path.parent.mkdir(
            parents=True,
            exist_ok=True
        )

        if source_path.is_dir():

            shutil.copytree(
                source_path,
                destination_path,
                dirs_exist_ok=True
            )

        else:

            shutil.copy2(
                source_path,
                destination_path
            )

        return (
            f"Copied: {source_path} -> {destination_path}"
        )

    # =========================================================
    # DESCRIBE
    # =========================================================

    def describe(self):

        return {

            "name": self.name,

            "description":
                self.description,

            "actions": {

                "create_directory": {
                    "description":
                        "Create a directory anywhere.",
                    "parameters": {
                        "path": {
                            "type": "string",
                            "required": True
                        }
                    }
                },

                "write_file": {
                    "description":
                        "Create or overwrite a text file anywhere.",
                    "parameters": {
                        "path": {
                            "type": "string",
                            "required": True
                        },
                        "content": {
                            "type": "string",
                            "required": True
                        }
                    }
                },

                "read_file": {
                    "description":
                        "Read a UTF-8 text file.",
                    "parameters": {
                        "path": {
                            "type": "string",
                            "required": True
                        }
                    }
                },

                "list_directory": {
                    "description":
                        "List a directory.",
                    "parameters": {
                        "path": {
                            "type": "string",
                            "required": False,
                            "default": "."
                        }
                    }
                },

                "delete": {
                    "description":
                        "Delete a file or directory.",
                    "parameters": {
                        "path": {
                            "type": "string",
                            "required": True
                        }
                    }
                },

                "rename": {
                    "description":
                        "Rename a file or directory.",
                    "parameters": {
                        "path": {
                            "type": "string",
                            "required": True
                        },
                        "new_name": {
                            "type": "string",
                            "required": True
                        }
                    }
                },

                "move": {
                    "description":
                        "Move a file or directory.",
                    "parameters": {
                        "source": {
                            "type": "string",
                            "required": True
                        },
                        "destination": {
                            "type": "string",
                            "required": True
                        }
                    }
                },

                "copy": {
                    "description":
                        "Copy a file or directory.",
                    "parameters": {
                        "source": {
                            "type": "string",
                            "required": True
                        },
                        "destination": {
                            "type": "string",
                            "required": True
                        }
                    }
                }
            }
        }