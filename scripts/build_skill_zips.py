#!/usr/bin/env python3
"""Package every skill under plugins/*/skills/ as an uploadable zip.

Each zip holds the skill folder at its top level (`<name>/SKILL.md`), the layout Claude.ai and
Claude Desktop require. The skill's plugin version is stamped into the zip's SKILL.md as
`metadata.version`; the files in the repo never carry a version. Zips are reproducible: the same
commit always produces byte-identical zips.

Also writes `manifest.json` (skill, plugin, version, sha256, size) and `SHA256SUMS` to the output
directory, for the website and for download verification.

Usage:
    build_skill_zips.py --out dist [--tag v0.2.0]

With --tag, every plugin's version in plugin.json must equal the tag without its leading "v".
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
    marketplace = json.loads((ROOT / ".claude-plugin" / "marketplace.json").read_text(encoding="utf-8"))
    plugins = []
    for entry in marketplace["plugins"]:
        plugin_dir = (ROOT / entry["source"]).resolve()
        manifest = json.loads((plugin_dir / ".claude-plugin" / "plugin.json").read_text(encoding="utf-8"))
        plugins.append((manifest["name"], manifest["version"], plugin_dir))
    return plugins


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--out", required=True, type=Path, help="output directory (created if missing)")
    parser.add_argument("--tag", help="release tag, for example v0.2.0; must match every plugin version")
    args = parser.parse_args()

    try:
        plugins = load_plugins()
        if args.tag:
            for plugin_name, version, _ in plugins:
                if args.tag != f"v{version}":
                    raise BuildError(f"tag {args.tag} does not match {plugin_name} version {version} in plugin.json")

        args.out.mkdir(parents=True, exist_ok=True)
        manifest = []
        seen: dict[str, str] = {}
        for plugin_name, version, plugin_dir in plugins:
            skills_dir = plugin_dir / "skills"
            for skill_dir in sorted(p for p in skills_dir.iterdir() if (p / "SKILL.md").is_file()):
                if skill_dir.name in seen:
                    raise BuildError(f"skill '{skill_dir.name}' exists in both {seen[skill_dir.name]} and {plugin_name}")
                seen[skill_dir.name] = plugin_name
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
