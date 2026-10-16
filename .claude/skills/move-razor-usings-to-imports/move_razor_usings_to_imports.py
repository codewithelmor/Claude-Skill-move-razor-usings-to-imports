#!/usr/bin/env python3
"""
move_razor_usings_to_imports.py (non-interactive, Claude-friendly variant)

Finds Blazor projects under a folder, lets you pick one or more with command
line options, and moves plain "@using Namespace" directives out of .razor
files into the NEAREST _Imports.razor.

This variant never asks questions. It is a DRY RUN by default; nothing is
written unless you pass --apply. (The original interactive prompts for the
project choice, dry-run/apply mode and the Y/N confirmation were replaced by
the --project, --list and --apply options so Claude can drive the script.)

How _Imports.razor files are handled:
  * Every _Imports.razor in the project is found recursively (bin/obj/
    node_modules skipped) and printed as a hierarchy, with the number of pages
    that use each one as their nearest.
  * For each .razor file, the script walks UP from the file's folder to the
    project root and uses the NEAREST _Imports.razor (this mirrors how Razor
    itself applies _Imports.razor files, so behavior is preserved):
        Pages/Manage/Email.razor   -> Pages/Manage/_Imports.razor
        Pages/Login.razor          -> Pages/_Imports.razor
        Shared/Foo.razor           -> nearest one above Shared/
  * If the namespace is already imported by any _Imports.razor above the file,
    the line is simply removed and nothing is added.
  * If no _Imports.razor exists above a file, the project-root one is used and
    created (the plan marks it as a NEW FILE and you confirm before writing).

Only pages that actually contain a plain "@using Namespace" line are modified,
and only those lines are removed. Line endings, BOM and the trailing newline
are preserved exactly. Existing _Imports.razor files are edited minimally: new
usings are inserted after the last existing @using and nothing else is
reordered.

Usage:
    python move_razor_usings_to_imports.py --path C:\\src\\MySolution --list
    python move_razor_usings_to_imports.py --path C:\\src\\MySolution
    python move_razor_usings_to_imports.py --path C:\\src\\MySolution --project BlazorApp
    python move_razor_usings_to_imports.py --path C:\\src\\MySolution --project BlazorApp --apply

Options:
    --path      Root folder to scan for Blazor projects (default: current folder).
    --list      Only list the Blazor projects found, then exit.
    --project   One or more project names (the .csproj file name without the
                extension). Omit it, or use "all", to include every project.
    --apply     Write the changes. Without this option the run is a preview.
    --dry-run   Accepted for compatibility. Preview is already the default.

Notes:
  * Make sure your working tree is clean (git status / commit) before running
    for real, so any change is easy to review or revert.
  * Only simple "@using Some.Namespace" lines are moved. "@using static Foo"
    and "@using Bar = Some.Other.Namespace" are reported but left in place.
  * A using moved into a sub-folder's _Imports.razor applies to every .razor
    file in that folder and below, not just the file it came from.
"""

from __future__ import annotations

import argparse
import os
import re
import sys
from dataclasses import dataclass
from pathlib import Path

SIMPLE_USING_RE = re.compile(r'^\s*@using\s+([A-Za-z_][\w.]*)\s*;?\s*$')
COMPLEX_USING_RE = re.compile(r'^\s*@using\s+(static\s+|[A-Za-z_][\w.]*\s*=)')
ANY_USING_RE = re.compile(r'^\s*@using\s')
BLANK_RE = re.compile(r'^\s*$')
SEGMENT_RE = re.compile(r'[^\n]*\n|[^\n]+')

EXCLUDED_DIR_PARTS = {"bin", "obj", "node_modules"}
IMPORTS_NAME = "_Imports.razor"
BOM = b"\xef\xbb\xbf"


# ---------------------------------------------------------------- file helpers

@dataclass
class RawFile:
    # One entry per line, INCLUDING its original line terminator, so joining
    # the segments rebuilds the file exactly. Index == zero-based line index.
    segments: list[str]
    has_bom: bool
    eol: str


def read_raw(path: Path) -> RawFile:
    raw = path.read_bytes()
    has_bom = raw.startswith(BOM)
    text = raw.decode("utf-8-sig")
    segments = SEGMENT_RE.findall(text)
    if "\r\n" in text:
        eol = "\r\n"
    elif "\n" in text:
        eol = "\n"
    else:
        eol = os.linesep
    return RawFile(segments, has_bom, eol)


