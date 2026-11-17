#!/usr/bin/env python3
"""New development jobs for Akash_Kit. Run with the project's .venv/bin/python."""
import argparse
from collections import Counter
from contextlib import contextmanager
import csv
from datetime import datetime
import fcntl
import hashlib
import json
import os
from pathlib import Path
import random
import sys
import urllib.request

MODEL = "qwen2.5:7b"
SIZES = {"nsclc100": (50, 950), "sigir204": (102, 990)}
DECISIONS = ("ELIGIBLE", "REVIEW", "NOT_ELIGIBLE")
LEGACY_PRED = "outputs/plain_ai_qwen_dev.jsonl"
LEGACY_CHECKS = (
    "outputs/mtp_completion/nsclc100/dev/"
    "plain_ai_qwen_dev_checks_theta95_fallback_exploratory.jsonl"
)
PILOT = "outputs/mtp_next_jobs/nsclc_reask_pilot"
SUBJECT_OPTIONS = {"temperature": 0, "seed": 0, "num_ctx": 8192, "num_predict": 400}
PAIR_SOURCE_KEYS = ("corpus_sha256", "criteria_sha256", "splits_sha256")


def read_json(path):
    return json.loads(path.read_text(encoding="utf-8"))


def atomic(path, value):
    temporary = path.with_name(path.name + ".tmp")
    with temporary.open("w", encoding="utf-8") as f:
        json.dump(value, f, indent=2, ensure_ascii=False, allow_nan=False)
        f.write("\n")
        f.flush()
        os.fsync(f.fileno())
    temporary.replace(path)


