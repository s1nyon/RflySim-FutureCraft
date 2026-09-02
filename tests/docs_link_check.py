#!/usr/bin/env python3
"""Validate local links in tracked Markdown and current-document destinations."""

from __future__ import annotations

import argparse
import re
import subprocess
import sys
from pathlib import Path
from urllib.parse import unquote, urlsplit


REFERENCE_DEFINITION_RE = re.compile(r"^[ \t]{0,3}\[([^\]]+)\]:[ \t]*(.*)$")
CURRENT_DESTINATIONS = (
    "docs/current/competition-roadmap.md",
    "docs/reference/competition-guide-2026.pdf",
)
ACTIVE_DOCUMENTS = (
    "README.md",
    "AGENTS.md",
    ".agents/AGENT2READ.md",
    ".agents/RFLYSIM_TOOLCHAIN_REFERENCE.md",
    "docs/README.md",
)
PARSER_FIXTURE = "tests/fixtures/docs_links/reference_and_inline_(fixture).txt"
PARSER_FIXTURE_TARGET = "reference_and_inline_(fixture).txt"


def find_closing_bracket(text: str, start: int) -> int | None:
    depth = 0
    index = start
    while index < len(text):
        character = text[index]
        if character == "\\" and index + 1 < len(text):
            index += 2
            continue
        if character == "[":
            depth += 1
        elif character == "]":
            depth -= 1
            if depth == 0:
                return index
        index += 1
    return None


def parse_destination(text: str, start: int) -> tuple[str, int] | None:
    index = start
    while index < len(text) and text[index].isspace():
        index += 1
    if index >= len(text):
        return None

    characters: list[str] = []
    if text[index] == "<":
        index += 1
        while index < len(text):
            character = text[index]
            if character == "\\" and index + 1 < len(text):
                characters.append(text[index + 1])
                index += 2
                continue
            if character == ">":
                return "".join(characters), index + 1
            if character in "\r\n":
                return None
            characters.append(character)
            index += 1
        return None

    depth = 0
    while index < len(text):
        character = text[index]
        if character == "\\" and index + 1 < len(text):
            characters.append(text[index + 1])
            index += 2
            continue
        if character == "(":
            depth += 1
            characters.append(character)
        elif character == ")":
            if depth == 0:
                break
            depth -= 1
            characters.append(character)
        elif character.isspace() and depth == 0:
            break
        else:
            characters.append(character)
        index += 1
    if not characters or depth != 0:
        return None
    return "".join(characters), index


def normalize_reference(label: str) -> str:
    return re.sub(r"\s+", " ", label.strip()).casefold()


def reference_definitions(text: str) -> tuple[dict[str, str], str]:
    definitions: dict[str, str] = {}
    scan_lines: list[str] = []
    for line in text.splitlines(keepends=True):
        match = REFERENCE_DEFINITION_RE.match(line.rstrip("\r\n"))
        if not match:
            scan_lines.append(line)
            continue
        parsed = parse_destination(match.group(2), 0)
        if parsed:
            definitions.setdefault(normalize_reference(match.group(1)), parsed[0])
        scan_lines.append("".join("\n" if character == "\n" else " " for character in line))
    return definitions, "".join(scan_lines)


def skip_code_span(text: str, start: int) -> int:
    delimiter_length = 1
    while start + delimiter_length < len(text) and text[start + delimiter_length] == "`":
        delimiter_length += 1
    delimiter = "`" * delimiter_length
    closing = text.find(delimiter, start + delimiter_length)
    return len(text) if closing == -1 else closing + delimiter_length


