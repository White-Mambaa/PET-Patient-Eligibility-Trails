# PET — ten-day completion milestone and conversation record

**Planning period:** 13–22 November 2026, inclusive, India Standard Time.  
**Scope:** Neha ma'am's original main project: NSCLC + SIGIR, components A–E, research questions K1–K6 and Tables 1–8.  
**Planning status:** a new ten-day working target requested by the student. It does not establish that the professors have extended their earlier three-day deadline. Day 3 remains an early submission checkpoint.  
**Evidence cutoff:** the supplied source/archive and the 9 November closeout. Laptop processes and newer results have not been inspected remotely.

## Contents

1. What must be delivered
2. What we can reuse
3. Complete remaining-work checklist
4. Terminal work to run first
5. Next automated jobs and their dependencies
6. Ten-day schedule
7. Manual work instructions
8. Terminal allocation and recovery rules
9. Final acceptance checklist and handover
10. Previous ten visible project messages

## 1. What must be delivered

The original research question is: **with limited checking time, which AI answers should a person inspect first to catch wrongly excluded eligible patient–trial pairs, and do automatic fixes help or harm?**

Expected software input: a patient note, reviewed trial criteria, inclusion/exclusion kind and criterion guidance.

Expected software outputs:

- Criterion truth (`yes`, `no`, `unknown`), source evidence, basis, rationale and confidence.
- A three-way screening decision: `ELIGIBLE`, `NOT_ELIGIBLE`, `REVIEW`.
- Six saved evidence checks and one checker label for each answer.
- A review queue, rejection-risk ranking and a trace of keeping, deferring or re-asking/rechecking answers.
- Reproducible experiment outputs demonstrating what worked, what failed and what remains uncertain.

### Original source documents

