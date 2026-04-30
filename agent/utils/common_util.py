import os
from pathlib import Path

from agent.utils.logger import get_logger

log = get_logger("common_util")

def find_project_root(start_path=None) -> Path:
    current = Path(start_path or __file__).resolve()
    for parent in [current, *current.parents]:
        if (parent / "pyproject.toml").exists():
            return parent
    raise FileNotFoundError("not found pyproject.toml")


def get_working_dir() -> str:
    """Get the working directory from env or fallback to project root."""
    env_dir = os.getenv("WORKING_DIR")
    if env_dir:
        return str(os.path.abspath(env_dir))
    return str(find_project_root())


def resolve_path(path: str) -> str:
    """Resolve a path relative to WORKING_DIR and verify it stays within bounds.

    - Relative paths are resolved against WORKING_DIR.
    - Absolute paths are checked to ensure they reside under WORKING_DIR.
    - Symlinks are resolved to detect path-traversal attempts.

    Returns:
        The resolved absolute path string.

    Raises:
        ValueError: If the resolved path escapes WORKING_DIR.
    """
    working_dir = Path(get_working_dir()).resolve()

    # Treat the path as relative to WORKING_DIR when it is not absolute
    candidate = Path(path)
    if not candidate.is_absolute():
        candidate = working_dir / candidate

    # Resolve symlinks and normalise '..' / '.' components
    resolved = candidate.resolve()

    if not str(resolved).startswith(str(working_dir)):
        raise ValueError(
            f"Path '{path}' resolves to '{resolved}' which is outside "
            f"the working directory '{working_dir}'. Operation denied."
        )

    return str(resolved)


def ensure_dir(path: Path) -> Path:
    """Ensure directory exists, return it."""
    path.mkdir(parents=True, exist_ok=True)
    return path


def init_workspace_templates(workspace: Path) -> list[str]:
    """Create workspace template files. Only create missing files."""
    from importlib.resources import files

    temp_path = files("agent") / "templates"

    added_files: list[str] = []

    ensure_dir(workspace / "memory" / "logs")
    long_term = ensure_dir(workspace / "long-term")
    for sub in ("projects", "knowledge", "decisions", "lessons", "journal"):
        ensure_dir(long_term / sub)

    def write_file(src, dest: Path):
        if dest.exists():
            return
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_text(src.read_text(encoding="utf-8") if src else "", encoding="utf-8")
        added_files.append(str(dest.relative_to(workspace)))

    for item in temp_path.rglob("*.md"):
        write_file(item, workspace / item.relative_to(temp_path))

    for name in added_files:
        log.info(f"init workspace template: create file {name}")

    return added_files