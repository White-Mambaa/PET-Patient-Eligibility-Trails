#!/usr/bin/env python3
"""Run the EXISTING local MTP evidence judge on the 3 verified trap predictions.

No changes to original project Python code or 1,940-row evidence audit.
An --inspect mode reveals candidate field lengths without disclosing patient notes.
"""
from __future__ import annotations
import argparse
import json
import runpy
import sys
from collections import Counter
from datetime import datetime
from pathlib import Path

FLAGS = ("context_issue", "logic_issue", "contradiction_issue", "missed_evidence_issue")


def read_jsonl(path: Path) -> list[dict]:
    if not path.is_file():
        raise FileNotFoundError(f"Required file missing: {path}")
    rows = []
    with path.open(encoding="utf-8") as f:
        for n, line in enumerate(f, 1):
            if line.strip():
                try:
                    value = json.loads(line)
                except json.JSONDecodeError as e:
                    raise ValueError(f"{path}:{n}: {e}") from e
                if not isinstance(value, dict):
                    raise ValueError(f"{path}:{n}: JSON object expected")
                rows.append(value)
    return rows


def index(rows: list[dict], field: str, origin: str) -> dict[int, dict]:
    result = {}
    for r in rows:
        k = int(r[field])
        if k in result:
            raise ValueError(f"Duplicate {origin} key {field}={k}")
        result[k] = r
    return result


def yes_value(value: object) -> bool:
    return str(value).strip().lower() in ("yes", "true", "1")


def validate(traps: list[dict], predictions: list[dict]):
    by_trap = index(traps, "case_idx", "trap")
    by_prediction = index(predictions, "pair_idx", "prediction")
    if set(by_trap) != set(by_prediction):
        raise ValueError(
            f"Trap/prediction case IDs differ. Traps: {sorted(by_trap)}; "
            f"predictions: {sorted(by_prediction)}"
        )
    if len(by_trap) != 3:
        raise ValueError(f"Expected exactly 3 controlled-trap pilot cases, got {len(by_trap)}")
    for case_idx in by_trap:
        trap, pred = by_trap[case_idx], by_prediction[case_idx]
        if int(trap["crit_idx"]) != int(pred["crit_idx"]):
            raise ValueError(f"Criterion index mismatch at case {case_idx}")
        if trap["kind"] != pred["kind"]:
            raise ValueError(f"Rule kind mismatch at case {case_idx}")
        if not yes_value(trap.get("checked_by_hand")):
            raise ValueError(f"Trap {case_idx} lacks confirmed checked_by_hand=true")
        if not yes_value(pred.get("parse_ok")):
            raise ValueError(f"Prediction {case_idx} did not parse successfully")
        expected = str(trap["expected_truth_after"]).strip().lower()
        if expected not in ("yes", "no", "unknown"):
            raise ValueError(f"Unsupported expected_truth_after={expected!r} at {case_idx}")
    return by_trap, by_prediction