| Source | Relevant sections |
|---|---|
| [Akash_Project_Guide.md](https://chatgpt.com/library?file_id=libfile_186835608d448191bef11cb91c0a0f99&account_id=personal) | §1 scope; §6 labels; §7 systems; §8 six checks; §§9–12 ranking, risk, fixes and traps; §13 Tables 1–8; §§14–16 reporting and freeze rules. |
| [SIGIR_PACK_README.md](https://chatgpt.com/library?file_id=libfile_68a69d47fb408191ac458e1cb397d603&account_id=personal) | Patient-based split, SIGIR labels, count-the-rules baseline, rule-count groups and frozen-method transfer. |

The assignment is assessed against these documents. Our earlier leftover-work note is a historical progress note, not a replacement specification. AAPEMS remains outside this milestone.

### Research outputs

| Research question | Required result |
|---|---|
| Baselines | Table 1: rule accuracy on student labels, verbatim quotations, wrongful exclusions, single-rule exclusions, wrongful inclusions and review workload. |
| K1 — review priority | Table 2 and curve: five strategies at 5, 10, 20, 50 and 100 checks, rescues per 10 checks and checks with unknown effect. |
| K2 — checker quality | Table 3: precision, recall, flag rate and accuracy of VERIFIED/flagged answers; Table 4: remove-one-check analysis. |
| K3 — repair | Table 5: fixed, broken and unchanged answers; pair outcomes before and after keep/flag/re-ask. |
| K4 — traps | Table 6: trap rate, detection rate and right-label rate by trap type. |
| K5 — rejection risk | Table 7: precision/recall at 3, 5 and 10, compared with random rejected-pair order. |
| K6 — transfer | Table 8: separate NSCLC and SIGIR results using the frozen method. |

## 2. What we can reuse

These are historical verified or recorded artifacts, not live progress assertions.

| Existing work | Reuse condition |
|---|---|
| Original saved development baseline: 950 NSCLC + 990 SIGIR criterion predictions | Verify exact IDs, dataset/split, model, configuration, complete coverage and file hashes before joining them to checker outputs. |
| Later Qwen unknown-allowed/forced-guess development result rows | The archived counts can be reported as saved development results. Recover their original prediction/pair CSVs for a new row-by-row recomputation. |
| Six-check implementation and 706/950 recorded legacy NSCLC judgments | 706/950 is closeout coverage, not accuracy. Inspect the current checkpoint; do not assume the old count is current or combine it with a different checker run. |
| Earlier 22/1/0 candidate comparison at budget 50 | Keep it as a separate retrospective exploratory result. It is not the full Table 2 experiment or 22 confirmed clinical corrections. |
| Repair pilot, synthetic fixtures, three preliminary trap inputs | Reuse for engineering/debugging. Establish accepted repairs and trap performance through the required real experiment and checks. |
| Portal, command-line engine, tests and reporting functions | Reuse the implementation, then connect and evaluate it. Passing software tests does not establish clinical or checker accuracy. |

### Baseline policy metrics already available in the saved November closeout

| Dataset / policy | Pairs | Binary accuracy | Eligible recall | Eligible F1 | Hard wrong exclusions | REVIEW |
|---|---:|---:|---:|---:|---:|---:|
| NSCLC / allow unknown | 50 | 50.0% | 0.0% | 0.0% | 12/25 | 16 |
| NSCLC / forced guess | 50 | 56.0% | 12.0% | 21.4% | 22/25 | 0 |
| SIGIR / allow unknown | 102 | 53.9% | 4.1% | 7.8% | 15/49 | 72 |
| SIGIR / forced guess | 102 | 57.8% | 12.2% | 21.8% | 43/49 | 0 |

Positive class: ELIGIBLE. Binary metrics treat REVIEW as not eligible. Hard wrong exclusions count explicit NOT_ELIGIBLE decisions; eligible pairs in REVIEW also reduce binary recall. These are baseline policy results, not a measured PET repair improvement. The archive does not contain the raw November prediction/checkpoint files needed to reconstruct every result row independently.

## 3. Complete remaining-work checklist

**Types:** `T` = automated terminal job; `M` = human work; `C` = coding/integration work with tests. A task is complete when its stated output is verified, not when a process has merely run.

| ID | Type | Remaining task | Completion evidence |
|---|---|---|---|
| W01 | T + M | Inventory live processes, saved predictions/checks, labels, manifests and current code. | One dated status record; no duplicate writers; source files identified. |
| W02 | M | Choose and document the main subject model, judge/support method, context backend, prompts, context size and answer policies. | One method record. Distinguish legacy Groq checks from any new local-Qwen experiment. |
| W03 | M | Complete the original student label sheets and UNSURE comments. | Final NSCLC file: 190 dev + 256 test rows; final SIGIR file: 108 dev + 95 test rows. All assigned identities present; 649 labels total. |
| W04 | T + M | Run both label checks and resolve conflicts with the supervisor. | Label-check CSVs and recorded supervisor decisions. Do not change labels merely to agree with pair outcomes. |
| W05 | T + M | Complete, review and freeze rule statements/key terms. | NSCLC: 95 dev + 128 test statements; SIGIR: 1,911 rules in total. Hand review as specified; identify the 24 earlier source-wording fallbacks. |
| W06 | T + M | Verify citation calibration and other checker settings using development data. | Calibration labels, selection output and method choices. The earlier selected theta=95 needs its provenance; it is not a substitute for the selection record. |
| W07 | C + T | Connect the portal to actual model screening and the six-check workflow. | A real case runs end to end, including evidence, all check statuses, priority and human review. A synthetic self-test is labelled separately. |
| W08 | T | Complete matched development baseline predictions for both answer policies and datasets. | 950 NSCLC and 990 SIGIR answers per policy, or an explicitly scoped pilot. Full final reports require full split coverage. Reuse matching completed outputs. |
| W09 | T | Complete all six checks for each evaluated answer. | Complete ID-matched checker records, all six components saved, invalid/missing work counted, exact source/configuration provenance. |
| W10 | T | Build Table 1 and criterion metrics. | Pair outcomes and quote rates; rule metrics on final student labels, both all-labelled and without-UNSURE. |
| W11 | T | Run all five K1 strategies with the guide's correction simulation. | Table 2, order CSVs, curve, per-10 measures, unknown-effect counts and comparison units. |
| W12 | T | Measure checker quality and ablations. | Tables 3–4: precision, recall, flag rate, VERIFIED accuracy, errors caught only by each check; all/without-UNSURE analyses. |
| W13 | T + M | Run keep/flag/re-ask and validate repairs. | Table 5, original and repaired answer files, rechecks, fixed/broken/unchanged counts and pair-level before/after results. |
| W14 | M + T | Build, hand-check and evaluate traps. | Table 6 for seven types, up to 20 suitable cases/type; true expected answers and altered-note provenance. Report smaller numbers if fewer suitable cases exist. |
| W15 | T | Evaluate rejection-risk ranking. | Table 7 with precision/recall at 3/5/10, counts and random comparison. Reference labels used for scoring, not ranking. |
| W16 | T + M | Complete SIGIR-specific controls. | Count-the-rules baseline; development-defined short/medium/long groups; patient-level comparisons; separate NSCLC/SIGIR reports. |
| W17 | T | Produce rarity reweighting and small-sample reporting. | Pair results at target eligibility rates 0.10 and 0.05, per-trial NSCLC and per-patient SIGIR results, uncertainty/comparisons as specified. |
| W18 | M + T | Freeze code, prompts, method and complete labels before held-out inference. | Commit/content hashes and freeze record; test eligibility gates pass. |
| W19 | T | Execute the planned held-out systems, checker, strategies and fixer once. | Complete run artifacts and Tables 1–8 for the final scope. No test-based tuning or silent deletion of failed cases. |
| W20 | M + T | Verify and deliver software, results, examples, report and slides. | Reproducible release, source-to-table mapping, 20 worked examples with appropriate privacy, setup/run instructions and known limitations. |

**Optional or additional feedback:** top-three-sentence local retrieval is an optional third subject in original guide §7.3. The latest supervisor feedback asks for a clearer LLM/RAG/agent workflow; implement a bounded, explicit retrieval → screening → checking → priority → one-repair/recheck route if included, and evaluate it separately. It must not replace the required two answer policies or delay their core evaluation. The guide's optional learned ranking and own 100-answer checker-style labels are later extras; do not make them blockers for the required core.

## 4. Terminal work to run first

### 4.1 First job: offline software tests and project status

Paste this complete block into a free terminal. It uses existing files in `~/MTP/Akash_Kit`, creates a fresh report directory and makes no real model requests. It does not stop or restart any worker.

```bash
(
  set -euo pipefail
  cd "$HOME/MTP/Akash_Kit"
  test -x .venv/bin/python || { echo 'STOP: Project Python environment is missing.'; exit 1; }
  test -s completion.py || { echo 'STOP: completion.py is missing from this project.'; exit 1; }
  test -s completion_selftest.py || { echo 'STOP: completion_selftest.py is missing.'; exit 1; }

  mkdir -p outputs/pet_milestone
  session_dir=$(mktemp -d "$PWD/outputs/pet_milestone/preflight_XXXXXX")

  .venv/bin/python completion_selftest.py --root "$PWD" \
    2>&1 | tee "$session_dir/software_tests.log"

  .venv/bin/python completion.py status \
    --root "$PWD" --out "$session_dir/PROJECT_STATUS.json" \
    2>&1 | tee "$session_dir/project_status.log"

  printf '\nPREFLIGHT OUTPUT: %s\n' "$session_dir"
)
```

Interpretation: a skipped medspaCy/NLI integration remains unverified. A passing mocked test is not a successful live model run. The status command summarises the original assigned sheets; the next check also inspects possible final-label files.

### 4.2 Read-only live-process, checkpoint and annotation audit

Paste the complete block, including the opening and closing `PY`. It prints counts and process identifiers, never note text or key values. It does not alter source data, annotations, predictions or keys.

```bash
cd "$HOME/MTP/Akash_Kit" && .venv/bin/python - <<'PY'
import csv
import json
import os
from pathlib import Path
import re
import subprocess

root = Path.cwd()
print('PROJECT:', root)
print('\nLIVE PROJECT WORKERS (PID, STATE, ELAPSED, SCRIPT)')
result = subprocess.run(
    ['ps', '-u', str(os.getuid()), '-o', 'pid=,stat=,etime=,args='],
    capture_output=True, text=True, check=True,
)
found = False
pattern = re.compile(r'(?<![\w-])(?:mtp_[\w-]+|completion|plain_ai|START_PET)\.py\b')
for line in result.stdout.splitlines():
    parts = line.strip().split(None, 3)
    if len(parts) != 4:
        continue
    match = pattern.search(parts[3])
    if match:
        found = True
        print(parts[0], parts[1], parts[2], match.group(0))
if not found:
    print('No matching project worker found.')

print('\nLEGACY DEVELOPMENT FILE COUNTS — NOT ACCURACY')
files = (
    ('NSCLC baseline', 'outputs/plain_ai_qwen_dev.jsonl', 950),
    ('SIGIR baseline', 'outputs/plain_ai_qwen_sigir_dev.jsonl', 990),
    ('Legacy NSCLC checker', 'outputs/mtp_completion/nsclc100/dev/'
     'plain_ai_qwen_dev_checks_theta95_fallback_exploratory.jsonl', 950),
)
for name, relative, expected in files:
    path = root / relative
    if not path.is_file():
        print(name, '| missing at legacy path; inspect newer run manifests.')
        continue
    count = invalid = duplicates = unidentified = 0
    seen = set()
    with path.open(encoding='utf-8') as f:
        for line in f:
            if not line.strip():
                continue
            count += 1
            try:
                row = json.loads(line)
                identity = (int(row['pair_idx']), int(row['crit_idx']))
            except json.JSONDecodeError:
                invalid += 1
                continue
            except (KeyError, TypeError, ValueError):
                unidentified += 1
                continue
            duplicates += identity in seen
            seen.add(identity)
    incomplete = Path(str(path) + '.INCOMPLETE').exists()
    print(name, '| lines:', count, '/', expected, '| unique IDs:', len(seen),
          '| invalid JSON:', invalid, '| unidentified:', unidentified,
          '| duplicate IDs:', duplicates, '| INCOMPLETE marker:', incomplete)

print('\nANNOTATION COUNTS — NO ROW CONTENTS')
for relative in (
    'labelling/my_label_sheet.csv', 'labelling/my_labels_final.csv',
    'labelling/sigir_label_sheet.csv', 'labelling/my_sigir_labels_final.csv',
):
    path = root / relative
    if not path.is_file():
        print(relative, '| missing')
        continue
    with path.open(newline='', encoding='utf-8-sig') as f:
        rows = list(csv.DictReader(f))
    print(relative, '| total rows:', len(rows))
    for split in ('dev', 'test'):
        group = [r for r in rows if (r.get('split') or '').strip().lower() == split]
        filled = sum((r.get('truth') or '').strip().lower() in
                     {'yes', 'no', 'unknown'} for r in group)
        unsure = sum((r.get('comment') or '').strip().upper().startswith('UNSURE')
                     for r in group)
        print(' ', split, '| filled:', filled, '/', len(group), '| UNSURE:', unsure)

print('\nAudit finished. Counts alone do not establish complete valid coverage.')
print('An active append may cause a partial last line; inspect again after the writer finishes.')
PY
```

If the audit finds a running worker, inspect its checkpoint/configuration before starting another inference process. A suspended `T` process still exists. Do not delete a lock file or kill processes merely to bypass a duplicate-worker message.

### 4.3 Next offline job: regenerate both original baseline reports

Run after the preflight confirms these are the correct complete prediction files. This job makes no generation calls and does not use the incomplete checker checkpoint. It writes to a fresh directory. Rule/checker metrics remain unavailable until final labels/checks are supplied.

```bash
(
  set -euo pipefail
  cd "$HOME/MTP/Akash_Kit"
  test -s outputs/plain_ai_qwen_dev.jsonl
  test -s outputs/plain_ai_qwen_sigir_dev.jsonl
  mkdir -p outputs/pet_milestone
  report_dir=$(mktemp -d "$PWD/outputs/pet_milestone/baseline_reports_XXXXXX")

  .venv/bin/python completion.py report \
    --root "$PWD" --dataset nsclc100 --split dev \
    --pred outputs/plain_ai_qwen_dev.jsonl --bootstrap 1000 \
    --out "$report_dir/nsclc100"

  .venv/bin/python completion.py report \
    --root "$PWD" --dataset sigir204 --split dev \
    --pred outputs/plain_ai_qwen_sigir_dev.jsonl --bootstrap 1000 \
    --out "$report_dir/sigir204"

  printf '\nBASELINE REPORTS: %s\n' "$report_dir"
)
```

These commands reproduce the supplied original baseline files. They do not automatically select the later paired-policy runs. Use the recovered report index and hashes to identify those separately. If a strict loader reports a mismatch or incompleteness, keep the failure visible and resolve the actual input issue; do not force a final score from partial coverage.

## 5. Next automated jobs and their dependencies

### Existing command entry points

The inspected `completion.py` supports these commands. These help commands make no model calls:

```bash
cd "$HOME/MTP/Akash_Kit"
.venv/bin/python completion.py statements --help
.venv/bin/python completion.py baseline --help
.venv/bin/python completion.py check --help
.venv/bin/python completion.py report --help
.venv/bin/python completion.py repair --help
.venv/bin/python completion.py prepare-traps --help
.venv/bin/python completion.py run-traps --help
.venv/bin/python completion.py trap-report --help
.venv/bin/python completion.py freeze --help
.venv/bin/python completion.py compare-datasets --help
```

Do not copy a guessed future filename into a launch command. The table below specifies the next actual jobs, including which ones require further coding or human input first.

| Order | Automated job | Required inputs/gate | Output | Model calls? |
|---|---|---|---|---|
| A01 | Tests, status and metadata audit — §4 | Existing project environment and files | Dated status/counts | No |
| A02 | Original baseline reports — §4.3 | Complete matching baseline files | Pair metrics, quote rates, per-cluster results | No |
| A03 | Label check using original `code/evaluate.py labelcheck` | Human-completed final student labels; correct dataset corpus | Conflict lists for supervisor | No |
| A04 | Generate missing rule statements | Development source rules, recorded model/config and bounded call budget | Draft statements and key terms | Yes; only missing matching work |
| A05 | Calibration selection | Human-labelled development paraphrase/invention cases | Selected threshold and selection record | No generation calls |
| A06 | Missing matched development baselines | Chosen subject model, policies, full notes/guidance, budget | Complete per-criterion JSONL for both datasets/modes | Yes, unless correctly cached |
| A07 | Six-check development runs | Matched predictions; reviewed statements; configured checker | Complete six-check JSONL | Depends on NLI/judge method; measure usage |
| A08 | Reports, five orders, K1 simulation, ablations and rejection risk | Complete matched checks/predictions and usable final labels | Tables 1–4, 7; ordering CSVs; risk CSV; JSON summaries | No generation calls |
| A09 | Priority-curve rendering and table export | A08 results | Curve and table artifacts | No; presentation/export code may need completing |
| A10 | Keep/flag/re-ask experiment | Complete checks, same subject model, bounded repair budget | Repaired/rechecked answers and Table 5 inputs | Re-ask/recheck only |
| A11 | Trap drafts → run → report | Reviewed labelled development sources; human-confirmed altered notes | Table 6 and traceable trap outputs | Draft generation is not annotation; model calls for screening/checking |
| A12 | SIGIR controls and rarity reporting | Complete dataset results; development-only cutoffs/groups | Rule-count baseline/groups and rarity tables | No generation calls; complete missing export code |
| A13 | Freeze and held-out evaluation | Human gates passed; method/config/code/labels frozen | Once-only test results and Table 8 | Yes for unseen inference/checking |
| A14 | Reproduction, integrity checks and packaging | All final artifacts with source hashes | Runnable release, report, slides and result bundle | No generation calls |

### One bounded development-check launch template

This is a **gated template**, not a claim that the inputs/settings have already been verified. Set its variables from the chosen run manifest/method record. A changed statement file, prompt, model or code version requires a new output path. Local Ollama and Groq are different configurations.

```bash
(
  set -euo pipefail
  cd "$HOME/MTP/Akash_Kit"
  : "${PET_DATASET:?Set nsclc100 or sigir204}"
  : "${PET_PRED:?Set the verified development prediction JSONL path}"
  : "${PET_STATEMENTS:?Set the reviewed development statement CSV path}"
  : "${PET_JUDGE_BACKEND:?Set the recorded ollama or groq backend}"
  : "${PET_JUDGE_MODEL:?Set the recorded judge model}"
  : "${PET_THETA:?Set the development-selected citation threshold}"
  : "${PET_TAU:?Set the recorded support threshold}"
  : "${PET_SUPPORT:?Set judge or nli}"
  : "${PET_CONTEXT:?Set the recorded medspacy or judge backend}"
  : "${PET_MAX_OUTPUT:?Set the recorded maximum output tokens}"
  : "${PET_NUM_CTX:?Set the recorded context size}"
  : "${PET_CHECKS_OUT:?Set a compatible pilot/resume output JSONL path}"
  test -s "$PET_PRED"
  test -s "$PET_STATEMENTS"

  .venv/bin/python -u completion.py check \
    --root "$PWD" --dataset "$PET_DATASET" --split dev \
    --backend "$PET_JUDGE_BACKEND" --model "$PET_JUDGE_MODEL" \
    --pred "$PET_PRED" --statements "$PET_STATEMENTS" \
    --theta "$PET_THETA" --tau "$PET_TAU" \
    --support-backend "$PET_SUPPORT" --context-backend "$PET_CONTEXT" \
    --max-output "$PET_MAX_OUTPUT" --num-ctx "$PET_NUM_CTX" \
    --limit 5 --max-calls 50 --out "$PET_CHECKS_OUT"
)
```

The limit is five development answers, not five API requests: one answer can require several sentence-level judgments. The 50-attempt cap is an engineering bound, not a full-dataset budget. If the cap is reached, leave the run INCOMPLETE. Scale only after inspecting actual calls/tokens and validation failures. Do not add `--allow-unreviewed-statements` to make the final evaluation bypass human statement review.

For an existing checkpoint, preserve all its original settings, input hashes and code version when resuming. The template does not automatically reproduce the old supervisor's settings. Establish that compatibility from its manifest first; otherwise use a separate run.

### Resource budget before a long run

Record a small development pilot: answers completed, attempts, cache hits, input/output tokens, latency, failure reasons and provider retry waits. Estimate the remaining workload from those observations. Do not reuse the earlier 66,256-request ceiling as a measured budget. Six checks do not necessarily mean six calls: exact/numeric checks may be local, and support/contradiction scans may use several calls per sentence. Reuse valid caches; do not repeatedly regenerate completed baselines.

## 6. Ten-day schedule

Human review and independent terminal work should overlap where their inputs are stable. The schedule is a completion target, not a guarantee of API throughput or annotation time.

| Day / date (IST) | Terminal work | Manual / coding work | End-of-day artifact or gate |
|---|---|---|---|
| **1 — 13 Nov** | Preflight, audit, strict baseline reports, recover report index/raw files, measure a bounded missing-work pilot. | Resolve experiment identities; start/finalise development labels; inspect dependency and integration gaps. | Dated inventory, baseline reports, task ownership and pilot-based compute estimate. |
| **2 — 14 Nov** | Generate missing development statements/predictions; run integration tests. | Finish development label review and statement review; implement portal-to-real-engine connection. | Reviewed development inputs and a real end-to-end case trace. |
| **3 — 15 Nov** | Run the reviewed checker pilot and first matched development tables. | Inspect both flagged and VERIFIED examples; demonstrate the actual workflow and explain limitations. | **Early submission checkpoint:** working software + verified development subset/results + explicit remaining scope. |
| **4 — 16 Nov** | Complete matched development baselines and six-check coverage, reusing valid work. | Resolve recurring invalid-output/root-cause issues; continue test labels without consulting model test outputs. | Complete development artifacts for both datasets/policies, or an explicit coverage shortfall. |
| **5 — 17 Nov** | Generate Tables 1–4, all five priority orders, strategy curve and ablations. | Check simulation definitions, UNSURE sensitivity and source-to-result joins. | Development K1/K2 evidence with reproducible artifacts. |
| **6 — 18 Nov** | Run bounded repair/recheck and the approved trap set. | Hand-confirm trap expectations; review fixes and breaks against student labels. | Development Tables 5–6 with traceable denominators. |
| **7 — 19 Nov** | Produce risk ranking, rule-count controls, rarity reweighting and development dataset comparison. | Finish assigned test labels and supervisor label-check resolutions; verify the main strategy/configuration. | Development Tables 1–8 as available; held-out readiness checklist. |
| **8 — 20 Nov** | Verify hashes/freeze, then start the planned held-out runs only after the gates pass. | Finalise code, prompts, selected settings, statement protocol and labels. | Recorded freeze and controlled test launch. No test-based edits. |
| **9 — 21 Nov** | Complete compatible held-out runs, repair/trap reporting as specified, and final tables/curve. | Inspect coverage and consistency; report failures and uncertainties without changing the method. | Final results with dataset/split/configuration provenance. |
| **10 — 22 Nov** | Reproduce results, verify release integrity, package software and artifacts. | Final report/slides, worked examples and demonstration rehearsal; check every claim against evidence. | Submission bundle and a clear completed/incomplete checklist. |

If the Day 1 pilot predicts that the full experiment cannot finish within the available capacity, surface that estimate immediately. Changing the evaluated scope must be explicit; never select an easier subset after seeing its results. An unfinished full-scope run remains incomplete.

## 7. Manual work instructions

### M1 — Student labels

- NSCLC: 446 assigned rows (190 dev, 256 test). SIGIR: 203 (108 dev, 95 test). Total: **649**.
- Complete truth, exact evidence, basis, applicability/compound indicators and comments using original guide §6. Follow `criterion_note` first.
- `unknown` means insufficient patient information. Interpretation uncertainty is recorded with `UNSURE:`; it is not automatically hidden as unknown.
- Standard implications permitted by the original guide may be marked `inferred`. Do not import a stricter replacement rubric without documenting the method change.
- Keep model suggestions out of blinded labelling. AI drafts do not become an independent answer key.
- Save the finished files as `labelling/my_labels_final.csv` and `labelling/my_sigir_labels_final.csv`, with full assigned identity coverage. Frozen labels are not edited to make a system win.
- Test labels must be complete **before any system run on test patients/trials**. Overlap agreement follows the supervisor's procedure; do not coordinate answers beforehand.

### M2 — Statements, calibration and traps

- Inspect all 95 NSCLC development statements, including source-wording fallbacks; follow the SIGIR rule-review instructions for assigned development rules.
- Complete any human paraphrase/invention calibration examples before selection. Keep threshold selection development-only.
- Build traps from development sources only. Re-read each altered note and confirm its expected answer; draft generation cannot set `checked_by_hand=true` on behalf of a person.

### M3 — Method and result review

- Record subject and judge models separately. Same-model judging can share errors; checker quality must still be measured against student labels.
- SIGIR units are patients, NSCLC units are trials. A patient–trial pair is not a distinct patient.
- Document the rule-count cutoff difference: guide §14 suggests the development median; SIGIR §6 supplies a development-accuracy-selected cutoff. Select the primary definition before the test and label both if reporting both.
- Define short/medium/long rule groups from development data and preserve them for test reporting.
- The guide's K1 simulation may replace an unlabelled failing answer on a reference-eligible pair with unknown. A simulated rescue removes a hard exclusion; it may route a pair to REVIEW, not prove clinical eligibility.
- Check that raw counts, accuracy, recall, F1, review rates and hard wrong exclusions use their stated denominators. Never reuse 92.73% as validated project accuracy.

## 8. Terminal allocation and recovery rules

| Terminal | Useful assignment | Boundary |
|---|---|---|
| **1** | One managed inference queue: missing baselines/statements/checks/repairs. | The current `completion.py` uses a project-wide model-process lock. Do not start another conflicting writer in the same project. |
| **2** | Offline metrics/plots/exports on completed, immutable outputs. | Do not score a partial checkpoint as a final run. A watcher alone produces no new inference results. |
| **3** | Manual labels, statement review, trap review and label-check resolution. | Work in review copies. Do not change frozen labels or files currently bound to an experiment. |
| **4** | Portal integration, synthetic fixtures, tests and documentation. | Use an isolated code copy/branch while inference runs. Editing imported experiment code mid-run breaks reproducibility; merge before the freeze. |

Do not add multiple simultaneous Qwen workers simply because terminals are free. They can compete for the same model server and memory. Use separate inference workers only after resource measurement and isolation of outputs/configurations establish that this helps.

Runtime requirements for a reliable long job:

- One owner for each output; atomic status/checkpoints and validated resume identities.
- A shared provider limiter, bounded attempts/time, and actual token/attempt logs.
- Respect `Retry-After`, including waits longer than a minute. Emit heartbeat status while waiting; waiting is not a completed answer.
- Distinguish authentication, quota, timeout, malformed response, quote mismatch and code errors. Do not rotate credentials to disguise invalid output or bypass an organisation-wide limit.
- A network retry may repeat a charge when the previous outcome is unknown; keep a bounded retry policy and record it.
- Invalid/unavailable work is not an `unknown` clinical answer. Keep failed runs INCOMPLETE, retain rows/checkpoints and report coverage.
- Stop cleanly on an irrecoverable error, exhausted budget or deadline. No program can guarantee uninterrupted useful execution.
- For terminal-independent execution, create the log file before background launch and use a supported `nohup`/service launcher. Keep awake and power/network settings appropriate; do not silently restart incompatible jobs.

## 9. Final acceptance checklist and handover

### Software

- [ ] A documented single entry point launches the tool.
- [ ] A real configured LLM screens a supplied case; model/backend are recorded.
- [ ] Six check statuses, evidence, priority and repair/recheck trace are visible.
- [ ] Missing dependencies, connection errors and incomplete work are visible.
- [ ] Human review is required for final case judgement; a checker label is not proof of correctness.
- [ ] Software tests are recorded; synthetic results are separated from benchmark results.

### Experiments

- [ ] Both answer policies, both datasets, exact coverage and same subject configuration.
- [ ] Final student labels, UNSURE counts, label checks and supervisor resolutions.
- [ ] Tables 1–8 with their correct units and counts.
- [ ] Five review strategies, fixed budgets, curve and guide simulation assumptions.
- [ ] Fixed and broken repairs; seven trap types; rejection-risk comparison.
- [ ] SIGIR count-the-rules and length-group controls; rarity reweighting.
- [ ] Freeze before held-out inference; test scope and failures explicitly reported.
- [ ] No metric mixes different October/November runs or reports a missing result as zero.

### Suggested new delivery layout

This is a proposed layout to create during packaging, not a claim these files already exist.

| Delivery area | Contents |
|---|---|
| `software/` | Source, launch instructions, dependency setup, schemas and tests. |
| `method/` | Prompts, model/settings record, hashes and freeze evidence. |
| `results/` | Tables 1–8, curves, machine-readable metrics and source-to-table mapping. |
| `evaluation_private/` | Approved private prediction/check/repair/annotation artifacts; no keys in the delivery. |
| `report/` | Final report, slides, worked examples and limitations. |

**Daily update format:** date; W-IDs completed; verified counts/expected counts; artifacts; new calls/tokens; blockers; next task. Mark work complete only when the corresponding acceptance evidence exists.

## 10. Previous ten visible project messages

The appendix below records the ten most recent visible project-discussion messages before this request, oldest first. User and assistant messages are counted separately; configuration, tools and progress updates are excluded. This is not an export of ten separate conversations. Whitespace and HTML space entities are normalised for readability; repeated discussion is retained. Earlier completion claims and estimates are retained as discussion history, not promoted into verified results or promises.

<!-- CHAT_HISTORY_START -->
### Message 1 — User

> but anyone can create what is unique ness in your project

---

### Message 2 — User

> **PET’s distinctive contribution is deciding which AI answer a reviewer should check first, based on whether correcting it could change the screening outcome.**
>
> If the panel says *“Anyone can build this,”* you can say:
>
> > Sir, the model and website can be reproduced. Our contribution is the review method. For each answer, we ask: **If this answer changes and all the other answers stay the same, does the screening outcome change?** Suppose the note says “ECOG 1,” the trial accepts ECOG 0 or 1, and the AI answers “no.” If that answer alone is driving the exclusion, PET puts it high in the review queue and shows the source evidence. If other criteria still block the case, correcting that one answer won’t change the outcome.
>
> **What backs it up:** In our retrospective development evaluation, with the same budget of **50 criterion checks**, ranking by decision impact surfaced **22 wrong-exclusion candidates**. Ranking by citation checks alone surfaced **1**, and the archived random order surfaced **0**. These were candidates for review; we did not measure confirmed clinical corrections.
>
> The research question you can defend is: **When reviewers have limited time, can we use it to find more errors that matter to the decision?**
>
> \==========
>
> My question is for you , can you just check the .md file what where we have to give output to the neha maa

---

### Message 3 — User

> **PET’s distinctive contribution is deciding which AI answer a reviewer should check first, based on whether correcting it could change the screening outcome.**
>
> If the panel says *“Anyone can build this,”* you can say:
>
> > Sir, the model and website can be reproduced. Our contribution is the review method. For each answer, we ask: **If this answer changes and all the other answers stay the same, does the screening outcome change?** Suppose the note says “ECOG 1,” the trial accepts ECOG 0 or 1, and the AI answers “no.” If that answer alone is driving the exclusion, PET puts it high in the review queue and shows the source evidence. If other criteria still block the case, correcting that one answer won’t change the outcome.
>
> **What backs it up:** In our retrospective development evaluation, with the same budget of **50 criterion checks**, ranking by decision impact surfaced **22 wrong-exclusion candidates**. Ranking by citation checks alone surfaced **1**, and the archived random order surfaced **0**. These were candidates for review; we did not measure confirmed clinical corrections.
>
> The research question you can defend is: **When reviewers have limited time, can we use it to find more errors that matter to the decision?**
>
> \==========
>
> My question is for you , can you just check the .md file what where we have to give output to the neha maa'am is that same output what ma'am mentioned in my project track what you say can you just review my sigar and other thing and telll me that could be very much helpful and supprotive so what you exactly say so also one more thing si that i need to know that what exactly it is related to ?
>
> output whch we have got and we send to our professor is that what neha maa'am exepecting ?
>
> why i ask these all questions because , i just got a reply from varun sir and neha ma'am
>
> Neha maa'am :
>
> what actually y0u made ? is this a project that which builds your career you should think and update it , so work for it and update this.
>
> you have done not exactly what we need
>
> we taught you concepts like RAG , AGents and LLMs why all that stuff taught to you ?
>
> Varun dutt :
>
> is this what you made out of 4 months ? this is what you present to your in on resume ? you should work for more , where are the softwares ? what you have used ? whcih algorithm you have use ? what are doing acutally ?
>
> so these all question you shoudl respond , you are not mere studnet but you are from computer science so you should understand what exact you are working with !
>
> So you have to work based on that , we are still giving you 3 days so adjust your work and submit back to us and that's up to you what you use adn work with so that si so clear i think !

---

### Message 4 — Assistant

> **I checked the original project guide, SIGIR pack and `leftover_work.md` against the delivered code and archived results.**
>
> **The decision-impact idea matches Neha ma’am’s original assignment. However, our submitted evidence covers only part of the required final evaluation. My earlier wording that the project was “complete” was too strong.**
>
> [Read the detailed requirements review](sandbox:/workspace/scratch/1b65be8412f1/output/PET_REQUIREMENTS_REVIEW.md)
>
> ## 1. What ma’am originally expected
>
> The assignment’s question is:
>
> > With limited checking time, which AI answers should a reviewer check first to catch wrongly excluded patients—and do automatic fixes help or harm?
>
> It requires these results:
>
> | Required work | Where we currently stand |
> |---|---|
> | **Baseline screening:** unknown-allowed versus forced-guess answers | Development results available for both datasets. |
> | **Review prioritisation:** compare five strategies at equal budgets | Exploratory results available; the complete comparison remains unfinished. |
> | **Checker quality:** precision, recall, accuracy of VERIFIED answers and check ablations | Code exists; the submitted evidence does not establish these final measurements. |
> | **Repairs:** count answers fixed **and broken** | Implementation and pilot drafts exist; measured benefit remains unestablished. |
> | **Seven trap types:** measure model errors and checker detection | Preliminary examples exist; complete evaluation is missing. |
> | **Rejection-risk ranking and SIGIR transfer** | Implementation/development work exists; complete final results are missing. |
>
> **Therefore, the 22-versus-1-versus-0 explanation supports the intended research direction. It does not replace all eight required results tables.**
>
> ## 2. What our software actually does
>
> The core work includes:
>
> - Qwen answering individual trial criteria with supporting evidence.
> - Code applying inclusion/exclusion logic to produce **ELIGIBLE, NOT_ELIGIBLE or REVIEW**.
> - Evidence-checking code for quotation accuracy, support, context, logic, contradictions and missed evidence.
> - Ranking algorithms using checker flags, confidence and the number of rejection reasons.
> - A bounded feedback-and-recheck repair workflow.
>
> **The important integration gap:** the current portal checks supplied answers. Live Qwen screening and the fuller checker are in a separate command-line workflow. The portal does not currently execute that entire live pipeline.
>
> ## 3. What about RAG and agents?
>
> **The original guide explicitly describes retrieval as an optional third system in Section 7.3.** It was not the main mandatory deliverable.
>
> Their latest feedback now asks for a stronger connected system. A suitable update is:
>
> **Retrieve relevant note evidence → generate criterion answers → run six checks → prioritise review → re-ask flagged answers once → recheck.**
>
> Each stage should show its actual evidence, model calls and output. Calling stages “agents” alone does not demonstrate improvement.
>
> ## 4. What to prioritise in these three days
>
> | Day | Concrete target |
> |---|---|
> | **1** | Connect the real model/checker workflow to the tool; finish development labels and statement review. |
> | **2** | Produce matched development comparisons, checker metrics, repair/trap results and SIGIR controls; freeze the method when ready. |
> | **3** | Run held-out evaluation after the freeze, verify results, and package the software, tables, curve and report. |
>
> The guide accepts **carefully completed student labels with supervisor conflict checks**. AI drafts cannot become the evaluation answer key.
>
> **My assessment: retain the project’s research question. Complete the connected software and missing evaluations. The current outputs are useful development evidence, but they are not yet the complete final output ma’am requested.**

---

### Message 5 — User

> i am talking abotu what mam given it is what i am asking acutally !
> SIGr .md forgot about leftover work whcih is created by us but what baout neha mama given to me which si in the neha maam one so that si what i am asking how she is expecteing the outptu ? what output actually needed ?

---

### Message 6 — Assistant

> **You mean Neha ma’am’s original assignment—not the leftover-work document we created.**
>
> I checked her original [Akash Project Guide](https://chatgpt.com/library?file_id=libfile_186835608d448191bef11cb91c0a0f99&account_id=personal) and [SIGIR Pack README](https://chatgpt.com/library?file_id=libfile_68a69d47fb408191ac458e1cb397d603&account_id=personal).
>
> ## 1. What output does she actually expect?
>
> Her project asks:
>
> > **When a reviewer has limited time, which AI answers should they check first to find wrongly excluded patients—and do automatic fixes help or harm?**
>
> She expects **working software and experimental results answering that question.**
>
> ### The software must produce these five outputs
>
> | Component | Expected output |
> |---|---|
> | **A. Evidence checker** | For every AI answer, save six checks: quotation, support, context, logic, contradiction and missed evidence. Assign one final checker label. |
> | **B. Review priority** | An ordered list showing which criterion answers a person should inspect first. |
> | **C. Rejection-risk list** | Rank rejected patient–trial pairs by the risk that their rejection is wrong, without using reference labels to rank them. |
> | **D. Fixer** | Compare keeping an answer, changing it to unknown for review, and re-asking the model once followed by rechecking. |
> | **E. Trap evaluation** | Test deliberately altered notes—negation, family history, hypothetical conditions, old values, contradictions, removed evidence and changed thresholds. |
>
> The underlying screening output is:
>
> **Patient note + trial criteria → criterion answers with evidence → ELIGIBLE / NOT_ELIGIBLE / REVIEW.**
>
> ## 2. What results must she receive?
>
> Her guide explicitly specifies **eight tables**:
>
> | Table | What she wants measured |
> |---|---|
> | **1. Baseline systems** | Criterion accuracy on student labels, real quotations, wrong exclusions, single-rule exclusions, wrong inclusions and REVIEW counts. |
> | **2. Review strategies** | Compare five strategies at **5, 10, 20, 50 and 100 checks**, including rescued pairs per 10 checks and a comparison curve. |
> | **3. Checker quality** | Flag precision, recall, accuracy of VERIFIED answers and accuracy of flagged answers. |
> | **4. Check ablation** | Remove each check and measure what performance is lost. |
> | **5. Repairs** | Answers **fixed, broken and unchanged**, plus screening decisions before and after. |
> | **6. Traps** | How often traps fool the model and how often the checker catches those errors. |
> | **7. Rejection risk** | Precision and recall among the top **3, 5 and 10** rejected pairs. |
> | **8. Dataset comparison** | Compare checking effectiveness on NSCLC and SIGIR. |
>
> **Her headline measure is “eligible patient–trial pairs rescued per checking budget.”** The guide defines this through a simulated review procedure; it is not a count of clinically confirmed patient rescues.
>
> ## 3. What does her SIGIR `.md` specifically require?
>
> SIGIR is the **second benchmark for the same system**. Its additional requirements include:
>
> - **204 pairs**, divided into **102 development and 102 test pairs**, separated by patient.
> - Complete your assigned **108 development + 95 test criterion labels**.
> - Use patient-level comparisons and report SIGIR separately from NSCLC.
> - Include a **count-the-rules baseline** and short/medium/long rule-list results.
> - Freeze settings and labels before running the test patients.
> - Apply the same checker, ranking and repair methods.
>
> **So her expected final submission is: runnable screening-and-review software, completed annotation checks, and Tables 1–8 demonstrating how well the method works. Accuracy is one required measurement; the main research output is whether decision-aware checking finds more harmful errors for the same review effort.**

---

### Message 7 — User

> so what we have done ? is that matching her output ?

---

### Message 8 — Assistant

> **Our work matches her project’s direction, but it does not yet satisfy her complete final-output requirements.** We have a software prototype and development experiments.
>
> Based on the supplied files and saved closeout:
>
> | What ma’am requested | What we have done | Status |
> |---|---|---|
> | **Baseline screening** | Saved NSCLC and SIGIR development predictions; reports comparing unknown-allowed and forced-guess policies. | Development results available |
> | **Six evidence checks** | Implemented the checker. The closeout records **706/950 NSCLC judgments**. | Implementation exists; evaluation incomplete |
> | **Review prioritisation** | Implemented ranking methods. Archived decision-impact ranking found **22 review candidates within 50 checks**, versus 1 for citation ranking and 0 for the archived random order. | Exploratory evidence; full required comparison unfinished |
> | **Rejection-risk list** | Implemented the scoring/ranking code. | Complete measured results not established |
> | **Fixer** | Implemented feedback, re-asking and rechecking; saved a repair pilot. | Fixed-versus-broken evaluation unfinished |
> | **Trap set** | Created preliminary examples and software demonstrations. | Full seven-type evaluation unfinished |
> | **NSCLC–SIGIR transfer** | Produced development baselines for both datasets. | Frozen-method held-out comparison missing |
> | **Working software** | Built the portal and command-line engine. | Live LLM/checker workflow remains separate from the portal |
>
> ### What this means
>
> **Yes, the baseline, checker, prioritisation and repair work belong to her assignment.** We have not accidentally built an entirely different project.
>
> **The shortfall is that we delivered implementations and preliminary results without completing the experimental evidence she requested.** In particular:
>
> - **706/950 is coverage**, not checker accuracy.
> - **22 candidates is an exploratory ranking result**, not 22 confirmed corrections.
> - Baseline accuracy does not measure whether **our checker and repair method improve screening**.
> - The submitted evidence does not establish completed final student labels, all eight results tables or the held-out evaluation.
>
> ### What should happen next?
>
> Keep the existing code and results. The priority is to **connect the actual screening/checking workflow and complete the missing evaluations**, especially checker precision/recall, equal-budget ranking, and repairs fixed versus broken.
>
> **My earlier statement that everything was complete was incorrect. We completed useful parts of her project; we have not yet completed her required final evaluation.**

---

### Message 9 — User

> how many days that will take to complete her work as she have given what you say

---

### Message 10 — Assistant

> **For Neha ma’am’s complete original assignment, I would budget approximately 7–10 focused working days using our existing code.** This is a planning estimate; we have not measured the remaining runtime.
>
> Assumptions: full-time work, stable model access, and someone completing the required student annotations.
>
> | Remaining work | Estimated effort |
> |---|---:|
> | Complete student labels, statement review and label checks | 2–3 days |
> | Connect the live screening/checker workflow and resolve failures | 1–2 days |
> | Complete development experiments: ranking, checker quality, repairs, traps and rejection risk | 2–3 days |
> | Freeze, run held-out evaluation, verify tables and package delivery | 1–2 days |
>
> Some tasks can overlap, giving the **7–10-day overall estimate**. Continued API limits or annotation delays could extend it.
>
> ### What about her three-day deadline?
>
> **Three days is a compressed recovery window—not a reliable estimate for completing every original requirement.**
>
> In those three days, the realistic target is:
>
> 1. A connected, working software demonstration.
> 2. A clearly defined development evaluation with verified metrics.
> 3. Reproducible results and an honest list of unfinished requirements.
>
> **My recommendation: plan for 7–10 days for the full assignment, while prioritising the strongest verifiable submission within the three days she has allowed.** Running more terminals can help independent experiments, but annotation, method review and result verification still require human work.
<!-- CHAT_HISTORY_END -->
