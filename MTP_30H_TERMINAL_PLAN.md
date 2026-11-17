# MTP 30-hour recovery / completion sprint

**Priority:** research code, reproducible experiments, and real metrics. **Not** slides, reports to faculty, or fresh large local-Qwen jobs.

## Run 3 terminals (2 active lightweight analyses + 1 monitoring/review)

Download `MTP_finish_sprint.py` into `/home/honcho/Downloads/`.

### Terminal 1 — Five-method equal-budget ranking and conservative deferral

```bash
cd ~/MTP/Akash_Kit
python3 ~/Downloads/MTP_finish_sprint.py --self-test
python3 ~/Downloads/MTP_finish_sprint.py --root ~/MTP/Akash_Kit --task risk
```

Outputs under `outputs/research_completion_sprint/risk_.../`, including
`risk_budget_summary.csv`, `proposed_review_actions_NO_GOLD.csv`,
`RISK_AND_DEFERRAL_REPORT.md`, and an SHA-256 source manifest.

There are five rankings, seven budgets (10/25/50/100/200/400/800) and two conservative deferral policies. Existing development reference pair labels are used **only to score the selections after ranking**. Review deferral is not a successful clinical repair. Do not claim patients have been rescued.

### Terminal 2 — Build blinded six-check annotation queue

```bash
cd ~/MTP/Akash_Kit
python3 ~/Downloads/MTP_finish_sprint.py --root ~/MTP/Akash_Kit --task queue --random-per-dataset 12 --target-per-check 5
```

Outputs under `outputs/research_completion_sprint/adjudication_.../`.

- `PRIVATE_BLINDED_REVIEW_FILL_LOCALLY.csv`: includes full patient notes and six **empty** ground-truth fields. Keep on authorized laptop. **Never upload or commit this file.**
- `public_case_ids_NO_NOTES.csv`: note-free keys and sampling cohorts.
- `queue_manifest.json`: sampling breakdown and label definitions.

A reviewer should fill each check with `1`, `0`, `defer`/`uncertain`, leaving unreviewed labels blank. Do **not** fill labels based on the second AI's outputs; have an independent blinded reviewer examine the medical evidence. Some errors may be impossible to adjudicate without clinical expertise; record deferral.

### Terminal 3 — Track tasks; DO NOT launch another large model process

```bash
cd ~/MTP/Akash_Kit
find outputs/research_completion_sprint -maxdepth 2 -type f -name '*.md' -o -name 'queue_manifest.json' | sort | tail -30
```

Look for files produced by the first two jobs. Both tasks are CPU-light and finish on existing outputs, so you can continue browser/LinkedIn/coursework work. Only launch one GPU/Ollama job at a time after these results are evaluated.

### After independent review (not before)

```bash
cd ~/MTP/Akash_Kit
python3 ~/Downloads/MTP_finish_sprint.py \
  --root ~/MTP/Akash_Kit --task score \
  --review-file 'outputs/research_completion_sprint/adjudication_YYYYMMDD_HHMMSS_xxxxxx/PRIVATE_BLINDED_REVIEW_FILL_LOCALLY.csv'
```

Replace the directory name with the actual output directory printed by the queue command. No model calls. The scorer **refuses** to manufacture scores when labels are blank. Metrics are conditional on reviewed and non-abstained cases; report sampling limitations, not population-wide clinical accuracy.

## Prioritized remaining 30-hour work

1. **First hour:** execute both CPU analyses, examine ranking/review burden results, freeze source inputs and determine which cases require independent review.
2. **Next 8–12 hours:** obtain independent six-check ground-truth annotations on the blinded local dataset, including positive/negative evidence and inter-reviewer agreement where feasible.
3. **Next 5–6 hours:** implement and test review-only conservative triage or controlled verified repairs; compare costs and harms against baseline, without automatically trusting the Qwen suggested truth.
4. **Next 5–6 hours:** freeze checker thresholds and evaluate untouched held-out test splits if validated protocol permits; explicitly isolate those test results from development analyses.
5. **Final hours:** reproducibility checks, error analysis, aggregate metrics, documentation, code packaging and limitation statements.

**Non-negotiable:** full clinical checker precision/recall/F1 and safe automatic repair cannot be claimed without independent labels. Held-out results cannot be backfilled from development data. No patient notes should be sent to external APIs without permission.

## Existing confirmed results (not recalculated by this readme)

- Development: 1,940 baseline criterion predictions; 1,940 Qwen judge outputs; six-check outputs for all 1,940 criteria.
- Baseline strict accuracy: NSCLC 46.00%, SIGIR 15.69%; original preliminary accuracy disagreement still requires reconciliation.
- Controlled known-answer trap pilot: 3/3 baseline truth/verdict correct; one suspected judge missed-evidence false alarm.
- Judge repeatability: 120/120 complete; 113/120 entirely identical on eight compared fields.
- Synthetic answer-level controlled challenge: 180/180 complete. Explicit `logic_issue=yes` against injected mapping errors TP=16 FN=104 FP=2 TN=58, F1=23.19%. Not clinical correctness.

This sprint helper preserves input datasets and prediction files. It writes only timestamped output folders under `outputs/research_completion_sprint/`. The six-check reviewer sheet is intentionally private and should remain local.
