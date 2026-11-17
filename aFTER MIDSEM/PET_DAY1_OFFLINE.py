#!/usr/bin/env python3
"""Inspect MTP progress and rebuild original development baseline reports offline.

Run with the project's Python environment:
    .venv/bin/python ~/Downloads/PET_DAY1_OFFLINE.py --root "$PWD"

This invokes only the existing `completion.py report` command. It does not
launch inference, fill annotations, change checkpoints, or stop workers.
Outputs contain aggregate counts, metrics and file identities, not note text.
"""
import argparse
from collections import Counter
import csv
from datetime import datetime, timezone
import hashlib
import json
import math
import os
from pathlib import Path
import re
import subprocess
import sys
import tempfile


BASELINES = (
    ('nsclc100', 'outputs/plain_ai_qwen_dev.jsonl', 950, 50),
    ('sigir204', 'outputs/plain_ai_qwen_sigir_dev.jsonl', 990, 102),
)
LEGACY_CHECKS = (
    'outputs/mtp_completion/nsclc100/dev/'
    'plain_ai_qwen_dev_checks_theta95_fallback_exploratory.jsonl'
)
SHEETS = (
    ('nsclc100', 'assigned', 'labelling/my_label_sheet.csv', {'dev': 190, 'test': 256}),
    ('nsclc100', 'final', 'labelling/my_labels_final.csv', {'dev': 190, 'test': 256}),
    ('sigir204', 'assigned', 'labelling/sigir_label_sheet.csv', {'dev': 108, 'test': 95}),
    ('sigir204', 'final', 'labelling/my_sigir_labels_final.csv', {'dev': 108, 'test': 95}),
)


def save_json(path, value):
    temporary = path.with_suffix(path.suffix + '.tmp')
    with temporary.open('x', encoding='utf-8') as f:
        json.dump(value, f, ensure_ascii=False, indent=2, allow_nan=False)
        f.write('\n')
    temporary.replace(path)


def file_identity(path):
    info = path.stat()
    return info.st_ino, info.st_size, info.st_mtime_ns


def sha256(path):
    value = hashlib.sha256()
    with path.open('rb') as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b''):
            value.update(chunk)
    return value.hexdigest()


def workers():
    pattern = re.compile(r'(?<![\w-])(?:mtp_[\w-]+|completion|plain_ai|START_PET)\.py\b')
    try:
        result = subprocess.run(
            ['ps', '-u', str(os.getuid()), '-o', 'pid=,stat=,etime=,args='],
            capture_output=True, text=True, check=True, timeout=15,
        )
    except (OSError, subprocess.SubprocessError):
        return {'status': 'PROCESS_LIST_UNAVAILABLE', 'processes': []}
    selected = []
    for line in result.stdout.splitlines():
        pieces = line.strip().split(None, 3)
        if len(pieces) != 4 or pieces[0] == str(os.getpid()):
            continue
        match = pattern.search(pieces[3])
        if match:
            # Never expose the command line; it could contain credentials.
            selected.append(dict(pid=int(pieces[0]), state=pieces[1],
                                 elapsed=pieces[2], script=match.group(0)))
    return {'status': 'READ_ONLY_SNAPSHOT', 'processes': selected}


def inspect_jsonl(path, expected):
    out = {'file': str(path), 'expected_rows': expected, 'status': 'MISSING'}
    if not path.is_file():
        return out
    count = invalid = unidentified = duplicates = 0
    seen = set()
    digest = hashlib.sha256()
    try:
        before = file_identity(path)
        with path.open('rb') as f:
            for line in f:
                digest.update(line)
                if not line.strip():
                    continue
                count += 1
                try:
                    row = json.loads(line)
                    if not isinstance(row, dict):
                        raise TypeError('Expected object')
                    key = (int(row['pair_idx']), int(row['crit_idx']))
                except (json.JSONDecodeError, UnicodeDecodeError):
                    invalid += 1
                    continue
                except (KeyError, TypeError, ValueError):
                    unidentified += 1
                    continue
                duplicates += key in seen
                seen.add(key)
        changing = file_identity(path) != before
    except OSError as error:
        out.update(status='READ_ERROR', error_type=type(error).__name__)
        return out
    incomplete = Path(str(path) + '.INCOMPLETE').exists()
    status = ('CHANGING_DURING_READ' if changing else 'INCOMPLETE_MARKER' if incomplete
              else 'INVALID_RECORDS' if invalid or unidentified or duplicates
              else 'EXPECTED_COUNT_ONLY' if len(seen) == expected else 'PARTIAL_OR_UNEXPECTED_COUNT')
    out.update(status=status, nonempty_lines=count, unique_ids=len(seen),
               invalid_json=invalid, unidentified_records=unidentified,
               duplicate_ids=duplicates, incomplete_marker=incomplete,
               sha256=digest.hexdigest() if not changing else None)
    return out


