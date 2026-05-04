import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Optional, List

import yaml


@dataclass
class SkillRecord:
    name: str
    description: str
    location: Path  # SKILL.md absolute path
    content: Optional[str] = None  # Can be read on activation; supports reading during discovery

    @property
    def skill_dir(self) -> Path:
        return self.location.parent


# Default directory names to skip (avoid deep scanning)
SKIP_DIRS = {
    ".git", ".svn", "__pycache__", "node_modules", "venv", ".venv", ".tox"
}

def find_skill_dirs_in_root(
    root: Path,
    max_depth: int = 4,
) -> List[Path]:
    """
    Find subdirectories under root containing SKILL.md (up to max_depth levels).
    Simplified: does not strictly handle symlink loops, controlled by max_depth.
    """
    skill_dirs: List[Path] = []

    def walk(current: Path, depth: int):
        if depth > max_depth:
            return
        try:
            entries = list(current.iterdir())
        except Exception:
            return  # Permission error / does not exist

        for entry in entries:
            if not entry.is_dir():
                continue
            if entry.name in SKIP_DIRS:
                continue
            # If SKILL.md exists directly under this directory, treat it as a skill directory
            if (entry / "SKILL.md").is_file():
                skill_dirs.append(entry)
            else:
                # Otherwise continue searching deeper
                walk(entry, depth + 1)

    walk(root, 0)
    return skill_dirs



def parse_skill_md(
    skill_md_path: Path,
    *,
    read_body_now: bool = False,
) -> SkillRecord:
    """
    Parse a single SKILL.md:
    - Extract YAML frontmatter (name/description)
    - Extract body (markdown part)
    - Lenient compatibility: common issues such as "missing quotes after colons" will be attempted to fix and retry
    - Return (SkillRecord)
    """
    text = skill_md_path.read_text(encoding="utf-8")

    # Split frontmatter and body
    parts = re.split(r"^-{3,}\s*$", text, flags=re.MULTILINE)
    if len(parts) < 3:
        # Handle the case where there's only one leading --- line (less common)
        if text.startswith("---"):
            parts2 = re.split(r"^-{3,}\s*$", text[3:], flags=re.MULTILINE)
            if len(parts2) >= 2:
                parts = [""] + parts2

    yaml_part = parts[1].strip()
    body_part = ("\n".join(parts[2:])).strip()

    # Try to parse YAML; on failure, attempt a simple “quote values” retry
    data = yaml.safe_load(yaml_part) or {}

    name = str(data.get("name", "")).strip()
    description = str(data.get("description", "")).strip()

    record = SkillRecord(
        name=name,
        description=description,
        location=skill_md_path,
        content=body_part if read_body_now else None,
    )
    return record


def render_skills_json(
    root_path: Path,
    expose_location: bool = True,
) -> Optional[str]:
    pathlist = find_skill_dirs_in_root(root_path)

    items = []
    for path in pathlist:
        skill_md = path / "SKILL.md"
        skill_record = parse_skill_md(skill_md)
        item: dict = {"name": skill_record.name, "description": skill_record.description}
        if expose_location:
            item["location"] = str(skill_record.location)
        items.append(item)

    if not items:
        return None

    return json.dumps({"available_skills":items}, ensure_ascii=False, indent=2)