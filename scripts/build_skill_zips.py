#!/usr/bin/env python3
"""Package every skill under plugins/*/skills/ as an uploadable zip.

Each zip holds the skill folder at its top level (`<name>/SKILL.md`), the layout Claude.ai and
Claude Desktop require. The skill's plugin version is stamped into the zip's SKILL.md as
`metadata.version`; the files in the repo never carry a version. Zips are reproducible: the same
commit always produces byte-identical zips.

Also writes `manifest.json` (skill, plugin, version, sha256, size) and `SHA256SUMS` to the output
directory, for the website and for download verification.

Usage:
    build_skill_zips.py --out dist [--tag underwriting-v1.0.0]

Without --tag, builds every plugin (a dry run for CI). With --tag, the tag names one plugin by its
folder under plugins/ (`underwriting` for plugins/underwriting) and its version. The script builds
only that plugin and fails unless the version equals the one in its plugin.json.
"""
import argparse
import hashlib
import json
import re
import sys
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
FRONTMATTER_RE = re.compile(r"\A---\n(.*?)\n---\n", re.DOTALL)
TAG_RE = re.compile(r"^(?P<slug>[a-z0-9]+(?:-[a-z0-9]+)*)-v(?P<version>\d+\.\d+\.\d+)$")
SKIP_NAMES = {".DS_Store", "__pycache__"}
FIXED_TIME = (1980, 1, 1, 0, 0, 0)


class BuildError(Exception):
    pass


def stamp_version(skill_md: str, version: str, where: str) -> str:
    """Return SKILL.md text with `metadata.version` set to `version`."""
    match = FRONTMATTER_RE.match(skill_md)
    if not match:
        raise BuildError(f"{where}: missing YAML frontmatter")
    lines = match.group(1).split("\n")

    meta_at = next((i for i, line in enumerate(lines) if re.match(r"^metadata:", line)), None)
    if meta_at is None:
        lines += ["metadata:", f'  version: "{version}"']
    else:
        if lines[meta_at].strip() != "metadata:":
            raise BuildError(f"{where}: write `metadata:` as a block, not inline, so a version can be added")
        end = meta_at + 1
        while end < len(lines) and lines[end][:1] in (" ", "\t"):
            if re.match(r"^\s+version\s*:", lines[end]):
                raise BuildError(f"{where}: metadata.version is set in the source; the build stamps it")
            end += 1
        lines.insert(meta_at + 1, f'  version: "{version}"')

    return "---\n" + "\n".join(lines) + "\n---\n" + skill_md[match.end():]


def skill_files(skill_dir: Path) -> list[Path]:
    return sorted(
        p for p in skill_dir.rglob("*")
        if p.is_file() and not any(part in SKIP_NAMES for part in p.relative_to(skill_dir).parts)
    )


def build_zip(skill_dir: Path, version: str, out_path: Path) -> None:
    name = skill_dir.name
    with zipfile.ZipFile(out_path, "w", zipfile.ZIP_DEFLATED) as zf:
        for path in skill_files(skill_dir):
            rel = path.relative_to(skill_dir).as_posix()
            data = path.read_bytes()
            if rel == "SKILL.md":
                data = stamp_version(data.decode("utf-8"), version, f"{name}/SKILL.md").encode("utf-8")
            info = zipfile.ZipInfo(f"{name}/{rel}", FIXED_TIME)
            info.compress_type = zipfile.ZIP_DEFLATED
            info.external_attr = 0o644 << 16
            zf.writestr(info, data)


def load_plugins() -> list[tuple[str, str, Path]]:
    """Return (plugin name, version, plugin dir) for every plugin in the marketplace."""
    marketplace = json.loads((ROOT / ".claude-plugin" / "marketplace.json").read_text(encoding="utf-8"))
    plugins = []
    for entry in marketplace["plugins"]:
        plugin_dir = (ROOT / entry["source"]).resolve()
        manifest = json.loads((plugin_dir / ".claude-plugin" / "plugin.json").read_text(encoding="utf-8"))
        plugins.append((manifest["name"], manifest["version"], plugin_dir))
    return plugins


def skills_of(plugin_dir: Path) -> list[Path]:
    skills_dir = plugin_dir / "skills"
    return sorted(p for p in skills_dir.iterdir() if (p / "SKILL.md").is_file())


def select_for_tag(plugins: list[tuple[str, str, Path]], tag: str) -> list[tuple[str, str, Path]]:
    """Pick the one plugin a release tag names, and check the tag's version against plugin.json."""
    match = TAG_RE.match(tag)
    if not match:
        raise BuildError(f"tag '{tag}' must look like <plugin>-vMAJOR.MINOR.PATCH, for example underwriting-v1.0.0")
    chosen = [p for p in plugins if p[2].name == match["slug"]]
    if not chosen:
        known = ", ".join(sorted(p[2].name for p in plugins))
        raise BuildError(f"tag '{tag}' names plugin folder '{match['slug']}', which is not in the marketplace (have: {known})")
    plugin_name, version, _ = chosen[0]
    if match["version"] != version:
        raise BuildError(f"tag {tag} has version {match['version']} but {plugin_name} is {version} in plugin.json")
    return chosen


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--out", required=True, type=Path, help="output directory (created if missing)")
    parser.add_argument("--tag", help="release tag, for example underwriting-v1.0.0; builds only that plugin")
    args = parser.parse_args()

    try:
        all_plugins = load_plugins()
        # Skill names are zip names and public download URLs, so they must be unique across plugins
        # even when this run builds only one of them.
        owner: dict[str, str] = {}
        for plugin_name, _, plugin_dir in all_plugins:
            for skill_dir in skills_of(plugin_dir):
                if skill_dir.name in owner:
                    raise BuildError(f"skill '{skill_dir.name}' exists in both {owner[skill_dir.name]} and {plugin_name}")
                owner[skill_dir.name] = plugin_name
        plugins = select_for_tag(all_plugins, args.tag) if args.tag else all_plugins

        args.out.mkdir(parents=True, exist_ok=True)
        manifest = []
        for plugin_name, version, plugin_dir in plugins:
            for skill_dir in skills_of(plugin_dir):
                out_path = args.out / f"{skill_dir.name}.zip"
                build_zip(skill_dir, version, out_path)
                digest = hashlib.sha256(out_path.read_bytes()).hexdigest()
                manifest.append({
                    "skill": skill_dir.name,
                    "plugin": plugin_name,
                    "version": version,
                    "file": out_path.name,
                    "sha256": digest,
                    "bytes": out_path.stat().st_size,
                })
    except (BuildError, OSError, KeyError, json.JSONDecodeError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1

    (args.out / "manifest.json").write_text(json.dumps({"skills": manifest}, indent=2) + "\n", encoding="utf-8")
    (args.out / "SHA256SUMS").write_text("".join(f"{m['sha256']}  {m['file']}\n" for m in manifest), encoding="utf-8")
    for m in manifest:
        print(f"{m['file']}  {m['version']}  {m['bytes']} bytes")
    return 0


if __name__ == "__main__":
    sys.exit(main())
