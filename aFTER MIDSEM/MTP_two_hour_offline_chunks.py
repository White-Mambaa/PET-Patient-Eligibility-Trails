#!/usr/bin/env python3
"""Offline, incremental next steps for the MTP, using already saved files.

Three separate tasks (traps, review, policy); run each once in order.
Never uses network, Ollama, inference, held-out data, or changes input files.
No private patient notes are printed or written in outputs.
Result tables describe synthetic expectations / conditional decisions, NOT
independent clinical ground truth or proven patient rescues.
"""
from __future__ import annotations
import argparse
import csv
import hashlib
import json
import os
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path

TRAP_DIR = Path('outputs/research_completion_sprint/cpu_guarded_synthetic_20261021_223247_656178')
TRAP_SOURCE = Path('outputs/research_completion_sprint/overnight_safe_20261020_223633/synthetic_42_cases.jsonl')
REVIEW_DIR = Path('outputs/research_completion_sprint/adjudication_20261020_163130_107196')
IMPACT = Path('outputs/decision_impact/real_priority_analysis.csv')
CATS = ('NEGATION','FAMILY_HISTORY','HYPOTHETICAL','OLD_VALUE','CONTRADICTION','EVIDENCE_REMOVED','THRESHOLD_SHIFT')
CHECKS = ('gold_nonverbatim_quote','gold_unsupported_evidence','gold_context_error',
          'gold_logic_error','gold_contradiction','gold_missed_evidence')
TRUTHS = {'yes','no','unknown'}
VERDICTS = {'met','not_met','not_stated'}


def read_csv(path):
    with path.open(encoding='utf-8-sig', newline='') as f:
        reader = csv.DictReader(f)
        if not reader.fieldnames:
            raise ValueError(f'Missing CSV header: {path}')
        rows=list(reader)
    if any(None in r for r in rows):
        raise ValueError(f'Unexpected extra CSV columns: {path}')
    return list(reader.fieldnames), rows


def read_jsonl(path):
    with path.open(encoding='utf-8') as f:
        return [json.loads(line) for line in f if line.strip()]


def sha(path):
    h=hashlib.sha256()
    with path.open('rb') as f:
        for b in iter(lambda: f.read(1024*1024), b''):h.update(b)
    return h.hexdigest()


def create_file(path, write_fn):
    # Refuse to overwrite any result or human annotation. Mode 0600 for report files.
    fd=os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    try:
        with os.fdopen(fd, 'w', encoding='utf-8', newline='') as f:
            write_fn(f)
    except BaseException:
        path.unlink(missing_ok=True)
        raise


def save_json(path, obj):
    create_file(path, lambda f: json.dump(obj, f, ensure_ascii=False, indent=2))


def save_csv(path, rows, fields):
    def write(f):
        w=csv.DictWriter(f,fieldnames=fields,extrasaction='raise')
        w.writeheader();w.writerows(rows)
    create_file(path, write)


def save_text(path, body):
    create_file(path, lambda f: f.write(body))


def map_truth(t, kind):
    if kind not in ('inclusion','exclusion') or t not in TRUTHS:
        raise ValueError('Bad truth/kind')
    if t=='unknown':return 'not_stated'
    return ('met' if t=='yes' else 'not_met') if kind=='inclusion' else ('not_met' if t=='yes' else 'met')


def decide(vs):
    if any(v not in VERDICTS for v in vs):raise ValueError('Unknown verdict')
    if any(v=='not_met' for v in vs):return 'NOT_ELIGIBLE'
    if vs and all(v=='met' for v in vs):return 'ELIGIBLE'
    return 'REVIEW'


def norm(s):return re.sub(r'\s+',' ',str(s or '')).strip()


