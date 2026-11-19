#!/usr/bin/env python3
"""Second-brain vault helper (stdlib only).

  brain.py init  [--dir brain]              create missing folders/files, never overwrite
  brain.py check [--dir brain] [--stale 7]  validate notes, links, sources, stale inbox items
"""
import argparse
import datetime as dt
import re
import shutil
import sys
from pathlib import Path

FOLDERS = ["sources", "0-inbox", "1-projects", "2-areas", "3-resources", "4-archive"]
NOTE_FOLDERS = FOLDERS[1:]
TEMPLATES = ["rules.md", "profile.md", "index.md", "changelog.md"]

TYPES = {
    "observation", "claim", "question", "request", "task", "decision",
    "commitment", "preference", "goal", "person", "concept", "project",
}
ACTIONABLE = {"task", "request", "commitment"}
ACTION_STATUS = {"open", "doing", "waiting", "done", "dropped"}
NOTE_STATUS = {"active", "archived"}
RELS = {
    "supports", "contradicts", "depends-on", "part-of", "follows-from",
    "about", "decided-by", "blocks", "related",
}
REQUIRED = ["id", "title", "type", "status", "created", "source"]


def cmd_init(root: Path) -> int:
    tpl = Path(__file__).resolve().parent.parent / "templates"
    root.mkdir(parents=True, exist_ok=True)
    for name in FOLDERS:
        d = root / name
        if not d.exists():
            d.mkdir()
            (d / ".gitkeep").touch()
            print(f"created {d}/")
    for name in TEMPLATES:
        dst = root / name
        if dst.exists():
            print(f"kept    {dst} (already exists)")
        else:
            shutil.copyfile(tpl / name, dst)
            print(f"created {dst}")
    return 0


def unquote(v: str) -> str:
    v = v.strip()
    if len(v) >= 2 and v[0] == v[-1] and v[0] in "\"'":
        return v[1:-1]
    return v


def parse_note(path: Path):
    """Return (fields, links, error). Handles the flat front matter this skill writes."""
    lines = path.read_text(encoding="utf-8").splitlines()
    if not lines or lines[0].strip() != "---":
        return None, None, "missing front matter"
    try:
        end = next(i for i in range(1, len(lines)) if lines[i].strip() == "---")
    except StopIteration:
        return None, None, "front matter not closed"
    fields, links, cur, in_links = {}, [], None, False
    for raw in lines[1:end]:
        if not raw.strip() or raw.lstrip().startswith("#"):
            continue
        if not raw.startswith((" ", "\t", "-")):
            key, _, val = raw.partition(":")
            key = key.strip()
            in_links = key == "links"
            cur = None
            if not in_links:
                fields[key] = unquote(val)
            continue
        if not in_links:
            continue
        item = raw.strip()
        if item.startswith("-"):
            cur = {}
            links.append(cur)
            item = item[1:].strip()
        if item and cur is not None:
            key, _, val = item.partition(":")
            cur[key.strip()] = unquote(val)
    return fields, links, None


def cmd_check(root: Path, stale_days: int) -> int:
    if not root.is_dir():
        print(f"ERROR {root} does not exist; run `brain.py init --dir {root}` first")
        return 1
    errors, warnings, notes = [], [], {}
    for name in FOLDERS + TEMPLATES:
        if not (root / name).exists():
            errors.append(f"{root / name}: missing (run init)")

    for folder in NOTE_FOLDERS:
        for path in sorted((root / folder).rglob("*.md")):
            rel = path.relative_to(root)
            fields, links, err = parse_note(path)
            if err:
                errors.append(f"{rel}: {err}")
                continue
            for key in REQUIRED:
                if not fields.get(key):
                    errors.append(f"{rel}: missing `{key}`")
            nid = fields.get("id")
            if nid:
                if nid in notes:
                    errors.append(f"{rel}: duplicate id `{nid}` (also {notes[nid][0]})")
                else:
                    notes[nid] = (rel, fields, links)
                if nid != path.stem:
                    warnings.append(f"{rel}: id `{nid}` differs from file name")
            typ, status = fields.get("type"), fields.get("status")
            if typ and typ not in TYPES:
                errors.append(f"{rel}: unknown type `{typ}`")
            elif typ and status:
                allowed = ACTION_STATUS if typ in ACTIONABLE else NOTE_STATUS | ACTION_STATUS
                if status not in allowed:
                    errors.append(f"{rel}: status `{status}` not valid for type `{typ}`")
            created = None
            if fields.get("created"):
                try:
                    created = dt.date.fromisoformat(fields["created"])
                except ValueError:
                    errors.append(f"{rel}: `created` is not YYYY-MM-DD")
            src = fields.get("source", "")
            if src and src not in ("user", "inferred") and not re.match(r"https?://", src):
                if not (root / src).is_file():
                    errors.append(f"{rel}: source `{src}` not found in vault")
            if fields.get("sensitive", "false") not in ("true", "false"):
                errors.append(f"{rel}: `sensitive` must be true or false")
            if folder == "0-inbox" and created:
                age = (dt.date.today() - created).days
                if age > stale_days:
                    warnings.append(f"{rel}: in inbox for {age} days")

    index_path = root / "index.md"
    index_text = index_path.read_text(encoding="utf-8") if index_path.exists() else ""
    for nid, (rel, _fields, links) in notes.items():
        for link in links:
            target = link.get("to")
            if not target:
                errors.append(f"{rel}: link without `to`")
            elif target not in notes:
                errors.append(f"{rel}: link to unknown note `{target}`")
            if link.get("rel") not in RELS:
                errors.append(f"{rel}: link rel `{link.get('rel')}` not recognised")
            if not link.get("why"):
                warnings.append(f"{rel}: link to `{target}` has no `why`")
        if nid not in index_text:
            warnings.append(f"{rel}: not listed in index.md")

    for line in errors:
        print("ERROR", line)
    for line in warnings:
        print("WARN ", line)
    print(f"{len(notes)} notes, {len(errors)} errors, {len(warnings)} warnings")
    return 1 if errors else 0


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    p_init = sub.add_parser("init")
    p_init.add_argument("--dir", default="brain")
    p_check = sub.add_parser("check")
    p_check.add_argument("--dir", default="brain")
    p_check.add_argument("--stale", type=int, default=7, help="inbox age in days that triggers a warning")
    args = ap.parse_args()
    root = Path(args.dir)
    return cmd_init(root) if args.cmd == "init" else cmd_check(root, args.stale)


if __name__ == "__main__":
    sys.exit(main())