def extract_markdown_targets(text: str) -> list[str]:
    definitions, scan_text = reference_definitions(text)
    targets: list[str] = []
    index = 0
    while index < len(scan_text):
        if scan_text[index] == "\\" and index + 1 < len(scan_text):
            index += 2
            continue
        if scan_text[index] == "`":
            index = skip_code_span(scan_text, index)
            continue

        bracket = index + 1 if scan_text[index] == "!" and index + 1 < len(scan_text) else index
        if scan_text[bracket] != "[":
            index += 1
            continue
        closing = find_closing_bracket(scan_text, bracket)
        if closing is None:
            index += 1
            continue

        label = scan_text[bracket + 1 : closing]
        following = closing + 1
        if following < len(scan_text) and scan_text[following] == "(":
            parsed = parse_destination(scan_text, following + 1)
            if parsed:
                targets.append(parsed[0])
                index = max(parsed[1] + 1, following + 1)
                continue
        elif following < len(scan_text) and scan_text[following] == "[":
            reference_closing = find_closing_bracket(scan_text, following)
            if reference_closing is not None:
                reference = scan_text[following + 1 : reference_closing] or label
                target = definitions.get(normalize_reference(reference))
                if target:
                    targets.append(target)
                index = reference_closing + 1
                continue
        else:
            target = definitions.get(normalize_reference(label))
            if target:
                targets.append(target)
        index = closing + 1
    return targets


def check_parser_contract(project_root: Path, errors: list[str]) -> None:
    fixture = project_root / PARSER_FIXTURE
    try:
        text = fixture.read_text(encoding="utf-8")
    except OSError as exc:
        errors.append(f"cannot read Markdown parser fixture: {exc}")
        return
    targets = extract_markdown_targets(text)
    expected = [PARSER_FIXTURE_TARGET] * 3
    if targets != expected:
        errors.append(f"Markdown parser fixture targets {targets!r}; expected {expected!r}")


def tracked_markdown(project_root: Path, errors: list[str]) -> list[Path]:
    result = subprocess.run(
        ["git", "ls-files", "--", "*.md"],
        cwd=project_root,
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        errors.append(f"git ls-files Markdown failed: {result.stderr.strip() or result.returncode}")
        return []
    return [project_root / line.strip() for line in result.stdout.splitlines() if line.strip()]


def local_target(raw_target: str) -> str | None:
    target = raw_target[1:-1] if raw_target.startswith("<") and raw_target.endswith(">") else raw_target
    if target.startswith("#"):
        return None
    split = urlsplit(target)
    if split.scheme.lower() in {"http", "https"}:
        return None
    if split.scheme:
        return None
    return unquote(split.path)


def check_links(project_root: Path, markdown_files: list[Path], errors: list[str]) -> None:
    for source in markdown_files:
        try:
            text = source.read_text(encoding="utf-8")
        except OSError as exc:
            errors.append(f"cannot read {source.relative_to(project_root)}: {exc}")
            continue
        for raw_target in extract_markdown_targets(text):
            target = local_target(raw_target)
            if not target:
                continue
            resolved = (source.parent / target).resolve()
            try:
                resolved.relative_to(project_root)
            except ValueError:
                errors.append(
                    f"{source.relative_to(project_root)} links outside the project: {raw_target}"
                )
                continue
            if not resolved.exists():
                errors.append(
                    f"broken local link in {source.relative_to(project_root)}: {raw_target}"
                )


def check_current_destinations(project_root: Path, errors: list[str]) -> None:
    active_text: list[str] = []
    for relative in ACTIVE_DOCUMENTS:
        path = project_root / relative
        if not path.is_file():
            errors.append(f"missing active document: {relative}")
            continue
        try:
            active_text.append(path.read_text(encoding="utf-8"))
        except OSError as exc:
            errors.append(f"cannot read active document {relative}: {exc}")
    combined = "\n".join(active_text)
    for destination in CURRENT_DESTINATIONS:
        if not (project_root / destination).is_file():
            errors.append(f"missing current documentation destination: {destination}")
        if destination not in combined:
            errors.append(f"active documents do not reference {destination}")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--project-root", required=True, type=Path)
    args = parser.parse_args()
    project_root = args.project_root.resolve()
    errors: list[str] = []

    check_parser_contract(project_root, errors)
    check_links(project_root, tracked_markdown(project_root, errors), errors)
    check_current_destinations(project_root, errors)

    if errors:
        for error in errors:
            print(f"[FAIL] {error}", file=sys.stderr)
        return 1
    print("[PASS] tracked Markdown local links and current destinations are valid")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
