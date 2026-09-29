from pathlib import Path
from typing import Any, Dict, List

from src.config.settings import Settings
from src.tools.base import Tool
from src.tools.files.path_security import is_sensitive_path, resolve_project_path


class ListDirectoryTool(Tool):
    name = "list_directory"
    description = "List directory tree under project root; skip __pycache__, node_modules, .git."

    def _project_root(self) -> Path:
        root = getattr(Settings, "PROJECT_ROOT", None)
        if root:
            return Path(root).resolve()
        return Path(__file__).resolve().parents[3]

    def _safe_resolve(self, path: str) -> Path:
        return resolve_project_path(self._project_root(), path)

    def run(self, path: str = ".", max_depth: int = 5) -> dict:
        try:
            root = self._safe_resolve(path)
            results: List[str] = []
            skip_dirs = {"__pycache__", "node_modules", ".git"}

            def walk(p: Path, depth: int):
                if depth < 0:
                    return
                for child in sorted(p.iterdir(), key=lambda x: (not x.is_dir(), x.name)):
                    if child.name in skip_dirs:
                        continue
                    if is_sensitive_path(child):
                        continue
                    rel = child.relative_to(self._project_root())
                    results.append(str(rel) + ("/" if child.is_dir() else ""))
                    if child.is_dir():
                        walk(child, depth - 1)

            walk(root, max_depth)
            return {"success": True, "entries": results}
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
                    "path": {"type": "string", "description": "Directory path relative to project root"},
                    "max_depth": {"type": "integer", "description": "How deep to recurse (default 5)"},
                },
                "required": [],
            },
        }
