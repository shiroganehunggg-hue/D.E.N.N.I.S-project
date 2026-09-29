import os
from pathlib import Path
from typing import Any, Dict, Optional

from src.config.settings import Settings
from src.tools.base import Tool
from src.tools.files.path_security import resolve_project_path


class ReadFileTool(Tool):
    name = "read_file"
    description = "Read a file within the project root; support line ranges (start_line, end_line)."

    def _project_root(self) -> Path:
        root = getattr(Settings, "PROJECT_ROOT", None)
        if root:
            return Path(root).resolve()
        return Path(__file__).resolve().parents[3]

    def _safe_resolve(self, path: str) -> Path:
        return resolve_project_path(self._project_root(), path)

    def run(self, path: str, start_line: Optional[int] = None, end_line: Optional[int] = None) -> dict:
        try:
            p = self._safe_resolve(path)
            if not p.exists():
                return {"success": False, "error": "File not found", "path": str(p)}

            # Read text file safely
            with p.open("r", encoding="utf-8", errors="replace") as f:
                if start_line is None and end_line is None:
                    content = f.read()
                else:
                    start = max(1, int(start_line)) if start_line is not None else 1
                    end = int(end_line) if end_line is not None else None
                    lines = f.readlines()
                    selected = lines[start - 1: end]
                    content = "".join(selected)

            return {"success": True, "path": str(p.relative_to(self._project_root())), "content": content}
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
                    "start_line": {"type": "integer", "description": "1-based start line (inclusive)"},
                    "end_line": {"type": "integer", "description": "1-based end line (exclusive)"},
                },
                "required": ["path"],
            },
        }