def write_raw(path: Path, segments: list[str], has_bom: bool) -> None:
    """Write bytes directly so BOM and line endings are exactly preserved."""
    data = "".join(segments).encode("utf-8")
    if has_bom:
        data = BOM + data
    path.write_bytes(data)


def line_text(segment: str) -> str:
    return segment.rstrip("\r\n")


def is_excluded(path: Path) -> bool:
    return any(part in EXCLUDED_DIR_PARTS for part in path.parts)


def get_razor_files(project_dir: Path, exclude_imports: bool = False) -> list[Path]:
    files = [
        f for f in project_dir.rglob("*.razor")
        if not is_excluded(f.relative_to(project_dir))
    ]
    if exclude_imports:
        files = [f for f in files if f.name != IMPORTS_NAME]
    return sorted(files)


def get_imports_files(project_dir: Path) -> set[Path]:
    """Recursively find every _Imports.razor in the project."""
    return {
        f for f in project_dir.rglob(IMPORTS_NAME)
        if f.is_file() and not is_excluded(f.relative_to(project_dir))
    }


def ancestor_imports(file: Path, project_dir: Path, known: set[Path]) -> list[Path]:
    """Existing _Imports.razor files from the file's folder up to the project
    root (inclusive), nearest first."""
    result: list[Path] = []
    d = file.parent
    while True:
        candidate = d / IMPORTS_NAME
        if candidate in known:
            result.append(candidate)
        if d == project_dir or d.parent == d:
            break
        d = d.parent
    return result


def get_existing_usings(imports_path: Path) -> set[str]:
    existing: set[str] = set()
    if imports_path.exists():
        for seg in read_raw(imports_path).segments:
            m = SIMPLE_USING_RE.match(line_text(seg))
            if m:
                existing.add(m.group(1))
    return existing


# ------------------------------------------------------------------- projects

@dataclass
class Project:
    name: str
    csproj_path: Path
    project_dir: Path
    razor_count: int


def find_blazor_projects(root: Path) -> list[Project]:
    csproj_files = [
        f for f in root.rglob("*.csproj")
        if not is_excluded(f.relative_to(root))
    ]

    projects: list[Project] = []
    for csproj in sorted(csproj_files):
        project_dir = csproj.parent
        razor_files = get_razor_files(project_dir)
        if razor_files:
            projects.append(Project(
                name=csproj.stem,
                csproj_path=csproj,
                project_dir=project_dir,
                razor_count=len(razor_files),
            ))
    return projects


def section(text: str) -> None:
    print()
    print("=" * 70)
    print(text)
    print("=" * 70)


def list_projects(projects: list[Project], root: Path) -> None:
    section(f"Blazor projects found under: {root}")
    for i, p in enumerate(projects, start=1):
        print(f"  [{i}] {p.name}  ({p.razor_count} .razor files)  -  {p.project_dir}")


def resolve_projects(projects: list[Project], names: list[str] | None) -> list[Project]:
    """Pick projects by name (case-insensitive). None or 'all' means every project."""
    if not names or any(n.lower() == "all" for n in names):
        return projects

    by_name = {p.name.lower(): p for p in projects}
    chosen: list[Project] = []
    unknown: list[str] = []
    for n in names:
        match = by_name.get(n.lower())
        if match is None:
            unknown.append(n)
        elif match not in chosen:
            chosen.append(match)

    if unknown:
        print(f"Unknown project name(s): {', '.join(unknown)}", file=sys.stderr)
        print("Available projects: " + ", ".join(p.name for p in projects), file=sys.stderr)
        sys.exit(1)
    return chosen


# ------------------------------------------------------------------ processing

@dataclass
class Move:
    file: Path
    line_index: int
    namespace: str
    target: Path      # the _Imports.razor this using belongs in
    covered: bool     # already imported at/above target -> just remove the line


@dataclass
class Skipped:
    file: Path
    line_index: int
    raw_line: str