def inspect_sheet(root, dataset, role, relative, expected):
    path = root / relative
    out = dict(dataset=dataset, role=role, file=str(path), expected=expected, status='MISSING')
    if not path.is_file():
        return out
    counts = {}
    all_splits = Counter()
    try:
        before = file_identity(path)
        with path.open(newline='', encoding='utf-8-sig') as f:
            reader = csv.DictReader(f)
            if not {'truth', 'split'}.issubset(reader.fieldnames or []):
                out['status'] = 'REQUIRED_COLUMNS_MISSING'
                return out
            for row in reader:
                split = (row.get('split') or '').strip().lower()
                all_splits[split] += 1
                if split not in expected:
                    continue
                group = counts.setdefault(split, dict(rows=0, valid=0, blank=0, invalid=0, unsure=0))
                group['rows'] += 1
                truth = (row.get('truth') or '').strip().lower()
                group['valid'] += truth in ('yes', 'no', 'unknown')
                group['blank'] += not truth
                group['invalid'] += bool(truth) and truth not in ('yes', 'no', 'unknown')
                group['unsure'] += (row.get('comment') or '').strip().upper().startswith('UNSURE')
        changing = before != file_identity(path)
        expected_counts = all(counts.get(s, {}).get('rows') == n and
                              counts.get(s, {}).get('valid') == n for s, n in expected.items())
        extra = sum(n for s, n in all_splits.items() if s not in expected)
        out.update(status='CHANGING_DURING_READ' if changing else
                   'FILLED_EXPECTED_COUNTS_ONLY' if expected_counts and not extra else 'INCOMPLETE_OR_UNEXPECTED_COUNTS',
                   counts=counts, other_split_rows=extra)
    except (OSError, csv.Error, UnicodeError, AttributeError) as error:
        out.update(status='READ_ERROR', error_type=type(error).__name__)
    return out


def number(value):
    return value if type(value) in (int, float) and math.isfinite(value) else None


def rebuild_report(root, run, dataset, prediction, expected_rows, expected_pairs, snapshot):
    out = {'dataset': dataset, 'source': str(prediction), 'status': 'NOT_RUN'}
    if snapshot['status'] != 'EXPECTED_COUNT_ONLY':
        out.update(status='SKIPPED_UNREADY_PREDICTION', source_status=snapshot['status'])
        return out
    report = run / dataset
    log = run / (dataset + '_report.log')
    command = [sys.executable, str(root / 'completion.py'), 'report', '--root', str(root),
               '--dataset', dataset, '--split', 'dev', '--pred', str(prediction),
               '--bootstrap', '1000', '--out', str(report)]
    try:
        with log.open('x', encoding='utf-8') as f:
            result = subprocess.run(command, cwd=root, stdout=f, stderr=subprocess.STDOUT, timeout=300)
        out.update(exit_code=result.returncode, log=str(log))
        if result.returncode:
            out['status'] = 'REPORT_COMMAND_FAILED'
            return out
        if sha256(prediction) != snapshot['sha256']:
            out['status'] = 'PREDICTION_CHANGED_DURING_REPORT'
            return out
        result_file = report / 'RESULTS.json'
        data = json.loads(result_file.read_text(encoding='utf-8'))
        metrics = data.get('pair_metrics', {})
        if data.get('dataset') != dataset or data.get('split') != 'dev' or metrics.get('n') != expected_pairs:
            out['status'] = 'REPORT_IDENTITY_OR_COUNT_MISMATCH'
            return out
        binary = metrics.get('binary_review_as_not_eligible', {})
        keys = ('n', 'eligible_pairs', 'ineligible_pairs', 'false_exclusions',
                'false_inclusions', 'sole_reason_false_exclusions', 'review_count', 'review_rate')
        out.update(status='BASELINE_REPORT_READY', results=str(result_file),
                   report=str(report / 'REPORT.md'), source_sha256=snapshot['sha256'],
                   pair_metrics={k: number(metrics.get(k)) for k in keys},
                   binary_review_as_negative={k: number(binary.get(k)) for k in
                                             ('accuracy', 'balanced_accuracy', 'precision',
                                              'sensitivity', 'specificity', 'f1', 'tp', 'fp', 'tn', 'fn')},
                   student_label_file_used=False, checker_file_used=False,
                   unparseable_predictions=number(data.get('unparseable_predictions')),
                   mapping_mismatches=number(data.get('baseline_mapping_mismatches')))
    except subprocess.TimeoutExpired:
        out.update(status='REPORT_TIMEOUT', log=str(log))
    except (OSError, ValueError, TypeError, AttributeError) as error:
        out.update(status='REPORT_READ_ERROR', error_type=type(error).__name__, log=str(log))
    return out