def trap_analysis(root,out):
    pred_path=root/TRAP_DIR/'synthetic_results.jsonl'
    src_path=root/TRAP_SOURCE
    saved=read_jsonl(pred_path); sources=read_jsonl(src_path)
    if len(saved)!=42 or len(sources)!=42:
        raise ValueError(f'Need 42 saved results and 42 source probes; found {len(saved)}, {len(sources)}')
    indexed={}
    for p in sources:
        ix=int(p['case_idx'])
        if ix in indexed:raise ValueError('Duplicate source case index')
        if p.get('checked_by_hand') is not False or p.get('synthetic_constructed') is not True:
            raise ValueError('Source expected synthetic unverified cases only')
        indexed[ix]=p
    if set(indexed)!=set(range(42)):raise ValueError('Source case indices not 0..41')
    grouped=defaultdict(list); differences=[]; breakdown=[]; cross=defaultdict(Counter)
    seen=set()
    for r in saved:
        ix=int(r['case_idx'])
        if ix not in indexed or ix in seen:raise ValueError('Unexpected/duplicate saved case index')
        seen.add(ix); src=indexed[ix]
        category=src['trap_type']
        expected=src['expected_truth_after']
        predicted=r.get('predicted_truth')
        if category not in CATS:raise ValueError('Unknown trap category')
        if r.get('trap_id')!=src['trap_id'] or r.get('trap_type')!=category:
            raise ValueError('ID/category mismatch across sources')
        if r.get('expected_truth_synthetic_not_gold')!=expected:
            raise ValueError('Source expectation mismatch')
        if predicted not in TRUTHS and predicted is not None:
            raise ValueError('Invalid prediction')
        if r.get('status') != ('ok' if predicted else 'unparseable'):
            raise ValueError('Contradictory run status')
        agreement=(predicted==expected) if predicted else None
        if r.get('agreement') is not agreement:
            raise ValueError('Saved agreement disagrees with independently recomputed comparison')
        rec={'trap_id':src['trap_id'],'trap_type':category,'criterion_index':src['crit_idx'],
             'expected_synthetic_not_gold':expected,'predicted_truth':predicted or 'unparseable',
             'agreement_with_constructed_expectation':('yes' if agreement else 'no') if agreement is not None else 'unparseable',
             'model_seconds':r.get('seconds'),'expert_gold_verified':'NO'}
        breakdown.append(rec);grouped[category].append(rec)
        cross[category][f'{expected} -> {predicted or "unparseable"}']+=1
        if not agreement:differences.append(rec)
    summary=[]; ncorrect=0
    for cat in CATS:
        group=grouped[cat]
        if len(group)!=6:raise ValueError(f'Expected 6 per category: {cat} got {len(group)}')
        correct=sum(r['agreement_with_constructed_expectation']=='yes' for r in group)
        ncorrect+=correct
        summary.append({'category':cat,'cases':len(group),'synthetic_agreements':correct,
                        'disagreements_or_unparseable':len(group)-correct,
                        'agreement_fraction':f'{correct/len(group):.3f}'})
    save_csv(out/'01_trap_summary.csv',summary,list(summary[0]))
    save_csv(out/'01_trap_disagreements_NO_NOTES.csv',differences,list(breakdown[0]))
    save_json(out/'01_trap_analysis.json',{
        'total':42,'parsed':sum(r['predicted_truth']!='unparseable' for r in breakdown),
        'agreement_with_synthetic_expectations':ncorrect,'overall_agreement_fraction':ncorrect/42,
        'category_confusions':{k:dict(v) for k,v in cross.items()},
        'sha256_saved_predictions':sha(pred_path),'sha256_synthetic_protocol':sha(src_path),
        'limitations':'42 artificial, constructed, unchecked-by-expert notes; not clinical gold; not representative held-out data. No independent evidence checker scored here.'})
    save_text(out/'01_TRAPS_README.txt',
        f'42 preexisting synthetic predictions examined. Agreement {ncorrect}/42.\n'
        'Read 01_trap_summary.csv and 01_trap_disagreements_NO_NOTES.csv.\n'
        'ALL expectations are programmatically constructed and unverified by independent clinical experts.\n'
        'No new model calls. No private notes in reports.\n')
    print('\n=== CHUNK 1: SEVEN SYNTHETIC TRAP TYPES ===')
    for r in summary:print(f"{r['category']:19s} {r['synthetic_agreements']}/6 matches")
    print(f'TOTAL: {ncorrect}/42 matches to constructed expectations; not clinical accuracy')
    print('Disagreements:',len(differences))


