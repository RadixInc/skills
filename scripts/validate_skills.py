#!/usr/bin/env python3
"""Validate every skill under plugins/*/skills/ and the plugin manifests."""
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
NAME_RE = re.compile(r"^[a-z0-9]+(-[a-z0-9]+)*$")
MAX_NAME = 64
MAX_DESCRIPTION = 1024
FRONTMATTER_RE = re.compile(r"\A---\n(.*?)\n---\n", re.DOTALL)
SEMVER_RE = re.compile(r"^\d+\.\d+\.\d+$")
# Claude.ai uploads, the Skills API and the Agent Skills spec reject any other top-level key.
ALLOWED_FRONTMATTER_KEYS = {"name", "description", "license", "compatibility", "metadata", "allowed-tools"}

errors: list[str] = []


def fail(path: Path, message: str) -> None:
    errors.append(f"{path.relative_to(ROOT)}: {message}")


def parse_frontmatter(block: str) -> dict[str, str]:
    """Read top-level `key: value` pairs, joining indented continuation lines.

    Covers plain, quoted and folded (`>` / `|`) scalars, which is all a skill needs.
    """
    meta: dict[str, str] = {}
    key = None
    for line in block.splitlines():
        if line[:1] in (" ", "\t") and key:
            meta[key] = f"{meta[key]} {line.strip()}".strip()
            continue
        match = re.match(r"^([A-Za-z0-9_-]+):\s*(.*)$", line)
        if not match:
            key = None
            continue
        key, value = match.group(1), match.group(2).strip()
        if value in (">", "|", ">-", "|-"):
            value = ""
        if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'":
            value = value[1:-1]
        meta[key] = value
    return meta


def check_skill(skill_md: Path) -> None:
    text = skill_md.read_text(encoding="utf-8")
    match = FRONTMATTER_RE.match(text)
    if not match:
        fail(skill_md, "missing YAML frontmatter")
        return
    meta = parse_frontmatter(match.group(1))

    for key in sorted(set(meta) - ALLOWED_FRONTMATTER_KEYS):
        hint = " (the version comes from plugin.json and is stamped in at build time)" if key == "version" else ""
        fail(skill_md, f"frontmatter key '{key}' is not allowed; Claude.ai uploads reject it{hint}")

    name = meta.get("name")
    description = meta.get("description")
    folder = skill_md.parent.name

    if not isinstance(name, str) or not name:
        fail(skill_md, "frontmatter needs a `name`")
    else:
        if name != folder:
            fail(skill_md, f"name '{name}' does not match folder '{folder}'")
        if not NAME_RE.match(name) or len(name) > MAX_NAME:
            fail(skill_md, f"name '{name}' must be kebab-case and at most {MAX_NAME} characters")

    if not isinstance(description, str) or not description.strip():
        fail(skill_md, "frontmatter needs a `description`")
    elif len(description) > MAX_DESCRIPTION:
        fail(skill_md, f"description is {len(description)} characters, limit is {MAX_DESCRIPTION}")


def check_json(path: Path) -> dict:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        fail(path, f"invalid JSON: {exc}")
        return {}


def main() -> int:
    marketplace_path = ROOT / ".claude-plugin" / "marketplace.json"
    marketplace = check_json(marketplace_path)

    for plugin in marketplace.get("plugins", []):
        plugin_dir = (ROOT / plugin.get("source", "")).resolve()
        manifest = plugin_dir / ".claude-plugin" / "plugin.json"
        if not manifest.is_file():
            fail(marketplace_path, f"plugin '{plugin.get('name')}' has no {manifest.relative_to(ROOT)}")
            continue
        meta = check_json(manifest)
        if meta.get("name") != plugin.get("name"):
            fail(manifest, "name does not match marketplace.json")
        # plugin.json is the only place a version lives. Claude Code ignores the marketplace
        # entry's version when plugin.json has one, and the docs say not to set both.
        if "version" in plugin:
            fail(marketplace_path, f"plugin '{plugin.get('name')}' sets a version; remove it, plugin.json owns the version")
        if not SEMVER_RE.match(str(meta.get("version", ""))):
            fail(manifest, "needs a `version` in MAJOR.MINOR.PATCH form")

        mcp = plugin_dir / ".mcp.json"
        if mcp.is_file():
            check_json(mcp)

        skills_dir = plugin_dir / "skills"
        for child in sorted(skills_dir.iterdir()) if skills_dir.is_dir() else []:
            if child.is_dir():
                skill_md = child / "SKILL.md"
                if skill_md.is_file():
                    check_skill(skill_md)
                else:
                    fail(child, "skill folder has no SKILL.md")

    if errors:
        print("\n".join(errors), file=sys.stderr)
        return 1
    print("OK")
    return 0


if __name__ == "__main__":
    sys.exit(main())
