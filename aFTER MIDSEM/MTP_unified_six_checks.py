#!/usr/bin/env python3
"""MTP: join saved development predictions, quotation checks and AI audits.

Produces SIX preliminary check outputs per criterion.  Does not infer, repair,
assert medical ground truth or alter any original experiment files.

Usage:
    python3 MTP_unified_six_checks.py --self-test
    python3 MTP_unified_six_checks.py --root ~/MTP/Akash_Kit
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import tempfile
from collections import Counter
from datetime import datetime
from pathlib import Path

BASELINES = (
    'outputs/plain_ai_qwen_dev.jsonl',
    'outputs/plain_ai_qwen_sigir_dev.jsonl',
)
AUDIT = 'outputs/overnight_audit/evidence_audit.jsonl'
CITATION = 'outputs/evidence_checks/real_citation_results.csv'
IMPACT = 'outputs/decision_impact/real_priority_analysis.csv'
TRUTH = {'yes', 'no', 'unknown'}
VERDICT = {'met', 'not_met', 'not_stated'}
KIND = {'inclusion', 'exclusion'}
SUPPORT = {'supported', 'unsupported', 'insufficient', 'uncertain'}
YES_NO_UNCERTAIN = {'yes', 'no', 'uncertain'}
CITATION_STATUS = {'PASS', 'FAIL', 'NO_EVIDENCE', 'INVALID_EVIDENCE'}
AUDIT_FIELDS = ('support', 'context_issue', 'logic_issue',
                'contradiction_issue', 'missed_evidence_issue',
                'suggested_truth', 'suggested_verdict',
                'needs_human_review')


class InputError(ValueError):
    pass


def identity(record):
    return (str(record['dataset']), int(record['pair_idx']), int(record['crit_idx']))


def truth_to_verdict(truth, kind):
    if truth not in TRUTH:
        raise InputError('Invalid truth ' + repr(truth))
    if kind not in KIND:
        raise InputError('Invalid kind ' + repr(kind))
    if truth == 'unknown':
        return 'not_stated'
    if kind == 'inclusion':
        return 'met' if truth == 'yes' else 'not_met'
    return 'not_met' if truth == 'yes' else 'met'


def parse_bool(value, label):
    if isinstance(value, bool):
        return value
    if str(value).strip().lower() in ('true', '1', 'yes'):
        return True
    if str(value).strip().lower() in ('false', '0', 'no'):
        return False
    raise InputError('Invalid boolean for ' + label + ': ' + repr(value))


def parse_csv_bool(value, label):
    return int(parse_bool(value, label))


def read_jsonl(path):
    if not path.is_file():
        raise InputError('Required file missing: ' + str(path))
    rows = []
    with path.open(encoding='utf-8') as stream:
        for line_no, line in enumerate(stream, 1):
            if not line.strip():
                continue
            try:
                obj = json.loads(line)
                if not isinstance(obj, dict):
                    raise InputError('Record must be object')
                rows.append(obj)
            except (ValueError, TypeError) as error:
                raise InputError(f'{path}:{line_no}: {error}') from error
    return rows


def read_csv(path):
    if not path.is_file():
        raise InputError('Required file missing: ' + str(path))
    with path.open(encoding='utf-8-sig', newline='') as stream:
        rows = list(csv.DictReader(stream))
    if not rows:
        raise InputError('No CSV rows: ' + str(path))
    return rows


def unique_index(rows, name):
    indexed = {}
    for row in rows:
        key = identity(row)
        if key in indexed:
            raise InputError('Duplicate ' + name + ': ' + str(key))
        indexed[key] = row
    return indexed


def same_keys(left, right, name):
    missing = left - right
    extra = right - left
    if missing or extra:
        raise InputError(f'{name} identities mismatch: missing={len(missing)} '
                         f'extra={len(extra)}; first missing={sorted(missing)[:3]}; '
                         f'first extra={sorted(extra)[:3]}')


def sha256(path):
    digest = hashlib.sha256()
    with path.open('rb') as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b''):
            digest.update(chunk)
    return digest.hexdigest()


def flag_from_judge(value, field):
    if value not in YES_NO_UNCERTAIN:
        raise InputError(f'Invalid AI {field}: {value!r}')
    return {'yes': 'FLAG_AI', 'no': 'NO_FLAG_AI', 'uncertain': 'UNCERTAIN_AI'}[value]


def support_status(value):
    if value not in SUPPORT:
        raise InputError('Invalid support: ' + repr(value))
    return {
        'supported': 'NO_FLAG_AI',
        'unsupported': 'FLAG_AI',
        'insufficient': 'INSUFFICIENT_AI',
        'uncertain': 'UNCERTAIN_AI',
    }[value]


def citation_status(value):
    if value not in CITATION_STATUS:
        raise InputError('Invalid citation status: ' + repr(value))
    return {
        'PASS': 'VERBATIM_MATCH',
        'FAIL': 'FLAG_NONVERBATIM',
        'NO_EVIDENCE': 'NO_CITATION',
        'INVALID_EVIDENCE': 'REVIEW_INVALID_EVIDENCE',
    }[value]


def construct(root, expected_count):
    baseline_paths = [root / p for p in BASELINES]
    audit_path = root / AUDIT
    citation_path = root / CITATION
    impact_path = root / IMPACT
    paths = baseline_paths + [audit_path, citation_path]

    baseline_rows = [r for p in baseline_paths for r in read_jsonl(p)]
    audits = read_jsonl(audit_path)
    citations = read_csv(citation_path)
    impacts = read_csv(impact_path) if impact_path.is_file() else None

    baseline = unique_index(baseline_rows, 'baseline')
    audit = unique_index(audits, 'audit')
    citation = unique_index(citations, 'citation')
    impact = unique_index(impacts, 'decision impact') if impacts is not None else None

    if len(baseline) != expected_count:
        raise InputError(f'Expected {expected_count} baseline records, got {len(baseline)}')
    for idx, obj in (('audit', audit), ('citation', citation)):
        same_keys(set(baseline), set(obj), idx)
    if impact is not None:
        same_keys(set(baseline), set(impact), 'decision impact')
        paths.append(impact_path)

    results = []
    counts = Counter()
    check_counts = {name: Counter() for name in
                    ('quote', 'unsupported', 'context', 'logic', 'contradiction', 'missed')}

    for key in sorted(baseline):
        b, a, c = baseline[key], audit[key], citation[key]
        nested = a.get('audit')
        if not isinstance(nested, dict) or any(f not in nested for f in AUDIT_FIELDS):
            raise InputError(f'Missing/invalid nested audit fields for {key}')

        kind, base_truth, base_verdict = b['kind'], b['truth'], b['verdict']
        if base_verdict not in VERDICT:
            raise InputError(f'Invalid baseline verdict for {key}')
        expected_baseline = truth_to_verdict(base_truth, kind)
        if a['baseline_truth'] != base_truth or a['baseline_verdict'] != base_verdict:
            raise InputError(f'Audit-baseline fields mismatch for {key}')
        if c['truth'] != base_truth or c['verdict'] != base_verdict:
            raise InputError(f'Citation-baseline fields mismatch for {key}')

        suggested_truth = nested['suggested_truth']
        derived_verdict = truth_to_verdict(suggested_truth, kind)
        judge_verdict = nested['suggested_verdict']
        if judge_verdict not in VERDICT:
            raise InputError(f'Invalid judge verdict for {key}')
        support = nested['support']
        support_info = nested.get('support_original_value', '')
        if support_info and (support_info != 'no_evidence' or support != 'insufficient'):
            raise InputError(f'Unexpected support normalization for {key}')
        human_review = parse_bool(nested['needs_human_review'], 'needs_human_review')

        cs = c['citation_status']
        quote = citation_status(cs)
        unsupported = support_status(support)
        context = flag_from_judge(nested['context_issue'], 'context_issue')
        model_logic = flag_from_judge(nested['logic_issue'], 'logic_issue')
        baseline_inconsistent = base_verdict != expected_baseline
        # Judge output inconsistency is a JUDGE quality-control issue,
        # not evidence that the original baseline's logic is wrong.
        logic = ('FLAG_BASELINE_MAPPING' if baseline_inconsistent else model_logic)
        contradiction = flag_from_judge(nested['contradiction_issue'], 'contradiction_issue')
        missed = flag_from_judge(nested['missed_evidence_issue'], 'missed_evidence_issue')
        judge_inconsistent = int(judge_verdict != derived_verdict)

        notes = []
        if judge_inconsistent:
            notes.append('JUDGE_VERDICT_MISMATCH_NOT_BASELINE_ERROR')
        if missed == 'FLAG_AI' and base_truth == suggested_truth == 'unknown':
            notes.append('MISSED_FLAG_BOTH_TRUTHS_UNKNOWN_NEEDS_VALIDATION')
        if cs == 'FAIL':
            notes.append('NONVERBATIM_NOT_PROOF_OF_FABRICATION')
        if cs == 'NO_EVIDENCE':
            notes.append('MISSING_QUOTE_NOT_AUTOMATICALLY_ERROR')
        if support in ('insufficient', 'uncertain'):
            notes.append('MODEL_EVIDENCE_UNCERTAIN_NOT_VERIFIED_ERROR')
        if support_info:
            notes.append('MODEL_SUPPORT_NORMALIZED_ORIGINAL_PRESERVED')

        item = {
            'dataset': key[0], 'pair_idx': key[1], 'crit_idx': key[2],
            'criterion_kind': kind, 'baseline_truth': base_truth,
            'baseline_verdict': base_verdict,
            'check_1_quote': quote,
            'check_2_unsupported': unsupported,
            'check_3_context': context,
            'check_4_logic': logic,
            'check_5_contradiction': contradiction,
            'check_6_missed': missed,
            'raw_citation_status': cs,
            'raw_support': support,
            'raw_support_original': support_info,
            'raw_context_issue': nested['context_issue'],
            'raw_logic_issue': nested['logic_issue'],
            'raw_contradiction_issue': nested['contradiction_issue'],
            'raw_missed_evidence_issue': nested['missed_evidence_issue'],
            'baseline_derived_verdict': expected_baseline,
            'baseline_mapping_inconsistent': int(baseline_inconsistent),
            'judge_suggested_truth': suggested_truth,
            'judge_suggested_verdict_raw': judge_verdict,
            'judge_verdict_derived': derived_verdict,
            'judge_mapping_inconsistent': judge_inconsistent,
            'judge_requested_human_review': int(human_review),
            'candidate_truth_change': int(base_truth != suggested_truth),
            'decision_changing': '', 'sole_rejection': '',
            'near_sole_rejection': '',
            'review_notes': ';'.join(notes),
            'evidence_ground_truth_verified': 0,
        }
        if impact is not None:
            d = impact[key]
            if d['verdict'] != base_verdict:
                raise InputError(f'Impact-baseline verdict mismatch for {key}')
            for col in ('decision_changing', 'sole_rejection', 'near_sole_rejection'):
                item[col] = parse_csv_bool(d[col], col)

        for check, result in zip(check_counts, (quote, unsupported, context, logic, contradiction, missed)):
            check_counts[check][result] += 1
        counts['baseline_mapping_inconsistent'] += baseline_inconsistent
        counts['judge_mapping_inconsistent'] += judge_inconsistent
        counts['judge_requested_human_review'] += human_review
        counts['suggested_truth_changed'] += base_truth != suggested_truth
        counts['missed_yes_unknown_unchanged'] += (missed == 'FLAG_AI' and base_truth == suggested_truth == 'unknown')
        counts['support_normalized'] += bool(support_info)
        counts['citation_quote_mismatch'] += cs == 'FAIL'
        counts['citation_no_evidence'] += cs == 'NO_EVIDENCE'
        results.append(item)

    summary = {
        'status': 'PRELIMINARY_AI_AND_DETERMINISTIC_OUTPUTS_NOT_GROUND_TRUTH',
        'records': len(results),
        'six_check_slots': len(results) * 6,
        'ground_truth_verified_records': 0,
        'per_check_status_counts': {k: dict(v) for k, v in check_counts.items()},
        'quality_control_counts': dict(counts),
        'source_sha256': {str(p.relative_to(root)): sha256(p) for p in paths},
        'important_limitations': [
            'No independent clinical adjudication is performed by this script.',
            'Citation PASS means a whitespace-normalized verbatim substring, not clinical correctness.',
            'Citation FAIL means nonverbatim quotation, not necessarily invented medical evidence.',
            'Support=insufficient is not automatically an unsupported-answer error.',
            'AI missed-evidence flags require verification, especially when both truths are unknown.',
            'Judge truth/verdict inconsistency is not baseline logic error.',
            'Derived judge verdict fixes mapping consistency only, not clinical truth.',
            'This is a development-stage pipeline, not held-out performance evaluation.',
        ],
    }
    return results, summary


def write_csv(path, rows):
    with path.open('x', newline='', encoding='utf-8') as stream:
        writer = csv.DictWriter(stream, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def write_outputs(root, records, summary):
    base = root / 'outputs/evidence_checks'
    tag = datetime.now().strftime('%Y%m%d_%H%M%S_%f')
    folder = base / ('unified_six_checks_' + tag)
    folder.mkdir(parents=True, exist_ok=False)
    write_csv(folder / 'unified_six_checks.csv', records)
    (folder / 'summary.json').write_text(
        json.dumps(summary, indent=2, ensure_ascii=False) + '\n', encoding='utf-8'
    )
    mismatches = [r for r in records if r['judge_mapping_inconsistent']]
    if mismatches:
        write_csv(folder / 'judge_mapping_mismatches.csv', mismatches)
    readme = '''# MTP six-check integration: development-stage output

This combines three existing output sets by exact (dataset,pair_idx,crit_idx):
- baseline Qwen predictions;
- deterministic whitespace-normalized quote matching results;
- Qwen evidence audits.
An optional fourth source adds already-computed decision-impact indicators.

The six columns `check_1_quote` through `check_6_missed` are **not**
independently adjudicated error labels. `FLAG_AI` means only that the
second AI marked an issue. `NO_FLAG_AI` is also not verified correctness.

The first citation check is a verbatim matching heuristic. A nonverbatim
quote is not necessarily fabricated. Missing citations are not automatically
mistakes. The second AI's `suggested_truth` is still unverified.

The separate `judge_verdict_derived` uses deterministic inclusion/exclusion
logic; **do not** treat it as an automatically safe correction. Raw suggested
verdict remains in `judge_suggested_verdict_raw`. A judge mapping mismatch is
NOT evidence of a baseline mistake. The original files are never modified.

`summary.json` includes input SHA-256 fingerprints, check-status counts and
quality-control warnings. Accuracy, precision, recall and F1 for the six
checks require independent or controlled known-answer error labels.
'''
    (folder / 'README.md').write_text(readme, encoding='utf-8')
    return folder


def self_test():
    assert truth_to_verdict('yes', 'inclusion') == 'met'
    assert truth_to_verdict('no', 'inclusion') == 'not_met'
    assert truth_to_verdict('yes', 'exclusion') == 'not_met'
    assert truth_to_verdict('no', 'exclusion') == 'met'
    assert truth_to_verdict('unknown', 'exclusion') == 'not_stated'
    assert citation_status('FAIL') == 'FLAG_NONVERBATIM'
    assert support_status('insufficient') == 'INSUFFICIENT_AI'
    try:
        truth_to_verdict('maybe', 'inclusion')
    except InputError:
        pass
    else:
        raise AssertionError('Invalid truth was accepted')

    with tempfile.TemporaryDirectory() as directory:
        root = Path(directory)
        for name in BASELINES + (AUDIT, CITATION, IMPACT):
            (root / name).parent.mkdir(parents=True, exist_ok=True)
        def jsonl(path, rows):
            path.write_text(''.join(json.dumps(x) + '\n' for x in rows))
        baseline = [
            dict(dataset='nsclc100', pair_idx=0, crit_idx=0, kind='inclusion', truth='yes', verdict='met'),
            dict(dataset='sigir204', pair_idx=3, crit_idx=4, kind='exclusion', truth='unknown', verdict='not_stated'),
            dict(dataset='sigir204', pair_idx=3, crit_idx=5, kind='exclusion', truth='no', verdict='met'),
        ]
        jsonl(root / BASELINES[0], baseline[:1])
        jsonl(root / BASELINES[1], baseline[1:])
        def audit_record(b, **changed):
            audit = dict(support='supported', context_issue='no', logic_issue='no',
                         contradiction_issue='no', missed_evidence_issue='no',
                         suggested_truth=b['truth'], suggested_verdict=b['verdict'],
                         needs_human_review=False)
            audit.update(changed)
            return dict(dataset=b['dataset'], pair_idx=b['pair_idx'],
                        crit_idx=b['crit_idx'], baseline_truth=b['truth'],
                        baseline_verdict=b['verdict'], audit=audit)
        aud = [audit_record(baseline[0]),
               audit_record(baseline[1], support='insufficient',
                            missed_evidence_issue='yes', suggested_verdict='not_met'),
               audit_record(baseline[2], support='unsupported',
                            contradiction_issue='yes', suggested_truth='yes',
                            suggested_verdict='met')]
        jsonl(root / AUDIT, aud)
        citations = []
        for i, b in enumerate(baseline):
            citations.append(dict(dataset=b['dataset'], pair_idx=b['pair_idx'],
                                  crit_idx=b['crit_idx'], truth=b['truth'],
                                  verdict=b['verdict'],
                                  citation_status=['PASS', 'NO_EVIDENCE', 'FAIL'][i]))
        with (root / CITATION).open('w', newline='') as f:
            w = csv.DictWriter(f, fieldnames=list(citations[0]))
            w.writeheader(); w.writerows(citations)
        impact = []
        for b in baseline:
            impact.append(dict(dataset=b['dataset'], pair_idx=b['pair_idx'],
                               crit_idx=b['crit_idx'], verdict=b['verdict'],
                               decision_changing='True', sole_rejection='False',
                               near_sole_rejection='False'))
        with (root / IMPACT).open('w', newline='') as f:
            w = csv.DictWriter(f, fieldnames=list(impact[0]))
            w.writeheader(); w.writerows(impact)
        records, summary = construct(root, 3)
        assert len(records) == 3 and summary['six_check_slots'] == 18
        assert summary['quality_control_counts']['judge_mapping_inconsistent'] == 2
        assert summary['quality_control_counts']['missed_yes_unknown_unchanged'] == 1
        assert summary['quality_control_counts']['citation_no_evidence'] == 1
        assert summary['quality_control_counts']['citation_quote_mismatch'] == 1
        assert summary['quality_control_counts']['suggested_truth_changed'] == 1
        assert all(r['evidence_ground_truth_verified'] == 0 for r in records)
        folder = write_outputs(root, records, summary)
        assert (folder / 'unified_six_checks.csv').is_file()
        assert (folder / 'judge_mapping_mismatches.csv').is_file()
    print('SELF-TEST PASS: joins, six fields, verdict mapping, uncertainty, output writing.')
    print('Model/API calls: 0')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', type=Path, default=Path.cwd(),
                        help='Path to the existing Akash_Kit project')
    parser.add_argument('--expected-count', type=int, default=1940,
                        help='Expected baseline count (default 1940)')
    parser.add_argument('--self-test', action='store_true')
    args = parser.parse_args()
    if args.self_test:
        self_test()
        return
    root = args.root.expanduser().resolve()
    records, summary = construct(root, args.expected_count)
    folder = write_outputs(root, records, summary)
    print('=== MTP UNIFIED SIX EVIDENCE CHECKS ===')
    print('Criterion records:', summary['records'])
    print('Six check output slots:', summary['six_check_slots'])
    print('Independently verified truth labels: 0')
    print('Judge mapping mismatches:', summary['quality_control_counts']['judge_mapping_inconsistent'])
    print('Baseline mapping mismatches:', summary['quality_control_counts']['baseline_mapping_inconsistent'])
    print('Missed-evidence flags with baseline and judge truth both unknown:',
          summary['quality_control_counts']['missed_yes_unknown_unchanged'])
    print('Output folder:', folder)
    print('Source files modified: NO')
    print('Ollama/API calls: 0')


if __name__ == '__main__':
    main()