def sha256(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def write_csv(path, rows):
    with path.open("x", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def read_pair_report(root, index, dataset, mode):
    entry = index[f"{dataset}_{mode}"]
    path = (root / entry["results"]).resolve()
    if not path.is_relative_to(root / "outputs"):
        raise ValueError(f"{dataset}/{mode}: report points outside the project outputs")
    report = read_json(path)
    expected_pairs, expected_rules = SIZES[dataset]
    if (report["dataset"], report["split"], report["subject_models"]) != (dataset, "dev", [MODEL]):
        raise ValueError(f"{dataset}/{mode}: expected a development report for {MODEL}")
    provenance = report["sources"]
    if any(not provenance.get(k) for k in (*PAIR_SOURCE_KEYS, "pred_sha256")):
        raise ValueError(f"{dataset}/{mode}: report is missing input provenance")
    rows = {}
    pairfile = path.with_name("pair_decisions.csv")
    with pairfile.open(encoding="utf-8-sig", newline="") as f:
        for row in csv.DictReader(f):
            k = int(row["pair_idx"])
            ref, n, failing = (int(row[c]) for c in ("reference", "n_rules", "n_failing"))
            if (k in rows or ref not in (0, 1) or row["decision"] not in DECISIONS
                    or n < 1 or not 0 <= failing <= n or not row["cluster"]):
                raise ValueError(f"{dataset}/{mode}: invalid or repeated pair in report")
            rows[k] = {"reference": ref, "trial_id": row["trial_id"], "cluster": row["cluster"],
                       "n_rules": n, "decision": row["decision"], "n_failing": failing}
    if (len(rows) != expected_pairs or report["pair_metrics"]["n"] != expected_pairs
            or sum(r["n_rules"] for r in rows.values()) != expected_rules):
        raise ValueError(f"{dataset}/{mode}: report has incomplete development coverage")
    return rows, {"report": str(path.relative_to(root)), "pairs_sha256": sha256(pairfile),
                  **{k: provenance[k] for k in (*PAIR_SOURCE_KEYS, "pred_sha256")}}


def compare_pairs(dataset, before, after):
    if set(before) != set(after):
        raise ValueError(f"{dataset}: modes contain different pair IDs")
    changes, counts = [], Counter()
    for pair_idx, u in sorted(before.items()):
        f = after[pair_idx]
        if any(u[k] != f[k] for k in ("reference", "trial_id", "cluster", "n_rules")):
            raise ValueError(f"{dataset}: modes disagree on pair identity, rules or reference")
        counts[u["reference"], u["decision"], f["decision"]] += 1
        changes.append({
            "dataset": dataset, "pair_idx": pair_idx, "trial_id": u["trial_id"],
            "reference": "eligible" if u["reference"] else "ineligible",
            "unknown_mode": u["decision"], "forced_mode": f["decision"],
            "unknown_failing_rules": u["n_failing"], "forced_failing_rules": f["n_failing"],
        })
    matrix = [
        {"dataset": dataset, "reference": "eligible" if ref else "ineligible",
         "unknown_mode": u, "forced_mode": f, "pairs": counts[ref, u, f]}
        for ref in (1, 0) for u in DECISIONS for f in DECISIONS
    ]
    return changes, matrix


def transitions(root):
    index = read_json(root / "outputs/mtp_parallel/REPORT_INDEX.json")
    matched, matrix, provenance = [], [], {}
    for dataset in SIZES:
        unknown, u = read_pair_report(root, index, dataset, "unknown")
        forced, f = read_pair_report(root, index, dataset, "forced")
        if any(u[k] != f[k] for k in PAIR_SOURCE_KEYS) or u["pred_sha256"] == f["pred_sha256"]:
            raise ValueError(f"{dataset}: reports do not represent two modes on the same source data")
        pairs, table = compare_pairs(dataset, unknown, forced)
        matched.extend(pairs)
        matrix.extend(table)
        provenance[dataset] = {"explicit_unknown": u, "forced_guess": f}

    out = root / "outputs/mtp_next_jobs" / datetime.now().strftime("pair_transitions_%Y%m%d_%H%M%S_%f")
    out.mkdir(parents=True, exist_ok=False)
    write_csv(out / "PAIR_TRANSITIONS_NO_NOTES.csv", matrix)
    write_csv(out / "MATCHED_PAIRS_NO_NOTES.csv", matched)
    atomic(out / "INPUTS.json", provenance)

    report = [
        "# Qwen development: paired decision changes",
        "",
        "Same patient–trial pairs in both answer modes. Reference groups use the dataset's "
        "pair eligibility labels. REVIEW is retained as a separate decision.",
        "",
    ]
    for dataset in SIZES:
        for ref in ("eligible", "ineligible"):
            rows = [r for r in matrix if r["dataset"] == dataset and r["reference"] == ref]
            c = {(r["unknown_mode"], r["forced_mode"]): r["pairs"] for r in rows}
            report.extend([
                f"## {dataset}: dataset reference {ref} (n = {sum(c.values())})",
                "",
                "| Explicit unknown → Forced guess | ELIGIBLE | REVIEW | NOT_ELIGIBLE |",
                "|---|---:|---:|---:|",
            ])
            for d in DECISIONS:
                report.append(f"| {d} | " + " | ".join(str(c[d, other]) for other in DECISIONS) + " |")
            report.append("")
            if ref == "eligible":
                wrong_before = sum(c["NOT_ELIGIBLE", f] for f in DECISIONS)
                wrong_after = sum(c[u, "NOT_ELIGIBLE"] for u in DECISIONS)
                report.extend([
                    f"Hard wrong exclusions: {wrong_before} → {wrong_after}. Of the eligible "
                    f"pairs initially sent to review, {c['REVIEW', 'NOT_ELIGIBLE']} moved to "
                    f"rejection and {c['REVIEW', 'ELIGIBLE']} moved to acceptance.",
                    "",
                ])
    report.append("Scope: descriptive development comparison. No calls or new reference labels.")
    (out / "REPORT.md").write_text("\n".join(report) + "\n", encoding="utf-8")
    print("PAIRED MODE REPORT:", out / "REPORT.md")
    print(f"Matched pairs: {len(matched)} | Model calls: 0")


@contextmanager
def try_lock(path, message):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a") as f:
        try:
            fcntl.flock(f, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            raise ValueError(message) from None
        yield


def local_worker_active():
    """Also recognise older Qwen workers that do not share the current lock."""
    for entry in Path("/proc").iterdir():
        if not entry.name.isdecimal() or entry.name == str(os.getpid()):
            continue
        try:
            if entry.stat().st_uid != os.getuid():
                continue
            argv = (entry / "cmdline").read_bytes().split(b"\0")
        except OSError:
            continue
        if not argv or not Path(os.fsdecode(argv[0])).name.startswith("python"):
            continue
        for i, arg in enumerate(argv[:-1]):
            script = Path(os.fsdecode(arg)).name
            if script == "mtp_qwen_followup.py":
                return True
            if script == "mtp_parallel.py" and argv[i + 1] == b"qwen":
                return True
    return False


def check_snapshot(path):
    """Take complete checkpoint lines only, even while the checker appends."""
    data = path.read_bytes()
    data = data[:data.rfind(b"\n") + 1]
    return [json.loads(line) for line in data.splitlines() if line.strip()]


def repo_imports(root):
    if not (root / "code/plain_ai.py").is_file() or not (root / "mtp_completion/common.py").is_file():
        raise ValueError("--root must be the installed Akash_Kit folder")
    sys.path[:0] = [str(root / "code"), str(root)]


def reask_inputs(root, limit, out):
    import plain_ai
    from criteria import map_truth
    from llm_client import prompt_key
    from mtp_completion.common import ensure_checks, hashed, load_predictions, select, unique

    dataset = "nsclc100"
    folder = root / "datasets" / dataset
    pred_path = root / LEGACY_PRED
    checks_path = root / LEGACY_CHECKS
    corpus, rules = select(root, dataset, "dev")
    pred = load_predictions(pred_path, corpus, rules, dataset)
    if (len(corpus), len(pred)) != SIZES[dataset]:
        raise ValueError("Unexpected legacy NSCLC development coverage")
    checks = unique(check_snapshot(checks_path))
    ensure_checks(checks.values())
    if not checks:
        raise ValueError("No saved checker rows are available yet")
    if any(k not in pred or c.get("provenance", {}).get("source_answer_hash") != hashed(pred[k])
           for k, c in checks.items()):
        raise ValueError("Checker rows do not match the legacy prediction file")
    if any(r.get("trace", {}).get("model") != MODEL for r in pred.values()):
        raise ValueError(f"Legacy subject must be {MODEL} with recorded model provenance")

    ids = sorted(pred)
    random.Random(7).shuffle(ids)
    order = {k: i for i, k in enumerate(ids)}
    verdicts = {k: map_truth(r["truth"], r["kind"]) for k, r in pred.items()}
    blockers = Counter(k[0] for k, v in verdicts.items() if v == "not_met")
    pairs = {int(p["pair_idx"]): p for p in corpus}

    # Same flagged subset ordering as K3, limited to rows already checked.
    def priority(k):
        failing = verdicts[k] == "not_met"
        return not failing, blockers[k[0]] if failing else 0, order[k]

    def job(k):
        r, c, pair = pred[k], checks[k], pairs[k[0]]
        rule = rules[pair["trial_id"]][k[1]]
        forced = ("FORCED" in r.get("trace", {}).get("prompt_id", "")
                  or "forced" in r.get("system", "").lower())
        system = plain_ai.SYSTEM_PROMPT_FORCED if forced else plain_ai.SYSTEM_PROMPT
        prompt_id = "REPAIR_ONCE_FORCED_v1" if forced else "REPAIR_ONCE_v1"
        allowed = ("yes", "no") if forced else ("yes", "no", "unknown")
        feedback = c["reason"]
        for label, field in (("CONTRADICTED", "contradiction"), ("MISSED_EVIDENCE", "missed_evidence")):
            if c["label"] == label:
                feedback += " Evidence: " + str(c["checks"][field]["sentence"])
        note = pair["patient_orig"]
        user = plain_ai.build_user(rule["criterion_text"], note, rule["note"]) + "\nFEEDBACK: " + feedback
        meta = {"pair_idx": k[0], "crit_idx": k[1], "before_truth": r["truth"], "checker_label": c["label"],
                "check_sha256": hashed(c), "prompt_sha256": prompt_key(MODEL, system, user, SUBJECT_OPTIONS)}
        return meta, system, user, prompt_id, allowed, note

    provenance = {"dataset": dataset, "split": "dev", "model": MODEL,
                  "subject_options": SUBJECT_OPTIONS, "limit": limit, "pred_sha256": sha256(pred_path),
                  "source_sha256": {p: sha256(folder / p) for p in (dataset + ".csv", "criteria.csv", "splits.csv")}}
    plan_path = out / "PLAN.json"
    if plan_path.exists():
        plan = read_json(plan_path)
        if plan["provenance"] != provenance:
            raise ValueError("Pilot settings or input changed; preserve the existing pilot folder")
        selected = [(j["pair_idx"], j["crit_idx"]) for j in plan["rows"]]
    else:
        selected = sorted((k for k, c in checks.items() if c["label"] != "VERIFIED"), key=priority)[:limit]
    if not selected or len(set(selected)) != len(selected) or len(selected) > limit:
        raise ValueError("No valid flagged cases are available for this pilot")
    jobs = [job(k) for k in selected]
    rows = [j[0] for j in jobs]
    if plan_path.exists():
        if plan["rows"] != rows:
            raise ValueError("A planned checker row or exact re-ask prompt changed")
    else:
        plan = {"provenance": provenance, "checker_rows_at_selection": len(checks), "rows": rows}
        atomic(plan_path, plan)
    return plan, jobs


class RejectRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def saved_case(out, meta):
    p = out / f"case_{meta['pair_idx']}_{meta['crit_idx']}.json"
    if not p.exists():
        return p, None
    data = read_json(p)
    if data["case"] != meta or data["status"] not in ("DRAFT_AWAITING_RECHECK", "UNPARSEABLE"):
        raise ValueError("A saved draft is inconsistent with its plan")
    return p, data


def repair_prep(root, limit):
    repo_imports(root)
    from llm_client import LocalLLM, CallFailed
    from plain_ai import clean_answer

    out = root / PILOT
    with try_lock(root / "outputs/mtp_parallel/qwen.lock", "A Qwen job is active; leave it running"):
        if local_worker_active():
            raise ValueError("A Qwen baseline or followup job is active; leave it running")
        out.mkdir(parents=True, exist_ok=True)
        plan, jobs = reask_inputs(root, limit, out)
        saved, pending = [], []
        for meta, *prompt in jobs:
            path, old = saved_case(out, meta)
            if old is None:
                pending.append((path, meta, *prompt))
            else:
                saved.append(old)

        # Keep notes on the loopback interface even if the shell uses an HTTP proxy.
        urllib.request.install_opener(urllib.request.build_opener(
            urllib.request.ProxyHandler({}), RejectRedirect()))
        client = LocalLLM(MODEL, host="http://127.0.0.1:11434",
                          num_ctx=SUBJECT_OPTIONS["num_ctx"], max_output=SUBJECT_OPTIONS["num_predict"],
                          timeout=120, call_retries=0, parse_retries=0)
        if client.options != SUBJECT_OPTIONS:
            raise ValueError("Installed Ollama client options differ from K3")
        status = {"status": "DRAFTS_COMPLETE", "stop_reason": None}
        try:
            print(f"K3 pilot: {len(saved)} / {len(jobs)} saved; "
                  f"sampled from {plan['checker_rows_at_selection']} checkpoint rows", flush=True)
            if pending:
                client.check_model_available()
            for path, meta, system, user, prompt_id, allowed, note in pending:
                response = client.chat_json(system, user, prompt_id=prompt_id)
                if response["prompt_sha256"] != meta["prompt_sha256"]:
                    raise ValueError("Installed Ollama client uses a different prompt hash")
                answer = clean_answer(response["data"], allowed) if response["ok"] else None
                draft = {
                    "case": meta, "status": "DRAFT_AWAITING_RECHECK" if answer else "UNPARSEABLE",
                    "answer": answer, "accepted": False,
                    "all_quotes_verbatim": all(q in note for q in answer["evidence"])
                    if answer and answer["evidence"] else None,
                    "cache_record": client.cache[meta["prompt_sha256"]] if answer else None,
                }
                atomic(path, draft)
                saved.append(draft)
                print(f"Saved {len(saved)} / {len(jobs)}: {draft['status']}", flush=True)
        except (CallFailed, KeyboardInterrupt) as error:
            status = {"status": "PAUSED", "stop_reason": type(error).__name__}
            if isinstance(error, CallFailed):
                print("Local Ollama stopped responding or refused a request. "
                      "Check 'ollama list', then repeat the same command.", flush=True)
        finally:
            if len(saved) != len(jobs):
                status["status"] = "PAUSED"
            status.update(scope="NSCLC dev; K3 re-ask only, no recheck or scoring",
                          planned=len(jobs), saved=len(saved),
                          usable_drafts=sum(d["answer"] is not None for d in saved),
                          external_api_calls=0)
            atomic(out / "STATUS_NO_NOTES.json", status)
            print("K3 STATUS:", out / "STATUS_NO_NOTES.json", flush=True)
        return 2 if status["status"] == "PAUSED" else 0


def reuse_cache(root):
    """Optional after the checker exits: make drafts available to completion.py repair."""
    repo_imports(root)
    from llm_client import LocalLLM, parse_json_object
    from plain_ai import clean_answer

    out = root / PILOT
    with try_lock(root / "outputs/mtp_parallel/qwen.lock", "A Qwen job is active"):
        with try_lock(root / ".mtp_completion.lock", "The checker or another completion job is active"):
            limit = read_json(out / "PLAN.json")["provenance"]["limit"]
            _, jobs = reask_inputs(root, limit, out)
            client = LocalLLM(MODEL, cache_dir=root / "outputs/mtp_completion/cache/ollama",
                              num_ctx=SUBJECT_OPTIONS["num_ctx"], max_output=SUBJECT_OPTIONS["num_predict"])
            added = 0
            for meta, _, _, prompt_id, allowed, _ in jobs:
                _, draft = saved_case(out, meta)
                if not draft or not draft["answer"]:
                    continue
                hit = draft["cache_record"]
                key = meta["prompt_sha256"]
                if (hit["key"] != key or hit["prompt_id"] != prompt_id or hit["done_reason"] == "length"
                        or clean_answer(parse_json_object(hit["raw"]), allowed) != draft["answer"]):
                    raise ValueError("A draft cannot be reused safely")
                if key not in client.cache:
                    client.cache[key] = hit
                    added += 1
            if added:
                tmp = client.cache_file.with_name(client.cache_file.name + ".tmp")
                with tmp.open("w", encoding="utf-8") as f:
                    for record in client.cache.values():
                        f.write(json.dumps(record, ensure_ascii=False) + "\n")
                    f.flush()
                    os.fsync(f.fileno())
                tmp.replace(client.cache_file)
            print(f"Cached {added} exact prompts for completion.py repair. Rechecks still required.")


def main():
    p = argparse.ArgumentParser(description=__doc__)
    sub = p.add_subparsers(dest="job", required=True)
    for name, help_text in (
        ("transitions", "compare the four completed Qwen development reports offline"),
        ("repair-prep", "prepare a bounded K3 pilot using local Qwen and existing NSCLC checks"),
        ("reuse-cache", "after the checker exits, stage exact drafts for the existing repair workflow"),
    ):
        command = sub.add_parser(name, help=help_text)
        command.add_argument("--root", default=Path.cwd(), type=Path)
        if name == "repair-prep":
            command.add_argument("--limit", default=20, type=int, choices=range(1, 101), metavar="1-100")
    args = p.parse_args()
    os.umask(0o077)
    root = args.root.resolve()
    try:
        if args.job == "transitions":
            transitions(root)
        elif args.job == "repair-prep":
            return repair_prep(root, args.limit)
        else:
            reuse_cache(root)
    except FileNotFoundError as error:
        print("STOP: missing required file:", error.filename, file=sys.stderr)
        return 2
    except (OSError, ValueError, KeyError, TypeError) as error:
        # Avoid printing model output or source row contents.
        if type(error) is ValueError:
            print("STOP:", str(error), file=sys.stderr)
        else:
            print(f"STOP: invalid input or local state ({type(error).__name__})", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
