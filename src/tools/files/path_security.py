from pathlib import Path


def is_sensitive_path(path: Path) -> bool:
    for part in path.parts:
        name = part.casefold()
        if name == ".env" or name.startswith(".env.") or name.endswith("_keys.json"):
            return True
        if name in {"id_rsa", "id_ed25519"} or Path(name).suffix in {".pem", ".p12", ".pfx"}:
            return True
    return False


def resolve_project_path(project_root: Path, path: str) -> Path:
    root = project_root.resolve()
    requested_path = Path(path)
    candidate = (root / requested_path).resolve() if not requested_path.is_absolute() else requested_path.resolve()

    try:
        candidate.relative_to(root)
    except ValueError as exc:
        raise PermissionError("Path outside project root is not allowed") from exc

    if is_sensitive_path(candidate):
        raise PermissionError("Access to credential files is not allowed")

    return candidate