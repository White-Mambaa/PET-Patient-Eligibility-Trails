#!/usr/bin/env python3
"""Run the existing NSCLC checker and make a morning report, with one writer."""
import argparse
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
import fcntl
import json
import math
import os
from pathlib import Path
import re
import subprocess
import sys
import time

SCRIPT = "mtp_supervisor_v3.py"
CHECKPOINT = Path("outputs/mtp_completion/nsclc100/dev/plain_ai_qwen_dev_checks_theta95_fallback_exploratory.jsonl")
EXPECTED = 950
ROUNDS = 10
ROUND_ATTEMPTS = 230
RETRY_PREFIX = "Server requests a long wait; resume later. Retry-After="
BUDGET_STOP = "API attempt budget reached; resume from cache"
POLL_SECONDS = 20
REPORT_SECONDS = 300


def saved_rows(root, writer_check=False):
    raw = (root / CHECKPOINT).read_bytes()
    end = raw.rfind(b"\n") + 1
    if writer_check and raw[end:].strip():
        raise ValueError("Checkpoint has an unfinished final line; inspect it before resuming.")
    keys = set()
    for line in raw[:end].splitlines():
        if not line.strip():
            continue
        r = json.loads(line)
        key = int(r["pair_idx"]), int(r["crit_idx"])
        if key in keys:
            raise ValueError("Duplicate checkpoint case ID; inspect the checkpoint before resuming.")
        keys.add(key)
    if len(keys) > EXPECTED:
        raise ValueError("Checkpoint contains more than 950 unique cases.")
    return len(keys)


def processes(root):
    """Find the original supervisor, worker and inhibit wrapper for this project."""
    result = []
    for d in Path("/proc").iterdir():
        if not d.name.isdecimal():
            continue
        try:
            if d.stat().st_uid != os.getuid():
                continue
            argv = [os.fsdecode(a) for a in (d / "cmdline").read_bytes().split(b"\0") if a]
            index = next((i for i, a in enumerate(argv) if os.path.basename(a) == SCRIPT), None)
            if index is None or not any(os.path.basename(a).startswith("python") for a in argv[:index]):
                continue
            if "--root" in argv[index + 1:]:
                pos = argv.index("--root", index + 1)
                declared = Path(argv[pos + 1])
                if not declared.is_absolute():
                    declared = (d / "cwd").resolve() / declared
                if declared.resolve() != root:
                    continue
            elif (d / "cwd").resolve() != root:
                continue
            state = (d / "stat").read_text().rsplit(")", 1)[1].split()[0]
            if state in ("Z", "X"):
                continue
        except (OSError, IndexError, ValueError):
            continue
        log = None
        try:
            target = Path(os.readlink(d / "fd/1"))
            if target.is_absolute() and target.is_file():
                target = target.resolve()
                if target.is_relative_to(root / "outputs"):
                    log = target
        except OSError:
            pass
        result.append((int(d.name), state, log))
    return result


def tail_text(path):
    with path.open("rb") as f:
        f.seek(max(0, os.fstat(f.fileno()).st_size - 32768))
        return f.read().decode("utf-8", errors="replace")


def terminal_stop(text):
    for line in reversed(text.splitlines()):
        s = line.strip()
        if not s or re.fullmatch(r"(?:\S+/)?python[\d.]* failed with exit status \d+\.", s):
            continue
        return s.removeprefix("STOP DETAIL: ") if s.startswith("STOP DETAIL: ") else None
    return None


def cooldown(log, allow_budget=False):
    detail = terminal_stop(tail_text(log))
    age = max(0, time.time() - log.stat().st_mtime)
    if allow_budget and detail == BUDGET_STOP:
        return max(0, 5 - age)
    if not detail or not detail.startswith(RETRY_PREFIX):
        return None
    retry = detail[len(RETRY_PREFIX):].strip()
    try:
        seconds = float(retry)
    except ValueError:
        try:
            dt = parsedate_to_datetime(retry)
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            return max(0, dt.timestamp() + 5 - time.time())
        except (ValueError, TypeError, OverflowError, OSError):
            return None
    return max(0, seconds + 5 - age) if math.isfinite(seconds) and seconds >= 0 else None


def most_recent_run_log(root):
    out = root / "outputs"
    candidates = (
        list(out.glob("mtp_groq_resume_*.log"))
        + list(out.glob("mtp_groq_guard_*.log"))
        + list(out.glob("mtp_overnight/night_*/round_*.log"))
    )
    for p in sorted(candidates, key=lambda x: x.stat().st_mtime_ns, reverse=True):
        text = tail_text(p)
        if re.search(r"(?m)^(STATUS FILE:|Saved: \d+ / 950 \| API attempts:|STOP DETAIL: )", text):
            return p
    return None


def follow_existing(root, end):
    active = processes(root)
    if not active:
        return most_recent_run_log(root), None
    print("Following the checker already running; no second checker launched.", flush=True)
    log = None
    next_report = 0
    while active:
        paths = [p for _, _, p in active if p is not None]
        if paths:
            seen = max(paths, key=lambda x: x.stat().st_mtime_ns)
            if log != seen:
                log = seen
                print(f"Following existing log: {log}", flush=True)
        if any(state in ("T", "t") for _, state, _ in active):
            return None, "Existing checker is paused; it was left in place."
        remaining = end - time.monotonic()
        if remaining <= 0:
            return None, "Overnight window ended; the existing checker was left in place."
        if time.monotonic() >= next_report:
            print(f"Existing checker: {saved_rows(root)} / {EXPECTED} saved.", flush=True)
            next_report = time.monotonic() + REPORT_SECONDS
        time.sleep(min(POLL_SECONDS, remaining))
        active = processes(root)
    if log is None:
        return None, "Existing checker exited without an identifiable log; no automatic restart."
    return log, None