def pct(value):
    return 'N/A' if value is None else f'{100 * value:.1f}%'


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', type=Path, required=True)
    args = parser.parse_args()
    os.umask(0o077)
    root = args.root.expanduser().resolve()
    if not (root / 'completion.py').is_file():
        parser.error('--root must contain the existing completion.py')
    parent = root / 'outputs' / 'pet_milestone'
    parent.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime('day1_%Y%m%d_%H%M%S_UTC_')
    run = Path(tempfile.mkdtemp(prefix=stamp, dir=parent))
    print('OFFLINE OUTPUT:', run, flush=True)
    live = workers()
    print('Matching worker processes:', len(live['processes']), flush=True)
    for worker in live['processes']:
        print(' ', worker['pid'], worker['state'], worker['elapsed'], worker['script'], flush=True)
    sheets = [inspect_sheet(root, *spec) for spec in SHEETS]
    for sheet in sheets:
        print('LABEL FILE:', sheet['dataset'], sheet['role'], sheet['status'], flush=True)
        for split, count in sheet.get('counts', {}).items():
            print(' ', split, 'filled', count['valid'], '/', count['rows'], flush=True)
    checks = inspect_jsonl(root / LEGACY_CHECKS, 950)
    print('LEGACY NSCLC CHECKER:', checks['status'], '| unique IDs:',
          checks.get('unique_ids', 0), '/ 950 (coverage only)', flush=True)
    sources = []
    reports = []
    for dataset, relative, expected_rows, expected_pairs in BASELINES:
        prediction = root / relative
        snapshot = inspect_jsonl(prediction, expected_rows)
        snapshot['dataset'] = dataset
        sources.append(snapshot)
        report = rebuild_report(root, run, dataset, prediction, expected_rows, expected_pairs, snapshot)
        reports.append(report)
        print('BASELINE REPORT:', dataset, report['status'], flush=True)
        if report['status'] == 'BASELINE_REPORT_READY':
            binary = report['binary_review_as_negative']
            print(' accuracy:', pct(binary['accuracy']), '| eligible recall:', pct(binary['sensitivity']),
                  '| F1:', pct(binary['f1']), flush=True)
    summary = dict(created_utc=datetime.now(timezone.utc).isoformat(), project=str(root),
                   scope='Original saved development baselines; not the later matched-mode experiment',
                   model_calls_requested=0, workers=live, annotation_counts=sheets,
                   legacy_checker_coverage=checks, baseline_sources=sources, baseline_reports=reports,
                   limitations=[
                       'Filled counts do not validate annotation identities, evidence or clinical correctness.',
                       'Expected JSONL counts do not independently establish reference-ID coverage.',
                       'The existing strict report loader performs the dataset join for each baseline.',
                       'No final labels or checker checkpoint are supplied to baseline scoring.',
                       'These metrics do not measure checker accuracy or repair improvement.',
                       'Worker status is a point-in-time observation; no worker was stopped or restarted.',
                   ])
    save_json(run / 'DAY1_NO_NOTES.json', summary)
    lines = ['# PET Day 1 offline results', '', 'No model calls requested.', '',
             'Scope: the original saved NSCLC and SIGIR development baselines.', '',
             '| Dataset | Report status | Binary accuracy | Eligible recall | F1 |',
             '|---|---|---:|---:|---:|']
    for report in reports:
        metric = report.get('binary_review_as_negative', {})
        lines.append('| ' + ' | '.join((report['dataset'], report['status'],
                                        pct(metric.get('accuracy')), pct(metric.get('sensitivity')),
                                        pct(metric.get('f1')))) + ' |')
    lines.extend(['', 'Binary metrics count REVIEW as not eligible. These are baseline scores.', '',
                  '## Next dependencies', '',
                  '- Inspect final-label counts; complete human labels and label checks as required.',
                  '- Inspect current workers and checker provenance before resuming model jobs.',
                  '- A partial checker checkpoint must not be scored as complete.',
                  '- Keep original and later answer-policy experiment identities separate.', '',
                  'DAY1_NO_NOTES.json contains aggregate status and source hashes, without note text.', ''])
    (run / 'SUMMARY.md').write_text('\n'.join(lines), encoding='utf-8')
    print('SUMMARY:', run / 'SUMMARY.md', flush=True)
    print('STATUS:', run / 'DAY1_NO_NOTES.json', flush=True)
    print('Existing annotations, predictions, checkpoints and workers were not changed.', flush=True)
    return 0 if all(r['status'] == 'BASELINE_REPORT_READY' for r in reports) else 2


if __name__ == '__main__':
    try:
        raise SystemExit(main())
    except KeyboardInterrupt:
        print('Interrupted. Existing source files and model workers were not changed.', file=sys.stderr)
        raise SystemExit(130)
