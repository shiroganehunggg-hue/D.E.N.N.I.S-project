import re
from pathlib import Path
from typing import Any, Dict, List

from src.config.settings import Settings
from src.tools.base import Tool
from src.tools.files.path_security import is_sensitive_path, resolve_project_path


class SearchInFilesTool(Tool):
    name = "search_in_files"
    description = "Search files under project root for a regex or keyword; return matching file and line numbers."

    def _project_root(self) -> Path:
        root = getattr(Settings, "PROJECT_ROOT", None)
        if root:
            return Path(root).resolve()
        return Path(__file__).resolve().parents[3]

    def _safe_resolve(self, path: str) -> Path:
        return resolve_project_path(self._project_root(), path)

    def run(self, pattern: str, regex: bool = False, ignore_case: bool = True, path: str = ".", max_results_per_file: int = 20) -> dict:
        try:
            root = self._safe_resolve(path)
            flags = re.MULTILINE
            if ignore_case:
                flags |= re.IGNORECASE
            if regex:
                patt = re.compile(pattern, flags)
            else:
                patt = re.compile(re.escape(pattern), flags)

            matches: Dict[str, List[int]] = {}

            for file in root.rglob("*"):
                if file.is_dir():
                    continue
                if is_sensitive_path(file):
                    continue
                if file.suffix in {".pyc", ".exe", ".dll"}:
                    continue
                try:
                    text = file.read_text(encoding="utf-8")
                except Exception:
                    continue
                file_matches: List[int] = []
                for i, line in enumerate(text.splitlines(), start=1):
                    if patt.search(line):
                        file_matches.append(i)
                        if len(file_matches) >= max_results_per_file:
                            break
                if file_matches:
                    rel = str(file.relative_to(self._project_root()))
                    matches[rel] = file_matches

            return {"success": True, "matches": matches}
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
                    "pattern": {"type": "string", "description": "Regex or keyword to search"},
                    "regex": {"type": "boolean", "description": "Interpret pattern as regex"},
                    "ignore_case": {"type": "boolean", "description": "Case-insensitive search"},
                    "path": {"type": "string", "description": "Subpath under project root to search"},
                },
                "required": ["pattern"],
            },
        }
