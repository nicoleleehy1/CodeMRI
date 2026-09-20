"""One allowed-root check shared by the HTTP API and the MCP server."""
import os
from pathlib import Path


def allowed_root() -> Path:
    return Path(os.environ.get("CODEMRI_ALLOWED_ROOT", os.getcwd())).resolve()


def resolve_allowed(root: str) -> Path:
    """Resolve `root` and require it to be inside CODEMRI_ALLOWED_ROOT; raise PermissionError otherwise."""
    path = Path(root).resolve()
    if not path.is_relative_to(allowed_root()):
        raise PermissionError("Repository must be under CODEMRI_ALLOWED_ROOT")
    return path
