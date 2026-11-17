#!/usr/bin/env python3
"""Build a timestamped, verifiable ZIP of the REAL files on the user's Ubuntu MTP computer.

Python 3.10+ standard library only. Run from any folder:
  python3 ~/Downloads/build_mtp_neha_submission.py

Archives the project tree (excluding development caches, credentials and model weights),
plus known ChatGPT presentation/handoff artifacts if present in ~/Downloads.
Never invokes Ollama or modifies the source project.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import io
import json
import os
import platform
from datetime import datetime
from pathlib import Path
from zipfile import ZIP_DEFLATED, ZipFile

PROJECT_DIR_DEFAULT = Path.home() / "MTP" / "Akash_Kit"
DOWNLOADS_DIR = Path.home() / "Downloads"

EXCLUDED_DIRS = {
    ".git", ".svn", ".hg", ".venv", "venv", "env", "node_modules",
    "__pycache__", ".pytest_cache", ".mypy_cache", ".ruff_cache",
    ".ipynb_checkpoints", ".cache", ".ollama", "model_weights",
}
EXCLUDED_SUFFIXES = {
    ".pyc", ".pyo", ".pem", ".p12", ".pfx", ".gguf", ".safetensors",
    ".onnx", ".pt", ".pth", ".zip", ".tar", ".gz", ".7z",
}
EXCLUDED_NAMES = {
    ".env", "credentials.json", "service_account.json", "secrets.json",
    "private_key", "id_rsa", "id_ed25519", ".netrc", ".npmrc",
}
DOWNLOAD_NAMES = [
    "MTP_Neha_Chat_Artifacts_14Oct2026.zip",
    "MTP_Progress_Presentation_14Oct2026.pptx",
    "MTP_Progress_Presentation_14Oct2026.pdf",
    "MTP_Presentation_Speaking_Notes_14Oct2026.md",
    "MTP_EXACT_STOP_AND_RESUME_HANDOFF_14OCT2026.md",
    "MTP_44_evidence_based_proposals.csv",
    "MTP_44_annotation_review_notes.md",
]

REQUIRED_OUTPUTS = [
    "outputs/plain_ai_qwen_dev.jsonl",
    "outputs/plain_ai_qwen_sigir_dev.jsonl",
    "outputs/decision_impact/real_priority_analysis.csv",
    "outputs/evidence_checks/real_citation_results.csv",
    "outputs/priority_comparison/priority_rankings.csv",
    "outputs/priority_comparison/equal_budget_summary.csv",
    "outputs/priority_comparison/top10_blinded_annotation.csv",
    "outputs/priority_comparison/top10_baseline_comparison_key.csv",
    "outputs/priority_comparison/evaluation_44_exploratory_20261014_155042_941024/case_level_comparison.csv",
    "outputs/priority_comparison/patient_counterfactual_exploratory_20261014_160609_713057/one_rule_at_a_time.csv",
    "outputs/priority_comparison/independent_adjudication_20261014_155813_331513/blinded_44_case_review.csv",
    "outputs/overnight_audit/evidence_audit.jsonl",
    "outputs/overnight_audit/errors.jsonl",
    "outputs/traps/trap_pilot_verified.jsonl",
]

SUMMARY = """# MTP progress-results package — information for Neha ma'am

Project: **Check What Can Change the Outcome — Targeted Checking of AI Clinical-Trial Screening Decisions**
Evidence date: **14 October 2026**. Package capture time is recorded separately in `CAPTURE_STATUS.json`.

## What was actually run

- Development baseline: **950** NSCLC + **990** SIGIR = **1,940 criterion predictions** on **152 patient–trial pairs**. These are **development** splits, not a finished held-out evaluation.
- Citation-status checker: 1,940 records (earlier counts: 879 PASS, 118 FAIL, 943 NO_EVIDENCE).
- Priority ranking: five strategies (`random`, `confidence`, `citation`, `decision_impact`, `combined`), 9,700 rows in the ranking table.
- Exploratory 44-case annotation sample, selected from strategy top-ten lists: **42 scorable assistant proposals**; **12 baseline–proposal disagreements**. The selection procedure introduces bias.
- Patient-level counterfactual exploration: **12 proposed criterion changes**, **11 simulated pair decisions changed** (1 NOT_ELIGIBLE→ELIGIBLE, 9 NOT_ELIGIBLE→REVIEW, 1 REVIEW→NOT_ELIGIBLE, 1 remained NOT_ELIGIBLE).
- Qwen2.5:7b evidence audit: final runner reported **1,940/1,940** successful model-assisted audits after a one-record schema retry. **A separate final unique-ID integrity check was not shown executed at the presentation freeze**.
- Audit reliability diagnostic on the first **1,939** results: **669 (34.50%)** logically inconsistent judge-suggested truth/verdict mappings. That is internal inconsistency, **not clinical error rate**.

