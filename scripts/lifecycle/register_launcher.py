#!/usr/bin/env python3
"""Launch a Windows process and register its PID in the stack manifest at creation time."""

from __future__ import annotations

import argparse
import shlex
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from lifecycle.stack_manifest import load_manifest, save_manifest  # noqa: E402
from lifecycle.stack_ownership import register_process  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--manifest", required=True, type=Path)
    parser.add_argument("--role", required=True)
    parser.add_argument("--command-line", required=True)
    parser.add_argument("--file-path", required=True)
    parser.add_argument("--arguments", default="")
    parser.add_argument("--working-directory", default=".")
    parser.add_argument("--pid-file", type=Path, default=None)
    argv = sys.argv[1:]
    # argparse rejects option-like values (e.g. --arguments "-cmd=x"); convert to
    # the equals form so the raw argument string is preserved as a single value.
    for index, token in enumerate(argv):
        if token == "--arguments" and index + 1 < len(argv):
            argv = argv[:index] + [f"--arguments={argv[index + 1]}"] + argv[index + 2 :]
            break
    args = parser.parse_args(argv)

    file_name = Path(args.file_path).name.lower()
    creation_flags = subprocess.CREATE_NEW_CONSOLE if file_name == "cmd.exe" else 0
    launch_args = [args.file_path] + shlex.split(args.arguments, posix=False)
    try:
        proc = subprocess.Popen(
            launch_args,
            cwd=args.working_directory or None,
            creationflags=creation_flags,
        )
    except OSError as exc:
        # stdout so for /f callers in batch can surface the failure.
        print(f"[ERROR] failed to launch {args.file_path}: {exc}")
        return 1

    manifest = load_manifest(args.manifest)
    register_process(
        manifest,
        side="windows",
        pid=proc.pid,
        role=args.role,
        name=Path(args.file_path).stem,
        # Register the EXACT command line handed to CreateProcess so identity
        # verification (PID + start-time + command-line fingerprint) matches
        # the process table.
        command_line=subprocess.list2cmdline(launch_args),
        reason="created via register_launcher.py (subprocess.Popen at creation)",
    )
    save_manifest(manifest, args.manifest)
    if args.pid_file:
        args.pid_file.write_text(str(proc.pid), encoding="ascii")
    print(proc.pid)
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:  # noqa: BLE001
        print(f"[ERROR] {exc}")
        raise SystemExit(1)
