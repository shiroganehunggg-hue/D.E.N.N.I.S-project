from pathlib import Path

import pytest

from src.config.settings import Settings
from src.tools.files.read_file import ReadFileTool
from src.tools.files.path_security import resolve_project_path


def test_project_root_points_to_repository_root():
    expected_root = Path(__file__).resolve().parents[1]

    assert Path(Settings.PROJECT_ROOT).resolve() == expected_root
    assert ReadFileTool()._project_root() == expected_root


@pytest.mark.parametrize(
    "path",
    [".env", ".env.local", "src/config/groq_keys.json", "private/id_ed25519"],
)
def test_project_path_resolver_rejects_credentials(path):
    with pytest.raises(PermissionError, match="credential files"):
        resolve_project_path(Path(Settings.PROJECT_ROOT), path)


def test_project_path_resolver_rejects_paths_outside_repository():
    with pytest.raises(PermissionError, match="outside project root"):
        resolve_project_path(Path(Settings.PROJECT_ROOT), "../outside.txt")