## Major research limitations

- **Zero independently adjudicated criterion truth labels** were confirmed at the freeze.
- AI judge flags / suggestions are **not** independently verified clinical labels.
- The 44-case cohort was selected according to the strategies being compared; equal-budget results in this cohort are **exploratory**, not unbiased proof of superiority.
- **Controlled-trap evaluation, repair-versus-deferral safety study, full six-check validation, and held-out final comparisons remain pending.**
- PC1 and PC2 computer outputs are **NOT** automatically present in an archive produced on `skyee`; see `CAPTURE_STATUS.json` and add separately if needed.
- Sensitive patient notes can occur in `datasets/`, `outputs/` and `labelling/`. **Review permission and recipient before sharing** and use an approved secure channel.

## Files in the archive

`PROJECT/` — the actual on-disk project files captured from this machine; `CHAT_ARTIFACTS/` — optional files from the Downloads folder; `FILE_MANIFEST.csv` — paths, byte sizes and SHA-256 checksums; `CAPTURE_STATUS.json` — capture provenance and missing expected results.

**Do not characterize this as a completed clinical decision-support product.** It is a reproducible **mid-project progress submission**.
"""


def should_skip(rel: Path) -> bool:
    parts = rel.parts
    if any(p in EXCLUDED_DIRS for p in parts[:-1]):
        return True
    name = rel.name
    lower = name.lower()
    if name in EXCLUDED_NAMES or lower.startswith(".env"):
        return True
    if lower.endswith(".private") or rel.suffix.lower() in EXCLUDED_SUFFIXES:
        return True
    # Dotfiles may contain access details; hidden folders and files are excluded.
    if any(p.startswith(".") for p in parts):
        return True
    return False


def iter_project_files(project: Path, only_outputs: bool):
    root = project / "outputs" if only_outputs else project
    if not root.is_dir():
        raise SystemExit(f"Project folder is missing: {root}")
    for walkroot, dirs, files in os.walk(root, followlinks=False):
        wd = Path(walkroot)
        dirs[:] = sorted(
            d for d in dirs
            if d not in EXCLUDED_DIRS
            and not d.startswith(".")
            and not (wd / d).is_symlink()
        )
        for filename in sorted(files):
            p = wd / filename
            rel = p.relative_to(project)
            if not p.is_file() or p.is_symlink() or should_skip(rel):
                continue
            yield p, f"PROJECT/{rel.as_posix()}"


def add_file(zf: ZipFile, p: Path, arcname: str, manifest: list, warnings: list):
    try:
        st_before = p.stat()
        sha = hashlib.sha256()
        total = 0
        with p.open("rb") as fin, zf.open(arcname, mode="w", force_zip64=True) as zout:
            while True:
                chunk = fin.read(1024 * 1024)
                if not chunk:
                    break
                sha.update(chunk)
                total += len(chunk)
                zout.write(chunk)
        st_after = p.stat()
        if st_before.st_size != st_after.st_size or st_before.st_mtime_ns != st_after.st_mtime_ns:
            warnings.append(f"CHANGED WHILE ARCHIVING: {p}")
        manifest.append({
            "archive_path": arcname,
            "source_path": str(p),
            "bytes": total,
            "mtime_local": datetime.fromtimestamp(st_after.st_mtime).isoformat(timespec="seconds"),
            "sha256": sha.hexdigest(),
        })
    except (OSError, RuntimeError) as exc:
        # Incomplete archives are conspicuously marked in the status report.
        warnings.append(f"FAILED TO ADD: {p}: {exc}")


def csv_bytes(records: list) -> bytes:
    out = io.StringIO()
    writer = csv.DictWriter(out, fieldnames=["archive_path", "source_path", "bytes", "mtime_local", "sha256"])
    writer.writeheader()
    writer.writerows(records)
    return out.getvalue().encode("utf-8")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--project", type=Path, default=PROJECT_DIR_DEFAULT, help="Ubuntu project directory")
    parser.add_argument("--outdir", type=Path, default=DOWNLOADS_DIR, help="Where to save ZIP")
    parser.add_argument("--only-outputs", action="store_true", help="Exclude code and datasets (smaller, less reproducible)")
    parser.add_argument("--exclude-downloads", action="store_true", help="Do not include chat/presentation files from ~/Downloads")
    parser.add_argument("--extra", type=Path, action="append", default=[], help="Additional PC1/PC2 report file or folder, ONLY if already copied to this machine")
    args = parser.parse_args()

    project = args.project.expanduser().resolve()
    args.outdir = args.outdir.expanduser().resolve()
    if not project.is_dir():
        raise SystemExit(f"Project not found: {project}")
    args.outdir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    fname = f"MTP_Neha_Maam_{'Outputs_Only' if args.only_outputs else 'Full_Project'}_{stamp}.zip"
    dest = args.outdir / fname
    if dest.is_relative_to(project):
        raise SystemExit("Choose an output directory OUTSIDE the project tree.")

    planned = list(iter_project_files(project, args.only_outputs))
    additions = []
    if not args.exclude_downloads:
        for name in DOWNLOAD_NAMES:
            p = DOWNLOADS_DIR / name
            if p.exists() and p.is_file() and not p.is_symlink():
                additions.append((p, f"CHAT_ARTIFACTS/{name}"))
    for j, requested in enumerate(args.extra, 1):
        source = requested.expanduser().resolve()
        if not source.exists():
            raise SystemExit(f"--extra path does not exist: {source}")
        if source.is_file():
            additions.append((source, f"ADDITIONAL_PC_REPORTS/{j}_{source.name}"))
        elif source.is_dir():
            for root, dirs, files in os.walk(source, followlinks=False):
                wd = Path(root)
                dirs[:] = sorted(d for d in dirs if d not in EXCLUDED_DIRS and not d.startswith(".") and not (wd / d).is_symlink())
                for name in sorted(files):
                    p = wd / name
                    rel = p.relative_to(source)
                    if not p.is_file() or p.is_symlink() or should_skip(rel):
                        continue
                    additions.append((p, f"ADDITIONAL_PC_REPORTS/{j}_{source.name}/{rel.as_posix()}"))

    present_outputs = {p.relative_to(project).as_posix() for p, _ in planned}
    missing = sorted(set(REQUIRED_OUTPUTS) - present_outputs)
    warnings = []
    records = []
    with ZipFile(dest, "x", compression=ZIP_DEFLATED, compresslevel=6, allowZip64=True) as zf:
        for p, arc in planned + additions:
            add_file(zf, p, arc, records, warnings)
        zf.writestr("README_FOR_NEHA.md", SUMMARY)
        zf.writestr("FILE_MANIFEST.csv", csv_bytes(records))
        status = {
            "capture_time_local": datetime.now().astimezone().isoformat(timespec="seconds"),
            "computer_hostname": platform.node(),
            "project_path": str(project),
            "archive_mode": "outputs-only" if args.only_outputs else "full-project",
            "archive_path_on_creator_computer": str(dest),
            "file_count": len(records),
            "missing_expected_outputs": missing,
            "warnings": warnings,
            "source_note": "Files actually present on this machine at collection time; PC1/PC2 require manual add/transfer if not mounted.",
            "model_run_note": "Last reported audit runner 1940/1940; count not newly verified by ZIP builder.",
        }
        zf.writestr("CAPTURE_STATUS.json", json.dumps(status, indent=2) + "\n")

    archive_sha256 = hashlib.sha256()
    with dest.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            archive_sha256.update(chunk)
    digest = archive_sha256.hexdigest()
    digest_path = dest.with_suffix(".zip.sha256")
    digest_path.write_text(f"{digest}  {dest.name}\n", encoding="utf-8")

    with ZipFile(dest, "r") as zf:
        bad = zf.testzip()
        if bad:
            raise SystemExit(f"ZIP CRC validation failed for {bad}")

    print("=== MTP SUBMISSION ARCHIVE CREATED ===")
    print("Archive:", dest)
    print("Size MiB:", round(dest.stat().st_size / 1024 / 1024, 2))
    print("Files archived:", len(records))
    print("Expected output paths missing:", len(missing))
    for missing_path in missing:
        print("  MISSING:", missing_path)
    print("Warnings:", len(warnings))
    for warning in warnings:
        print("  WARNING:", warning)
    print("SHA256:", digest)
    print("Checksum file:", digest_path)
    print("ZIP integrity: PASS")
    print("Source files modified: NO")
    print("Ollama calls: 0")
    print("IMPORTANT: Inspect archive for patient-note privacy before external sharing.")
    if missing:
        print("IMPORTANT: Archive is a real snapshot but NOT all expected outputs were found. Inspect CAPTURE_STATUS.json.")


if __name__ == "__main__":
    main()