def remove_lines(segments: list[str], remove: set[int]) -> list[str]:
    """Drop the given lines, plus the blank line a removed block leaves behind
    (at the top of the file, or as a doubled blank line in the middle)."""
    kept: list[str] = []
    prev_removed = False
    for i, seg in enumerate(segments):
        if i in remove:
            prev_removed = True
            continue
        if prev_removed and BLANK_RE.match(line_text(seg)):
            if not kept or BLANK_RE.match(line_text(kept[-1])):
                continue
        prev_removed = False
        kept.append(seg)
    return kept


def add_usings(raw: RawFile | None, namespaces: list[str]) -> list[str]:
    """Insert new @using lines after the last existing @using (or at the top if
    there is none) without touching anything else in the file."""
    segs = list(raw.segments) if raw else []
    eol = raw.eol if raw else os.linesep
    block = [f"@using {ns}{eol}" for ns in namespaces]

    anchor = -1
    for i, seg in enumerate(segs):
        if ANY_USING_RE.match(line_text(seg)):
            anchor = i

    if anchor >= 0:
        if not segs[anchor].endswith("\n"):
            segs[anchor] += eol
        segs[anchor + 1:anchor + 1] = block
    else:
        segs[0:0] = block
        if len(segs) > len(block) and not BLANK_RE.match(line_text(segs[len(block)])):
            segs.insert(len(block), eol)   # blank separator before existing content
    return segs