def review_analysis(root,out):
    p=root/REVIEW_DIR/'PRIVATE_TERMINAL_REVIEW_WORKING.csv'
    base=root/REVIEW_DIR/'PRIVATE_STAGE2_BASELINE_VISIBLE_REVIEW.csv'
    header,rows=read_csv(p)
    base_header,original=read_csv(base)
    required={'case_id','patient_note_PRIVATE_DO_NOT_UPLOAD','baseline_evidence','criterion_kind',
              'gold_criterion_truth','gold_criterion_verdict','verified_supporting_quote'}|set(CHECKS)
    if not required.issubset(header):raise ValueError('Missing review columns')
    if len(rows)!=49 or len(original)!=49:raise ValueError('Expected 49 review cases')
    oi={r['case_id']:r for r in original}
    if len(oi)!=49 or {r['case_id'] for r in rows}!=set(oi):raise ValueError('Case identity mismatch')
    checks=['criterion_kind','criterion_text','patient_note_PRIVATE_DO_NOT_UPLOAD',
            'baseline_truth','baseline_verdict','baseline_evidence','baseline_rationale']
    if any(any(r.get(k)!=oi[r['case_id']].get(k) for k in checks) for r in rows):
        raise ValueError('Clinical/baseline source field mismatch; stopped, no reports written')
    labels=Counter();flags=[];labeled_cases=0;totals=Counter()
    allowed_binary={'','0','1','uncertain','defer','na','n/a'}
    for r in rows:
        cid=r['case_id']; any_label=False
        for field in CHECKS:
            val=str(r.get(field) or '').strip().lower()
            if val in ('0','1'):labels[field]+=1;any_label=True
            if val not in allowed_binary:
                flags.append({'case_id':cid,'reason':'invalid_binary','column':field,'priority':'high'})
        t=str(r.get('gold_criterion_truth') or '').strip().lower()
        v=str(r.get('gold_criterion_verdict') or '').strip().lower()
        if t in TRUTHS:
            any_label=True;totals['truth_labeled']+=1
            if v!=map_truth(t,r['criterion_kind']):
                flags.append({'case_id':cid,'reason':'truth_verdict_mapping_conflict','column':'gold_criterion_verdict','priority':'high'})
            if t in ('yes','no') and not str(r.get('verified_supporting_quote') or '').strip():
                flags.append({'case_id':cid,'reason':'truth_without_verified_support_quote','column':'verified_supporting_quote','priority':'review'})
        elif t not in ('','uncertain','defer'):
            flags.append({'case_id':cid,'reason':'invalid_truth','column':'gold_criterion_truth','priority':'high'})
        if v and v not in VERDICTS:
            flags.append({'case_id':cid,'reason':'invalid_verdict','column':'gold_criterion_verdict','priority':'high'})
        try:
            quotes=json.loads(r.get('baseline_evidence') or '[]')
            if isinstance(quotes,str):quotes=[quotes]
            if not isinstance(quotes,list) or not all(isinstance(x,str) for x in quotes):raise ValueError()
            expected=int(any(norm(q) not in norm(r['patient_note_PRIVATE_DO_NOT_UPLOAD']) for q in quotes if norm(q)))
            c=str(r.get('gold_nonverbatim_quote') or '').strip()
            if c in ('0','1') and c!=str(expected):
                flags.append({'case_id':cid,'reason':'quotation_label_vs_exact_match','column':'gold_nonverbatim_quote','priority':'high'})
        except (ValueError,TypeError,json.JSONDecodeError):
            flags.append({'case_id':cid,'reason':'unparseable_baseline_evidence','column':'baseline_evidence','priority':'high'})
        if any_label:labeled_cases+=1
    seen=set();unique=[]
    for f in flags:
        key=(f['case_id'],f['reason'],f['column'])
        if key not in seen:seen.add(key);unique.append(f)
    save_json(out/'02_review_qa_NO_NOTES.json',{
        'cases':len(rows),'cases_with_at_least_one_review_label':labeled_cases,
        'binary_labels_per_check':dict(labels),'truth_labels':totals['truth_labeled'],
        'potential_flags':len(unique),'distinct_flagged_cases':len({f['case_id'] for f in unique}),
        'sha256_working_review':sha(p),'sha256_original_review':sha(base),
        'warning':'Flags are mechanical consistency warnings, not clinician verdicts. Author labels are NOT independent expert gold.'})
    save_csv(out/'02_cases_to_recheck_NO_NOTES.csv',unique,['case_id','reason','column','priority'])
    save_text(out/'02_REVIEW_README.txt',
        'No notes leave the laptop and no labels are changed.\n'
        'Use 02_cases_to_recheck_NO_NOTES.csv to prioritize qualified human re-review.\n'
        'Do NOT mechanically turn unknown into no, or assume unlabeled cases are 0.\n'
        'The reviewer must confirm support using the patient note and trial rule.\n')
    print('\n=== CHUNK 2: QUALITY CHECK OF 49 REVIEW CASES ===')
    print('Cases with at least one entered label:',labeled_cases,'/49')
    print('Potential QA flags:',len(unique),'across',len({f['case_id'] for f in unique}),'cases')
    print('Six binary check label counts:',dict(labels))
    print('This is NOT independently verified gold.')


