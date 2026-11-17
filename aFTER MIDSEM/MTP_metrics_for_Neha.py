#!/usr/bin/env python3
"""Reproduce MTP DEVELOPMENT screening metrics and audit diagnostics.

Runs offline on the user's existing Akash_Kit directory. No model inference.
Preserves original files; writes outputs to a new timestamped folder.
Does NOT manufacture checker precision/recall without independently adjudicated labels.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
import re
import zipfile
from collections import Counter, defaultdict
from datetime import datetime
from pathlib import Path

DATASETS = {
    "nsclc100": {
        "pred": "outputs/plain_ai_qwen_dev.jsonl",
        "ref": "datasets/nsclc100/nsclc100.csv",
        "expected_rules": 950,
        "expected_pairs": 50,
        "expected_eligible": 25,
        "previous_strict_accuracy": 50.0,
    },
    "sigir204": {
        "pred": "outputs/plain_ai_qwen_sigir_dev.jsonl",
        "ref": "datasets/sigir204/sigir204.csv",
        "expected_rules": 990,
        "expected_pairs": 102,
        "expected_eligible": 49,
        "previous_strict_accuracy": 53.9,
    },
}
TRUTHS = ("ELIGIBLE", "NOT_ELIGIBLE")
PREDICTIONS = ("ELIGIBLE", "NOT_ELIGIBLE", "REVIEW")
TARGET_NAMES = (
    "label", "eligibility", "eligibility_label", "label_eligibility",
    "gold_label", "gold_eligibility", "reference_label", "reference_target",
    "reference_pair_target", "pair_label", "pair_target", "is_eligible",
    "eligible", "target", "ground_truth", "ground_truth_label",
    "gold", "label_pair", "is_eligible_pair", "eligibility_status",
    "actual_eligibility", "eligibility_gold", "trial_eligibility",
)


def read_csv(path):
    with path.open("r", newline="", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        if not reader.fieldnames:
            raise ValueError(f"No header in {path}")
        return list(reader), reader.fieldnames


def read_jsonl(path):
    out = []
    with path.open("r", encoding="utf-8") as f:
        for n, line in enumerate(f, 1):
            if line.strip():
                try:
                    out.append(json.loads(line))
                except json.JSONDecodeError as exc:
                    raise ValueError(f"Invalid JSON at {path}:{n}: {exc}") from exc
    return out


def normalize_ref(value):
    raw = str(value).strip().lower()
    compact = re.sub(r"[^a-z0-9]+", "", raw)
    if compact in {"eligible", "yes", "true", "1", "e", "included", "positive"}:
        return "ELIGIBLE"
    if compact in {"noteligible", "ineligible", "noteligiblepatient", "no", "false", "0", "ne", "excluded", "negative", "noneligible"}:
        return "NOT_ELIGIBLE"
    return None


def pick_target(dataset, fields, rows, override):
    # Only candidates whose nonempty values are ALL parseable binary labels are eligible.
    candidates = []
    ordered = ([override] if override else []) + [f for f in TARGET_NAMES if f != override]
    for name in ordered:
        if name not in fields:
            continue
        raw_values = [str(r.get(name, "")).strip() for r in rows]
        if raw_values and all(v and normalize_ref(v) for v in raw_values):
            candidates.append(name)
        elif override == name:
            example = sorted(set(raw_values))[:15]
            raise ValueError(f"Override {name!r} is not fully usable for {dataset}. Values: {example}")
    if not candidates:
        other = {f: sorted({str(r.get(f, "")).strip() for r in rows})[:12] for f in fields if ("label" in f.lower() or "elig" in f.lower() or "target" in f.lower() or "gold" in f.lower())}
        raise ValueError(
            f"Cannot identify eligible/not eligible reference column for {dataset}. "
            f"CSV columns: {fields}. Relevant column values: {other}. "
            f"Use --{dataset}-target NAME after checking the file schema."
        )
    preferred = candidates[0]
    # Reject conflicting alternatives to avoid accidentally using a criterion rather than pair label.
    selected_values = [normalize_ref(r[preferred]) for r in rows]
    conflicting = [name for name in candidates[1:] if [normalize_ref(r[name]) for r in rows] != selected_values]
    if conflicting:
        raise ValueError(f"Conflicting plausible reference columns for {dataset}: {preferred} vs {conflicting}. Select carefully with --{dataset}-target NAME")
    return preferred


def truth_to_verdict(truth, kind):
    if truth == "unknown":
        return "not_stated"
    if kind == "inclusion":
        return "met" if truth == "yes" else "not_met"
    if kind == "exclusion":
        return "not_met" if truth == "yes" else "met"
    raise ValueError(f"Unexpected criterion kind {kind!r}")


def metric(tp, fp, fn):
    precision = tp / (tp + fp) if tp + fp else 0.0
    recall = tp / (tp + fn) if tp + fn else 0.0
    f1 = 2 * precision * recall / (precision + recall) if precision + recall else 0.0
    return precision, recall, f1


def pc(x):
    return f"{x * 100:.2f}%"


def metrics_for(rows, dataset, ref_column):
    n = len(rows)
    assert n, "No pairs to evaluate"
    matrix = Counter((r["reference"], r["prediction"]) for r in rows)
    assert sum(matrix.values()) == n
    strict_correct = sum(matrix[(c, c)] for c in TRUTHS)
    decided = [r for r in rows if r["prediction"] != "REVIEW"]
    reviewed = n - len(decided)
    conditional_correct = sum(r["prediction"] == r["reference"] for r in decided)
    byclass = []
    total_tp = total_fp = total_fn = 0
    for label in TRUTHS:
        tp = matrix[(label, label)]
        fp = sum(matrix[(other, label)] for other in TRUTHS if other != label)
        fn = sum(matrix[(label, other)] for other in PREDICTIONS if other != label)
        p, rec, f1 = metric(tp, fp, fn)
        byclass.append({
            "dataset": dataset, "class": label, "support": sum(matrix[(label, x)] for x in PREDICTIONS),
            "tp": tp, "fp": fp, "fn_including_review": fn,
            "precision": round(p, 6), "recall_including_review": round(rec, 6),
            "f1_including_review": round(f1, 6),
        })
        total_tp += tp
        total_fp += fp
        total_fn += fn
    macro_f1 = sum(x["f1_including_review"] for x in byclass) / 2
    weighted_f1 = sum(x["f1_including_review"] * x["support"] for x in byclass) / n
    micro_p, micro_r, micro_f1 = metric(total_tp, total_fp, total_fn)
    balanced_accuracy_strict = sum(x["recall_including_review"] for x in byclass) / 2
    out = {
        "dataset": dataset, "reference_column": ref_column,
        "pairs": n, "reference_eligible": sum(r["reference"] == "ELIGIBLE" for r in rows),
        "reference_not_eligible": sum(r["reference"] == "NOT_ELIGIBLE" for r in rows),
        "predicted_eligible": sum(r["prediction"] == "ELIGIBLE" for r in rows),
        "predicted_not_eligible": sum(r["prediction"] == "NOT_ELIGIBLE" for r in rows),
        "predicted_review": reviewed,
        "review_rate": round(reviewed / n, 6),
        "definitive_coverage": round(len(decided) / n, 6),
        "strict_correct": strict_correct,
        "strict_accuracy": round(strict_correct / n, 6),
        "strict_balanced_accuracy": round(balanced_accuracy_strict, 6),
        "strict_macro_f1": round(macro_f1, 6),
        "strict_weighted_f1": round(weighted_f1, 6),
        "strict_micro_precision": round(micro_p, 6),
        "strict_micro_recall": round(micro_r, 6),
        "strict_micro_f1": round(micro_f1, 6),
        "definitive_accuracy": round(conditional_correct / len(decided), 6) if decided else "NA",
        "definitive_correct": conditional_correct,
        "definitive_count": len(decided),
        "false_exclusion_count": matrix[("ELIGIBLE", "NOT_ELIGIBLE")],
        "false_inclusion_count": matrix[("NOT_ELIGIBLE", "ELIGIBLE")],
        "eligible_review_count": matrix[("ELIGIBLE", "REVIEW")],
        "not_eligible_review_count": matrix[("NOT_ELIGIBLE", "REVIEW")],
    }
    confusion = [{"dataset": dataset, "actual": ref, "predicted": pred, "count": matrix[(ref, pred)]} for ref in TRUTHS for pred in PREDICTIONS]
    return out, byclass, confusion


def audit_check(root, expected_rule_keys):
    path = root / "outputs/overnight_audit/evidence_audit.jsonl"
    if not path.exists():
        return None
    rows = read_jsonl(path)
    observed = [(str(r["dataset"]), int(r["pair_idx"]), int(r["crit_idx"])) for r in rows]
    unique = set(observed)
    if len(rows) != len(unique) or unique != expected_rule_keys:
        raise ValueError(f"Audit key mismatch: total={len(rows)}, unique={len(unique)}, missing={len(expected_rule_keys - unique)}, extra={len(unique - expected_rule_keys)}")
    baseline = {}
    for ds, d in DATASETS.items():
        for r in read_jsonl(root / d["pred"]):
            baseline[(str(r["dataset"]), int(r["pair_idx"]), int(r["crit_idx"]))] = r
    invalid = 0
    flagged = Counter()
    support = Counter()
    missed_unchanged_unknown = 0
    for r in rows:
        k = (r["dataset"], int(r["pair_idx"]), int(r["crit_idx"]))
        a = r["audit"]
        b = baseline[k]
        judge_truth = a["suggested_truth"]
        judge_verdict = a["suggested_verdict"]
        if judge_truth not in {"yes", "no", "unknown"} or judge_verdict != truth_to_verdict(judge_truth, b["kind"]):
            invalid += 1
        support[a.get("support", "MISSING")] += 1
        for field in ("context_issue", "logic_issue", "contradiction_issue", "missed_evidence_issue"):
            if a.get(field) == "yes":
                flagged[field] += 1
        if a.get("missed_evidence_issue") == "yes" and judge_truth == b["truth"] == "unknown":
            missed_unchanged_unknown += 1
        if a.get("needs_human_review") is True:
            flagged["needs_human_review"] += 1
    return {
        "audit_rows": len(rows), "audit_unique_ids": len(unique),
        "invalid_judge_truth_verdict_mappings": invalid,
        "invalid_judge_mapping_fraction": round(invalid / len(rows), 6),
        "missed_evidence_yes_and_both_unknown": missed_unchanged_unknown,
        "support_counts": dict(sorted(support.items())),
        "flag_yes_counts": dict(sorted(flagged.items())),
        "clinical_checker_accuracy": "NOT AVAILABLE: no independent criterion-level ground truth",
    }


def save_csv(path, rows):
    if not rows:
        return
    with path.open("x", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def create_report(summary, class_metrics, confusion, audit, root, output):
    lines = [
        "# MTP — Verified-from-files development baseline metrics for Neha Ma'am",
        "",
        "**Run timestamp:** " + datetime.now().strftime("%Y-%m-%d %H:%M:%S local"),
        "**Experiment:** Development splits only; local Qwen2.5:7b baseline. No new model inference.",
        "",
        "## Baseline performance",
        "",
        "| Dataset | Pairs | Correct (strict) | Strict accuracy | Balanced accuracy | Macro F1 | Weighted F1 | REVIEW rate | Accuracy on definite decisions |",
        "|---|---:|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for x in summary:
        def_acc = "NA" if x["definitive_accuracy"] == "NA" else pc(x["definitive_accuracy"])
        lines.append(f"| {x['dataset']} | {x['pairs']} | {x['strict_correct']} | {pc(x['strict_accuracy'])} | {pc(x['strict_balanced_accuracy'])} | {pc(x['strict_macro_f1'])} | {pc(x['strict_weighted_f1'])} | {pc(x['review_rate'])} | {def_acc} ({x['definitive_count']} definite) |")
    lines.extend(["", "**How REVIEW is handled:** The gold labels are binary (Eligible and Not Eligible), while the screening system may output REVIEW. Strict accuracy counts REVIEW as not correct; class recall counts a REVIEW for that class as a false negative; precision has no REVIEW false-positive contribution. Accuracy on definite decisions excludes REVIEW and MUST be accompanied by coverage. This distinction matters because a high abstention rate can make conditional accuracy look better.", "", "## Strict two-by-three confusion matrices", ""])
    for item in summary:
        ds = item["dataset"]
        cnt = {(r["actual"],r["predicted"]):r["count"] for r in confusion if r["dataset"] == ds}
        lines.extend([
            f"### {ds}",
            "", "| Reference label | Predicted ELIGIBLE | Predicted NOT_ELIGIBLE | Predicted REVIEW | Total |",
            "|---|---:|---:|---:|---:|",
        ])
        for label in TRUTHS:
            vals = [cnt[(label, pred)] for pred in PREDICTIONS]
            lines.append(f"| {label} | {vals[0]} | {vals[1]} | {vals[2]} | {sum(vals)} |")
        lines.extend(["", f"Reference-eligible automatic rejections: **{item['false_exclusion_count']}**; reference-not-eligible automatic inclusions: **{item['false_inclusion_count']}**; review decisions: **{item['predicted_review']}**.", ""])
    lines.extend(["## Class-specific precision, recall and F1", "", "| Dataset | Class | Support | Precision | Recall (REVIEW missed) | F1 |", "|---|---|---:|---:|---:|---:|"])
    for c in class_metrics:
        lines.append(f"| {c['dataset']} | {c['class']} | {c['support']} | {pc(c['precision'])} | {pc(c['recall_including_review'])} | {pc(c['f1_including_review'])} |")
    lines.extend(["", "## Evidence-audit diagnostics (NOT clinical checker accuracy)", ""])
    if audit:
        lines.extend([
            f"- Audit records matched to the **1,940 original criterion predictions**: **{audit['audit_rows']}**.",
            f"- Inconsistent judge truth-to-verdict pairs: **{audit['invalid_judge_truth_verdict_mappings']}/{audit['audit_rows']} ({pc(audit['invalid_judge_mapping_fraction'])})**.",
            f"- Missed-evidence flags with both baseline and judge truth unknown: **{audit['missed_evidence_yes_and_both_unknown']}**.",
            "- Support-value counts: " + ", ".join(f"{key}={v}" for key,v in audit["support_counts"].items()) + ".",
            "- AI judge flag counts: " + ", ".join(f"{key}={v}" for key,v in audit["flag_yes_counts"].items()) + ".",
        ])
    else:
        lines.append("- Complete evidence audit not available. No checker performance results calculated.")
    lines.extend([
        "", "## Checker / proposed method — metrics not yet established", "",
        "**Independent criterion-level adjudications available: 0 at the project freeze.**",
        "Therefore, verified precision, recall, specificity, sensitivity, F1 and MCC for the six proposed evidence checks cannot be computed reliably from the available development artifacts. AI-vs-AI disagreements, judge flags and counterfactual simulation outcomes are NOT accuracy or precision measurements.",
        "", "### Exploratory findings to keep separate from baseline metrics", "",
        "- Forty-four deliberately selected cases were given assistant-proposed labels (42 with yes/no/unknown and 2 deferred). Twelve proposals disagreed with the baseline predictions.",
        "- Equal-budget within these selected cases (top 10 each): random=1, confidence=0, citation=1, decision impact=7, combined=6 assistant-baseline disagreements. **The cohort is selection-biased and not independent error-detection evaluation.**",
        "- Replacing the 12 disputed rule answers hypothetically changed 11 pair decisions: 1 rejected→eligible, 9 rejected→review, 1 review→rejected; 1 remained rejected. **Not verified patient rescues.**",
        "- Running the same Qwen2.5:7b family as screening model and judge does not create independent clinical gold-standard labels.",
        "", "## Reproducibility / limitations", "",
        "- This report uses only existing development-model predictions and the source datasets' pair-level reference labels. It does not use the held-out test split.",
        "- The strict-label convention and evaluation averaging should be stated whenever metrics are quoted; `REVIEW` is explicitly not counted as a correct class.",
        "- The source datasets' patient–trial labels are reference labels, not necessarily independently verified clinical truth for each criterion.",
        "- The script did not change any input dataset, model prediction, or audit file, and made no Ollama calls.",
        "- The raw patient notes are intentionally NOT included in this metrics ZIP. Separate approval may be required before sharing any note-level data.",
        "", "## Files in this report", "",
        "- `baseline_performance.csv` — one row per dataset with aggregate performance and coverage.",
        "- `baseline_confusion_matrix.csv` — all two-by-three counts per dataset.",
        "- `baseline_class_metrics.csv` — class-wise TP/FP/FN, precision, recall, F1.",
        "- `baseline_pair_predictions.csv` — per-pair reference and model decisions, without clinical notes.",
        "- `audit_summary.json` — full-run judge diagnostics, if available.",
        "- `SHA256SUMS.txt` — checksums of reported files.",
    ])
    (output / "NEHA_PERFORMANCE_REPORT.md").write_text("\n".join(lines)+"\n", encoding="utf-8")


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--root", default=".")
    ap.add_argument("--nsclc100-target", default="")
    ap.add_argument("--sigir204-target", default="")
    args = ap.parse_args()
    root = Path(args.root).expanduser().resolve()
    all_summary, all_class, all_confusion, all_pairs = [], [], [], []
    all_baseline_keys = set()
    for ds, cfg in DATASETS.items():
        predicted = read_jsonl(root / cfg["pred"])
        if len(predicted) != cfg["expected_rules"]:
            raise ValueError(f"{ds}: expected {cfg['expected_rules']} dev rule predictions; found {len(predicted)}")
        groups = defaultdict(dict)
        for r in predicted:
            if str(r["dataset"]) != ds:
                raise ValueError(f"Prediction dataset mismatch: {r}")
            pair, crit = int(r["pair_idx"]), int(r["crit_idx"])
            key = (ds,pair,crit)
            if key in all_baseline_keys:
                raise ValueError(f"Duplicate baseline prediction {key}")
            all_baseline_keys.add(key)
            if crit in groups[pair]:
                raise ValueError(f"Duplicate criterion {key}")
            kind, truth, verdict = r["kind"], r["truth"], r["verdict"]
            if truth not in ("yes", "no", "unknown") or verdict != truth_to_verdict(truth, kind):
                raise ValueError(f"Baseline truth/verdict inconsistency at {key}: {truth} / {verdict} / {kind}")
            groups[pair][crit] = verdict
        if len(groups) != cfg["expected_pairs"]:
            raise ValueError(f"{ds}: expected {cfg['expected_pairs']} dev pairs; found {len(groups)}")
        src_rows, fields = read_csv(root / cfg["ref"])
        if "pair_idx" not in fields:
            raise ValueError(f"{ds}: reference data is missing pair_idx; columns={fields}")
        override = getattr(args, ds + "_target")
        target_col = pick_target(ds, fields, src_rows, override)
        references = {}
        for r in src_rows:
            pid = int(r["pair_idx"])
            label = normalize_ref(r[target_col])
            if pid in references and references[pid] != label:
                raise ValueError(f"{ds}: contradictory reference target for pair {pid}")
            references[pid] = label
        if set(groups) - set(references):
            raise ValueError(f"{ds}: {len(set(groups)-set(references))} prediction pairs not in reference dataset: {sorted(set(groups)-set(references))[:8]}")
        rows = []
        for pair, verdicts in sorted(groups.items()):
            counts = Counter(verdicts.values())
            predicted_label = "NOT_ELIGIBLE" if counts["not_met"] else "REVIEW" if counts["not_stated"] else "ELIGIBLE"
            rows.append({
                "dataset": ds, "pair_idx": pair,
                "reference": references[pair], "prediction": predicted_label,
                "criterion_count": len(verdicts),
                "num_met": counts["met"],
                "num_not_met": counts["not_met"],
                "num_not_stated": counts["not_stated"],
                "strict_correct": int(references[pair] == predicted_label),
            })
        eligibles = sum(r["reference"] == "ELIGIBLE" for r in rows)
        if eligibles != cfg["expected_eligible"]:
            raise ValueError(f"{ds}: chosen reference column {target_col} produces {eligibles} development eligible pairs; previous validated count is {cfg['expected_eligible']}. STOP and inspect source labels before reporting.")
        summary, classes, confusion = metrics_for(rows, ds, target_col)
        summary["criterion_predictions"] = len(predicted)
        expected = cfg["previous_strict_accuracy"]
        if abs(summary["strict_accuracy"]*100 - expected) > 0.15:
            summary["previous_report_mismatch"] = f"YES: earlier {expected:.1f}% vs regenerated {summary['strict_accuracy']*100:.2f}%"
        else:
            summary["previous_report_mismatch"] = "NO"
        all_summary.append(summary)
        all_class.extend(classes)
        all_confusion.extend(confusion)
        all_pairs.extend(rows)
    if len(all_baseline_keys) != 1940 or len(all_pairs) != 152:
        raise ValueError("Unexpected cross-dataset evaluation counts")
    audit = audit_check(root, all_baseline_keys)
    output = root / "outputs" / ("neha_metrics_"+ datetime.now().strftime("%Y%m%d_%H%M%S_%f"))
    output.mkdir(parents=True, exist_ok=False)
    save_csv(output / "baseline_performance.csv", all_summary)
    save_csv(output / "baseline_class_metrics.csv", all_class)
    save_csv(output / "baseline_confusion_matrix.csv", all_confusion)
    save_csv(output / "baseline_pair_predictions.csv", all_pairs)
    (output / "audit_summary.json").write_text(json.dumps(audit or {"available": False}, indent=2)+"\n", encoding="utf-8")
    create_report(all_summary, all_class, all_confusion, audit, root, output)
    files = sorted(p for p in output.iterdir() if p.is_file())
    checksum = "\n".join(f"{hashlib.sha256(p.read_bytes()).hexdigest()}  {p.name}" for p in files)+"\n"
    (output / "SHA256SUMS.txt").write_text(checksum, encoding="utf-8")
    zip_path = output / "NEHA_MTP_METRICS_RESULTS.zip"
    with zipfile.ZipFile(zip_path,"x",compression=zipfile.ZIP_DEFLATED) as z:
        for path in sorted(output.iterdir()):
            if path.is_file() and path != zip_path:
                z.write(path, arcname=path.name)
    with zipfile.ZipFile(zip_path) as z:
        invalid = z.testzip()
        if invalid:
            raise ValueError(f"ZIP integrity failure: {invalid}")
    print("=== MTP PERFORMANCE METRICS FOR NEHA MA'AM ===")
    for s in all_summary:
        print(f"{s['dataset']}: {s['pairs']} pairs; strict accuracy={pc(s['strict_accuracy'])}; balanced accuracy={pc(s['strict_balanced_accuracy'])}; macro F1={pc(s['strict_macro_f1'])}; weighted F1={pc(s['strict_weighted_f1'])}")
        print(f"  REVIEW={s['predicted_review']}/{s['pairs']} ({pc(s['review_rate'])}); definitive accuracy={'NA' if s['definitive_accuracy']=='NA' else pc(s['definitive_accuracy'])}; false exclusions={s['false_exclusion_count']}; false inclusions={s['false_inclusion_count']}")
        print(f"  Reference column: {s['reference_column']}; discrepancy vs earlier report: {s['previous_report_mismatch']}")
    if audit:
        print(f"Evidence audit: {audit['audit_rows']}/1940, inconsistent judge mappings: {audit['invalid_judge_truth_verdict_mappings']} ({pc(audit['invalid_judge_mapping_fraction'])})")
    print("Checker accuracy: NOT AVAILABLE without independent criterion labels")
    print("REPORT:", output / "NEHA_PERFORMANCE_REPORT.md")
    print("ZIP:", zip_path)
    print("Input files modified: NO; Ollama calls: 0")


if __name__ == "__main__":
    main()
