import os
from pathlib import Path
from typing import Any, Dict

from src.config.settings import Settings
from src.tools.base import Tool
from src.tools.files.path_security import resolve_project_path


class WriteFileTool(Tool):
    name = "write_file"
    description = "Create or overwrite a file within the project root."

    def _project_root(self) -> Path:
        root = getattr(Settings, "PROJECT_ROOT", None)
        if root:
            return Path(root).resolve()
        return Path(__file__).resolve().parents[3]

    def _safe_resolve(self, path: str) -> Path:
        return resolve_project_path(self._project_root(), path)

    def run(self, path: str, content: str, overwrite: bool = False) -> dict:
        try:
            p = self._safe_resolve(path)
            p.parent.mkdir(parents=True, exist_ok=True)
            if p.exists() and not overwrite:
                return {"success": False, "error": "File exists; set overwrite=True to replace"}
            with p.open("w", encoding="utf-8") as f:
                f.write(content)
            return {"success": True, "path": str(p.relative_to(self._project_root()))}
        except PermissionError as exc:
            return {"success": False, "error": str(exc)}
        except Exception as exc:
            return {"success": False, "error": str(exc)}

    def schema(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "description": self.description,
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {"type": "string", "description": "File path relative to project root"},
                    "content": {"type": "string", "description": "Content to write"},
                    "overwrite": {"type": "boolean", "description": "Allow overwrite if file exists"},
                },
                "required": ["path", "content"],
            },
        }
