"""Process table backends: Windows (CIM), WSL (ps), and a test fake."""

from __future__ import annotations

import subprocess
import re
from dataclasses import dataclass
from typing import List, Optional, Sequence


@dataclass
class ProcessInfo:
    pid: int
    name: str
    start_time_utc: str
    command_line: str
    parent_pid: int
    pgid: Optional[int] = None
    start_time_raw: Optional[str] = None


class FakeProcessTable:
    def __init__(self, processes: Sequence[ProcessInfo]):
        self.processes = list(processes)

    def snapshot(self) -> List[ProcessInfo]:
        return list(self.processes)


def find_by_pid(processes: Sequence[ProcessInfo], pid: int) -> Optional[ProcessInfo]:
    for proc in processes:
        if int(proc.pid) == int(pid):
            return proc
    return None


def find_by_pgid(processes: Sequence[ProcessInfo], pgid: int) -> List[ProcessInfo]:
    return [proc for proc in processes if proc.pgid is not None and int(proc.pgid) == int(pgid)]


def _cim_datetime_to_utc(cim_value: Optional[str]) -> str:
    """Convert a serialized process start time to UTC ISO.

    Handles both `/Date(<epoch-ms>)/` (PowerShell ConvertTo-Json output) and
    WMI CIM datetime (e.g. 20260808120003.123456+480).
    """
    if not cim_value:
        return ""
    text = str(cim_value).strip()
    date_ms = re.fullmatch(r"\\?/Date\((\d+)([+-]\d{4})?\)\\?/", text)
    if date_ms:
        import datetime as dt

        epoch_ms = int(date_ms.group(1))
        return dt.datetime.fromtimestamp(epoch_ms / 1000.0, tz=dt.timezone.utc).strftime(
            "%Y-%m-%dT%H:%M:%SZ"
        )
    m = re.fullmatch(r"(\d{4})(\d{2})(\d{2})(\d{2})(\d{2})(\d{2})(?:\.\d+)?([+-]\d{3,4})?", text)
    if not m:
        return ""
    year, month, day, hour, minute, second, offset = m.groups()
    import datetime as dt

    base = dt.datetime(int(year), int(month), int(day), int(hour), int(minute), int(second))
    if offset:
        sign = 1 if offset[0] == "+" else -1
        minutes = sign * (int(offset[1:3]) * 60 + int(offset[3:5]))
        base = base - dt.timedelta(minutes=minutes)
    return base.replace(tzinfo=dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


class WindowsProcessTable:
    """Enumerate Windows processes via CIM (read-only)."""

    def __init__(self, powershell: str = "powershell.exe"):
        self.powershell = powershell
        self.last_error = None

    def snapshot(self) -> List[ProcessInfo]:
        script = (
            "Get-CimInstance Win32_Process | "
            "Select-Object ProcessId,ParentProcessId,Name,CreationDate,CommandLine | "
            "ConvertTo-Json -Compress"
        )
        try:
            result = subprocess.run(
                [self.powershell, "-NoLogo", "-NoProfile", "-Command", script],
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=60,
            )
        except (subprocess.SubprocessError, OSError) as exc:
            self.last_error = str(exc)
            return []
        if result.returncode != 0:
            self.last_error = f"exit={result.returncode}"
            return []
        import json

        try:
            data = json.loads(result.stdout)
        except json.JSONDecodeError:
            self.last_error = "invalid JSON"
            return []
        self.last_error = None
        if isinstance(data, dict):
            data = [data]
        processes: List[ProcessInfo] = []
        for item in data or []:
            try:
                processes.append(
                    ProcessInfo(
                        pid=int(item["ProcessId"]),
                        name=str(item.get("Name") or ""),
                        start_time_utc=_cim_datetime_to_utc(item.get("CreationDate")),
                        command_line=str(item.get("CommandLine") or ""),
                        parent_pid=int(item.get("ParentProcessId") or 0),
                    )
                )
            except (TypeError, ValueError, KeyError):
                continue
        return processes


class WslProcessTable:
    """Enumerate WSL processes via `ps` (read-only)."""

    def __init__(self, distro: str = "RflySim-20.04", wsl: str = "wsl.exe"):
        self.distro = distro
        self.wsl = wsl
        self.last_error = None

    def snapshot(self) -> List[ProcessInfo]:
        command = (
            "ps -eo pid=,ppid=,pgid=,lstart=,args="
        )
        try:
            result = subprocess.run(
                [self.wsl, "-d", self.distro, "-e", "bash", "-lic", command],
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=60,
            )
        except (subprocess.SubprocessError, OSError) as exc:
            self.last_error = str(exc)
            return []
        if result.returncode != 0:
            self.last_error = f"exit={result.returncode}"
            return []
        self.last_error = None
        return parse_wsl_snapshot(result.stdout)


def parse_wsl_snapshot(text: str) -> List[ProcessInfo]:
    import re

    processes: List[ProcessInfo] = []
    observer_command = "ps -eo pid=,ppid=,pgid=,lstart=,args="
    # lstart: "Sat Aug  8 12:00:14 2026" (day right-aligned).
    line_re = re.compile(
        r"^\s*(\d+)\s+(\d+)\s+(\d+)\s+"
        r"([A-Z][a-z]{2})\s+([A-Z][a-z]{2})\s+(\d{1,2})\s+"
        r"(\d{2}:\d{2}:\d{2})\s+(\d{4})\s+(.*)$"
    )
    for line in text.splitlines():
        line = line.rstrip()
        if not line.strip():
            continue
        m = line_re.match(line)
        if not m:
            continue
        pid, ppid, pgid, weekday, month, day, time, year, args = m.groups()
        if args.strip() == observer_command:
            continue
        lstart = f"{weekday} {month} {day:>2} {time} {year}"
        iso = parse_lstart_iso(lstart)
        processes.append(
            ProcessInfo(
                pid=int(pid),
                name=(args.split("/")[-1].split(" ")[0] if args else ""),
                start_time_utc=iso,
                command_line=args.strip(),
                parent_pid=int(ppid),
                pgid=int(pgid),
                start_time_raw=lstart,
            )
        )
    return processes


def parse_lstart_iso(lstart: str) -> str:
    """Parse `ps lstart` text to an ISO UTC string.

    `ps lstart` prints LOCAL time (e.g. "Sat Aug  8 16:12:20 2026"), while
    manifest entries store TRUE UTC. Treating local as UTC would shift every
    WSL process start by the local-UTC offset (8h here) and break PID-reuse
    identity verification. Convert via the system's current local timezone.
    """
    import datetime as dt
    import re

    normalized = re.sub(r"\s+", " ", lstart.strip())
    try:
        parsed = dt.datetime.strptime(normalized, "%a %b %d %H:%M:%S %Y")
    except ValueError:
        return ""
    local_tz = dt.datetime.now().astimezone().tzinfo
    try:
        parsed_local = parsed.replace(tzinfo=local_tz)
        return parsed_local.astimezone(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    except (OverflowError, OSError, ValueError):
        return parsed.strftime("%Y-%m-%dT%H:%M:%SZ")
