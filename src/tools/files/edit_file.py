from pathlib import Path
from typing import Any, Dict

from src.config.settings import Settings
from src.tools.base import Tool
from src.tools.files.path_security import resolve_project_path


class EditFileTool(Tool):
    name = "edit_file"
    description = "Replace a unique occurrence of old_str with new_str in a file within project root."

    def _project_root(self) -> Path:
        root = getattr(Settings, "PROJECT_ROOT", None)
        if root:
            return Path(root).resolve()
        return Path(__file__).resolve().parents[3]

    def _safe_resolve(self, path: str) -> Path:
        return resolve_project_path(self._project_root(), path)

    def run(self, path: str, old_str: str, new_str: str) -> dict:
        try:
            p = self._safe_resolve(path)
            if not p.exists():
                return {"success": False, "error": "File not found"}
            text = p.read_text(encoding="utf-8")
            count = text.count(old_str)
            if count == 0:
                return {"success": False, "error": "old_str not found"}
            if count > 1:
                return {"success": False, "error": "old_str occurs multiple times; edit requires a unique match"}
            new_text = text.replace(old_str, new_str, 1)
            p.write_text(new_text, encoding="utf-8")
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
                    "old_str": {"type": "string", "description": "Exact old string to replace"},
                    "new_str": {"type": "string", "description": "Replacement string"},
                },
                "required": ["path", "old_str", "new_str"],
            },
        }