def process_project(project: Project, is_dry_run: bool) -> None:
    section(f"Project: {project.name}")

    project_dir = project.project_dir
    root_imports = project_dir / IMPORTS_NAME

    razor_files = get_razor_files(project_dir, exclude_imports=True)
    if not razor_files:
        print("No .razor files (other than _Imports.razor) found. Nothing to do.")
        return

    # ---- Recursively discover every _Imports.razor in the project ----
    imports_files = get_imports_files(project_dir)

    # Nearest _Imports.razor for every page, computed once
    ancestors_by_file: dict[Path, list[Path]] = {}
    governed: dict[Path, int] = {}
    unattached = 0
    for f in razor_files:
        anc = ancestor_imports(f, project_dir, imports_files)
        ancestors_by_file[f] = anc
        if anc:
            governed[anc[0]] = governed.get(anc[0], 0) + 1
        else:
            unattached += 1

    print(f"Detected {len(imports_files)} _Imports.razor file(s) (hierarchy, nearest-wins):")
    if not imports_files:
        print("  (none - the project-root one will be created if anything needs to move)")
    else:
        for p in sorted(imports_files):
            rel = p.relative_to(project_dir)
            indent = "  " * (len(rel.parts) - 1)
            print(f"  {indent}{rel}   [{governed.get(p, 0)} page(s) use this as their nearest]")
    if unattached:
        print(f"  {unattached} page(s) have no _Imports.razor above them; "
              f"the project-root one would be used.")

    usings_cache: dict[Path, set[str]] = {p: get_existing_usings(p) for p in imports_files}

    moves: list[Move] = []
    skipped: list[Skipped] = []

    for file in razor_files:
        segments = read_raw(file).segments
        ancestors = ancestors_by_file[file]
        target = ancestors[0] if ancestors else root_imports

        for i, seg in enumerate(segments):
            line = line_text(seg)
            m = SIMPLE_USING_RE.match(line)
            if m:
                ns = m.group(1)
                covered = any(ns in usings_cache[a] for a in ancestors)
                moves.append(Move(file, i, ns, target, covered))
            elif COMPLEX_USING_RE.match(line):
                skipped.append(Skipped(file=file, line_index=i, raw_line=line.strip()))

    if not moves:
        print()
        print("No plain '@using Namespace' lines found in this project's .razor files.")
        if skipped:
            print(f"{len(skipped)} alias/static @using line(s) found - left untouched (review manually):")
            for s in skipped:
                print(f"  {s.file.name}  (line {s.line_index + 1}): {s.raw_line}")
        return

    # ---- Group by target and work out what each target must gain ----
    moves_by_target: dict[Path, list[Move]] = {}
    for mv in moves:
        moves_by_target.setdefault(mv.target, []).append(mv)

    adds_by_target: dict[Path, list[str]] = {
        t: sorted({mv.namespace for mv in mvs if not mv.covered})
        for t, mvs in moves_by_target.items()
    }

    files_touched = {mv.file for mv in moves}
    total_adds = sum(len(a) for a in adds_by_target.values())
    changed_targets = sum(1 for a in adds_by_target.values() if a)

    # ---- Show the plan ----
    print()
    print("Planned changes (only pages that contain @using lines are touched):")
    for target in sorted(moves_by_target):
        mvs = moves_by_target[target]
        new_tag = "" if target.exists() else "  (NEW FILE - will be created)"
        print()
        print(f"  Target: {target.relative_to(project_dir)}{new_tag}")

        adds = adds_by_target[target]
        if not adds:
            print("    Add: (none - everything is already imported at or above this level)")
        else:
            print(f"    Add ({len(adds)}):")
            for ns in adds:
                print(f"      @using {ns}")

        print("    Remove from:")
        by_file: dict[Path, list[Move]] = {}
        for mv in mvs:
            by_file.setdefault(mv.file, []).append(mv)
        for file in sorted(by_file):
            print(f"      {file.relative_to(project_dir)}")
            for mv in by_file[file]:
                note = "  (already imported above)" if mv.covered else ""
                print(f"        line {mv.line_index + 1}: @using {mv.namespace}{note}")

    print()
    print(f"  Totals: {len(moves)} line(s) removed from {len(files_touched)} page(s); "
          f"{total_adds} using(s) added across {changed_targets} _Imports.razor file(s).")

    if skipped:
        print()
        print(f"  Alias/static @using lines found - NOT moved, review manually ({len(skipped)}):")
        for s in skipped:
            print(f"    {s.file.name} (line {s.line_index + 1}): {s.raw_line}")

    if is_dry_run:
        print()
        print("DRY RUN - no files were changed. Re-run with --apply to write the changes.")
        return

    # ---- 1) Remove using lines from the pages (and nothing else) ----
    moves_by_file: dict[Path, set[int]] = {}
    for mv in moves:
        moves_by_file.setdefault(mv.file, set()).add(mv.line_index)
    for file, indices_to_remove in moves_by_file.items():
        raw = read_raw(file)
        write_raw(file, remove_lines(raw.segments, indices_to_remove), raw.has_bom)

    # ---- 2) Add the namespaces to each target _Imports.razor (minimal edit) ----
    for target, adds in adds_by_target.items():
        if not adds:
            continue
        raw = read_raw(target) if target.exists() else None
        write_raw(target, add_usings(raw, adds), raw.has_bom if raw else False)

    print()
    print(f"Done. Added {total_adds} using(s) across {changed_targets} _Imports.razor file(s) "
          f"and cleaned {len(moves)} line(s) from {len(moves_by_file)} page(s).")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Move @using directives from .razor files into the nearest _Imports.razor. "
                    "Preview by default; pass --apply to write changes."
    )
    parser.add_argument("--path", default=".", help="Root folder to scan for Blazor projects.")
    parser.add_argument(
        "--project",
        nargs="+",
        default=None,
        help="Project name(s) to process (.csproj name without extension). "
             "Omit or use 'all' for every project.",
    )
    parser.add_argument("--list", action="store_true", help="List Blazor projects and exit.")
    parser.add_argument("--apply", action="store_true", help="Write the changes (default is a preview).")
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Preview only (this is already the default; kept for compatibility).",
    )
    args = parser.parse_args()

    if args.apply and args.dry_run:
        print("Use either --apply or --dry-run, not both.", file=sys.stderr)
        sys.exit(1)

    root = Path(args.path).resolve()
    if not root.exists():
        print(f"Path not found: {root}", file=sys.stderr)
        sys.exit(1)

    section("Scanning for Blazor projects")
    projects = find_blazor_projects(root)

    if not projects:
        print(f"No .csproj projects containing .razor files were found under {root}")
        sys.exit(0)

    if args.list:
        list_projects(projects, root)
        return

    selected_projects = resolve_projects(projects, args.project)
    is_dry_run = not args.apply

    list_projects(selected_projects, root)
    print()
    print("Mode: " + ("DRY RUN (preview only)" if is_dry_run else "APPLY (files will be written)"))

    for project in selected_projects:
        process_project(project, is_dry_run)

    section("Finished")


if __name__ == "__main__":
    main()