def launch(root, hours, log):
    args = [sys.executable, "-u", str(root / SCRIPT), "--root", str(root), "--hours", str(hours),
            "--max-attempts", str(ROUND_ATTEMPTS), "--max-restarts", "30"]
    env = os.environ.copy()
    env.pop("GROQ_API_KEY", None)
    with log.open("x", encoding="utf-8", buffering=1) as dest:
        with subprocess.Popen(args, cwd=root, env=env, stdin=subprocess.DEVNULL,
                              stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True,
                              encoding="utf-8", errors="replace", bufsize=1) as p:
            for line in p.stdout:
                dest.write(line)
                print(line, end="", flush=True)
            return p.wait()


def overnight(root, run_dir, end):
    log, pause = follow_existing(root, end)
    if saved_rows(root) == EXPECTED:
        return 0, "All 950 checks saved.", 0
    if pause:
        return 2, pause, 0
    if log is None:
        return 2, "No previous supervisor log found; no automatic restart.", 0
    for attempt in range(1, ROUNDS + 1):
        delay = cooldown(log, allow_budget=attempt > 1 or log.name.startswith("round_"))
        if delay is None:
            return 2, f"Latest stop is not a recognised cooldown or resume signal. Inspect {log}.", attempt - 1
        left = end - time.monotonic()
        if delay + 3600 > left:
            return 2, f"Requested cooldown ({math.ceil(delay)}s remaining) does not fit the overnight window.", attempt - 1
        print(f"Waiting {math.ceil(delay)}s before resuming from {saved_rows(root)} / {EXPECTED}.", flush=True)
        if delay > 0:
            time.sleep(delay)
        if processes(root):
            return 2, "A checker started during the wait; it was left in place.", attempt - 1
        saved = saved_rows(root, writer_check=True)
        if saved == EXPECTED:
            return 0, "All 950 checks saved.", attempt - 1
        hours = int((end - time.monotonic()) // 3600)
        if hours < 1:
            return 2, "Overnight time budget reached.", attempt - 1
        log = run_dir / f"round_{attempt:02d}.log"
        print(f"Starting round {attempt}/{ROUNDS}, at most {ROUND_ATTEMPTS} API attempts.", flush=True)
        launch(root, hours, log)
        if saved_rows(root, writer_check=True) == EXPECTED:
            return 0, "All 950 checks saved.", attempt
    return 2, "Overnight attempt cap reached.", ROUNDS


def write_reports(root, run_dir, start, first, reason, rounds, scorer, delivery):
    try:
        finish = saved_rows(root)
    except (OSError, ValueError, KeyError, TypeError):
        finish = None
    data = {"started_at": datetime.fromtimestamp(start).astimezone().isoformat(),
            "finished_at": datetime.now().astimezone().isoformat(), "reason": reason,
            "starting_checks": first,
            "saved_checks": finish, "expected_checks": EXPECTED,
            "new_supervisor_rounds": rounds, "max_additional_api_attempts": ROUNDS * ROUND_ATTEMPTS,
            "scope": "NSCLC exploratory development checker checkpoint"}
    (run_dir / "MORNING_STATUS.json").write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
    print(f"OVERNIGHT RESULT: {finish if finish is not None else 'unavailable'} / {EXPECTED} saved. {reason}",
          flush=True)
    print(f"MORNING SUMMARY: {run_dir / 'MORNING_STATUS.json'}", flush=True)
    for path, subcommand in ((scorer, "score"), (delivery, "report")):
        if path.is_file():
            try:
                code = subprocess.run([sys.executable, str(path), subcommand, "--root", str(root)],
                                      cwd=root, timeout=180).returncode
                if code:
                    print(f"Optional report exited with status {code}: {path.name}", flush=True)
            except (OSError, subprocess.TimeoutExpired) as e:
                print(f"Optional report unavailable: {path.name} ({type(e).__name__})", flush=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path.cwd())
    parser.add_argument("--hours", type=int, default=8, choices=range(2, 25), metavar="2–24")
    args = parser.parse_args()
    root = args.root.resolve()
    downloads = Path(__file__).resolve().parent
    os.umask(0o077)
    try:
        if not (root / SCRIPT).is_file():
            raise ValueError("Existing mtp_supervisor_v3.py not found in project root.")
        with (root / "outputs/.mtp_groq_resume_guard.lock").open("a", encoding="utf-8") as lock:
            try:
                fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError:
                raise ValueError("A cooldown launcher already holds the checker lock; leave it running.") from None
            start = time.time()
            end = time.monotonic() + args.hours * 3600
            run_dir = root / "outputs/mtp_overnight" / datetime.now().strftime("night_%Y%m%d_%H%M%S_%f")
            run_dir.mkdir(parents=True, exist_ok=False)
            first = None
            try:
                first = saved_rows(root)
                print(f"OVERNIGHT WINDOW: {args.hours} hours | saved {first} / {EXPECTED} | new cap {ROUNDS * ROUND_ATTEMPTS}.",
                      flush=True)
                rc, reason, rounds = overnight(root, run_dir, end)
            except (OSError, ValueError, KeyError, TypeError) as e:
                rc, reason, rounds = 2, str(e) if type(e) in (ValueError, FileNotFoundError) else type(e).__name__, None
            write_reports(root, run_dir, start, first, reason, rounds, downloads / "mtp_checker_work.py",
                          downloads / "MTP_TOOL/mtp_week_delivery.py")
            return rc
    except (OSError, ValueError, KeyError, TypeError) as e:
        print("STOP:", str(e) if type(e) in (ValueError, FileNotFoundError) else type(e).__name__, file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