def summarize_record(rec: dict) -> str:
    a = rec["audit"]
    return (
        f"case={rec['case_idx']} trap={rec['trap_type']} "
        f"correct_baseline={rec['baseline_truth_correct']} "
        f"support={a.get('support')} "
        + " ".join(f"{k}={a.get(k)}" for k in FLAGS)
        + f" judge_mapping_inconsistent={rec['judge_mapping_inconsistent']}"
    )


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--root", type=Path, default=Path.cwd(), help="MTP/Akash_Kit project root")
    p.add_argument("--inspect", action="store_true", help="Show note/text field lengths; no inference")
    p.add_argument("--note-field", choices=("note", "text"), help="Verified full altered patient-note field")
    p.add_argument("--model", help="Optional JUDGE_MODEL: configure via environment before launching")
    args = p.parse_args()
    root = args.root.expanduser().resolve()
    folder = root / "outputs" / "traps"
    traps = read_jsonl(folder / "trap_pilot_verified.jsonl")
    preds = read_jsonl(folder / "trap_pilot_predictions.jsonl")
    by_trap, by_pred = validate(traps, preds)

    print("=== MTP CONTROLLED-TRAP EVIDENCE-JUDGE EXPERIMENT ===", flush=True)
    print("Cases:", len(by_trap), flush=True)
    for i in sorted(by_trap):
        r = by_trap[i]
        print(f"Case {i}, {r['trap_type']}: "
              f"note chars={len(str(r.get('note') or ''))}; "
              f"text chars={len(str(r.get('text') or ''))}", flush=True)
    if args.inspect:
        print("INSPECTION ONLY. No calls; no files modified.")
        print("Inspect experiments/create_trap_pilot.py to identify which field is the FULL ALTERED PATIENT NOTE.")
        return
    if not args.note_field:
        p.error("Please select --note-field note or --note-field text after verifying the generator source. Start with --inspect.")

    sys.path.insert(0, str((root / "code").resolve()))
    from criteria import map_truth

    module_path = root / "experiments" / "overnight_evidence_audit.py"
    if not module_path.is_file():
        raise FileNotFoundError(module_path)
    # run_path uses __name__='<run_path>', so its if __name__ == '__main__' is NOT executed.
    # We use the project judge() directly; we never call the original main().
    module = runpy.run_path(str(module_path))
    judge = module.get("judge")
    if not callable(judge):
        raise RuntimeError("Existing evidence audit did not expose judge(record, note)")
    model_name = module.get("MODEL", "unspecified")
    if args.model and args.model != model_name:
        raise ValueError(f"Configured model {model_name!r} does not match requested {args.model!r}. Set JUDGE_MODEL before running.")

    output = folder / "trap_pilot_evidence_audit.jsonl"
    existing_rows = read_jsonl(output) if output.exists() else []
    completed = index(existing_rows, "case_idx", "saved audit")
    if set(completed) - set(by_trap):
        raise ValueError("Saved audit contains unknown case indices; refusing to append")
    print("Existing completed:", len(completed), flush=True)
    print("Judge model:", model_name, flush=True)
    print("Output:", output, flush=True)
    print("Original 1,940-record audit is untouched.", flush=True)

    # Create the new output file only after all preflight checks succeed.
    with output.open("a", encoding="utf-8") as f:
        for i in sorted(by_trap):
            if i in completed:
                print("SKIP previously audited case", i, flush=True)
                continue
            trap = by_trap[i]
            pred = by_pred[i]
            note = trap.get(args.note_field)
            if not isinstance(note, str) or len(note.strip()) < 40:
                raise ValueError(f"Case {i}: selected {args.note_field!r} is not a full patient note; "
                                 "inspect the trap generator before proceeding")
            truth = str(trap["expected_truth_after"]).strip().lower()
            expected_verdict = map_truth(truth, trap["kind"])
            baseline_truth_correct = str(pred["truth"]).strip().lower() == truth
            baseline_verdict_correct = str(pred["verdict"]).strip().lower() == expected_verdict
            print(f"AUDITING case={i} type={trap['trap_type']} ...", flush=True)
            audit = judge(pred, note)
            if not isinstance(audit, dict):
                raise RuntimeError(f"Case {i}: judge returned {type(audit).__name__}, expected object")
            suggested_truth = str(audit.get("suggested_truth", "unknown")).strip().lower()
            derived = map_truth(suggested_truth, trap["kind"])
            proposed = str(audit.get("suggested_verdict", "")).strip().lower()
            record = {
                "case_idx": i,
                "trap_id": trap.get("trap_id"),
                "trap_type": trap.get("trap_type"),
                "crit_idx": int(pred["crit_idx"]),
                "kind": trap["kind"],
                "checked_by_hand": True,
                "reference_truth": truth,
                "reference_verdict": expected_verdict,
                "baseline_truth": str(pred["truth"]).strip().lower(),
                "baseline_verdict": str(pred["verdict"]).strip().lower(),
                "baseline_truth_correct": baseline_truth_correct,
                "baseline_verdict_correct": baseline_verdict_correct,
                "judge_model": model_name,
                "audit_type": "AI_PRELIMINARY_TRAP",
                "audit": audit,
                "derived_judge_verdict": derived,
                "judge_mapping_inconsistent": derived != proposed,
                "note_field_used": args.note_field,
                "created_at": datetime.now().astimezone().isoformat(),
            }
            f.write(json.dumps(record, ensure_ascii=False) + "\n")
            f.flush()
            completed[i] = record
            print("SAVED", summarize_record(record), flush=True)

    print("\n=== PILOT SUMMARY ===")
    print("Completed cases:", len(completed), "/", len(by_trap))
    print("Baseline truth correct:", sum(bool(x['baseline_truth_correct']) for x in completed.values()))
    print("Baseline verdict correct:", sum(bool(x['baseline_verdict_correct']) for x in completed.values()))
    for key in ("support",) + FLAGS:
        count = Counter(str(x["audit"].get(key, "MISSING")).lower() for x in completed.values())
        print(f"{key}: {dict(count)}")
    print("Judge mapping inconsistencies:", sum(bool(x['judge_mapping_inconsistent']) for x in completed.values()))
    print("WARNING: These are preliminary judge flags, not verified checker TP/FP counts.")
    print("OUTPUT:", output)
    print("Original baseline predictions and original 1,940-record audit modified: NO")


if __name__ == "__main__":
    main()