def policy_analysis(root,out):
    p=root/IMPACT
    fields,rows=read_csv(p)
    required={'dataset','pair_idx','crit_idx','verdict'}
    if not required.issubset(fields):raise ValueError('Decision impact fields missing')
    groups=defaultdict(list)
    for r in rows:groups[(r['dataset'],r['pair_idx'])].append(r)
    if len(rows)!=1940 or len(groups)!=152:
        raise ValueError(f'Expected 1940 criteria/152 pairs, got {len(rows)}/{len(groups)}')
    output=[];baselines=Counter();outcomes=Counter()
    for (dataset,pair),recs in sorted(groups.items()):
        pairsort=sorted(recs,key=lambda r:int(r['crit_idx']))
        indexes=[int(r['crit_idx']) for r in pairsort]
        if len(set(indexes))!=len(indexes):raise ValueError('Duplicate rule in pair')
        vs=[r['verdict'] for r in pairsort]
        current=decide(vs)
        baselines[current]+=1
        bad=[j for j,x in enumerate(vs) if x=='not_met']
        if len(bad)!=1:continue
        j=bad[0]
        deferred=vs.copy();deferred[j]='not_stated'
        hypothetical=vs.copy();hypothetical[j]='met'
        after_defer=decide(deferred);after_verified=decide(hypothetical)
        output.append({'dataset':dataset,'pair_idx':pair,'criterion_index':indexes[j],
            'baseline_decision':current,'if_unverified_rule_deferred':after_defer,
            'if_rule_independently_proven_met':after_verified,
            'real_repair_performed':'NO','patient_rescue_verified':'NO'})
        outcomes[(after_defer,after_verified)]+=1
    fields_out=['dataset','pair_idx','criterion_index','baseline_decision','if_unverified_rule_deferred',
                'if_rule_independently_proven_met','real_repair_performed','patient_rescue_verified']
    save_csv(out/'03_sole_rejection_policy_NO_GOLD.csv',output,fields_out)
    save_json(out/'03_policy_summary.json',{
        'all_criterion_predictions':len(rows),'all_development_pairs':len(groups),
        'baseline_decision_counts':dict(baselines),'sole_rejection_candidates':len(output),
        'conditional_outcome_counts':{str(k):v for k,v in outcomes.items()},
        'sha256_input':sha(p),
        'interpretation':'If the sole rejecting criterion is unverified, defer it for review; never auto-correct. The met scenario is hypothetical and only valid if independently verified. Zero clinically verified corrections or rescues.'})
    save_text(out/'03_POLICY_README.txt',
        'CONSERVATIVE POLICY COUNTERFACTUAL -- NOT AN ACTUAL REPAIR EXPERIMENT\n'
        '39 candidate pairs may change under deferral/conditional independently verified corrections.\n'
        'DO NOT claim 39 repaired patients, clinically rescued patients, or improved strict accuracy.\n'
        'A qualified reviewer and re-evaluation are required to validate true outcomes.\n')
    print('\n=== CHUNK 3: CONDITIONAL REVIEW VS REPAIR ===')
    print('Pairs:',len(groups),'criterion predictions:',len(rows))
    print('Baseline decision counts:',dict(baselines))
    print('Sole-rejection candidate pairs:',len(output))
    print('True clinical repairs performed: 0 (counterfactual only)')


def test():
    assert map_truth('yes','inclusion')=='met'
    assert map_truth('no','inclusion')=='not_met'
    assert map_truth('yes','exclusion')=='not_met'
    assert map_truth('no','exclusion')=='met'
    assert map_truth('unknown','exclusion')=='not_stated'
    assert decide(['met','met'])=='ELIGIBLE'
    assert decide(['met','not_stated'])=='REVIEW'
    assert decide(['met','not_met'])=='NOT_ELIGIBLE'
    assert len(CATS)==7 and len(CHECKS)==6
    print('SELF-TEST PASS: 9 deterministic checks; no data files changed; no inference calls')


def main():
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--root',type=Path,default=Path.cwd())
    ap.add_argument('--task',choices=['traps','review','policy'])
    ap.add_argument('--out',type=Path,default=Path('outputs/research_completion_sprint/offline_chunks_20261022'))
    ap.add_argument('--self-test',action='store_true')
    a=ap.parse_args()
    if a.self_test:test();return
    if a.task is None:ap.error('--task required unless --self-test')
    root=a.root.expanduser().resolve()
    if not (root/'code/criteria.py').is_file():raise ValueError('Wrong project root: missing code/criteria.py')
    out=(root/a.out).resolve() if not a.out.is_absolute() else a.out.resolve()
    if not str(out).startswith(str(root/'outputs'/'research_completion_sprint')+'/'):
        raise ValueError('Output directory must be under outputs/research_completion_sprint/')
    out.mkdir(mode=0o700,parents=True,exist_ok=True)
    os.chmod(out,0o700)
    tag={'traps':'01_trap_analysis.json','review':'02_review_qa_NO_NOTES.json','policy':'03_policy_summary.json'}[a.task]
    if (out/tag).exists():
        print('ALREADY COMPLETE, NOT REPEATING:',out/tag)
        return
    {'traps':trap_analysis,'review':review_analysis,'policy':policy_analysis}[a.task](root,out)
    print('OUTPUTS SAVED:',out)
    print('No Ollama calls. No original data changed. No held-out test data accessed.')

if __name__=='__main__':
    try:main()
    except (ValueError,FileNotFoundError,KeyError,TypeError,OverflowError) as e:
        print('ERROR:',type(e).__name__,str(e),file=sys.stderr)
        sys.exit(2)
