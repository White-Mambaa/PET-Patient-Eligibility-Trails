#!/usr/bin/env python3
"""MTP next-stage LOCAL analysis. No model calls; does not edit original sources.

  --self-test
  --task triage --root ~/MTP/Akash_Kit
  --task review --root ~/MTP/Akash_Kit

Triage applies planned REVIEW routing to the development pair-level baseline;
clinical corrections are never made. Reference is used exclusively to score
an already-fixed routing choice. Review task makes a baseline-visible,
judge-blinded *unlabeled* annotation file from the previous 49-case queue.
"""
from __future__ import annotations
import argparse
import csv
import json
import os
from collections import Counter
from datetime import datetime
from pathlib import Path

STRATEGIES = ('random','confidence','citation','decision_impact','combined')
GOLDS = ('gold_nonverbatim_quote','gold_unsupported_evidence','gold_context_error',
         'gold_logic_error','gold_contradiction','gold_missed_evidence')

def read_csv(path: Path):
    if not path.is_file():
        raise FileNotFoundError(f'Missing file: {path}')
    with path.open(newline='',encoding='utf-8-sig') as f:
        return list(csv.DictReader(f))

def read_jsonl(path: Path):
    if not path.is_file():
        raise FileNotFoundError(f'Missing file: {path}')
    with path.open(encoding='utf-8') as f:
        return [json.loads(s) for s in f if s.strip()]

def to_csv(path: Path,rows,cols=None,private=False):
    if path.exists():
        raise FileExistsError(f'Refusing overwrite: {path}')
    if not rows and not cols:
        raise ValueError('Empty rows and columns')
    flags=os.O_WRONLY|os.O_CREAT|os.O_EXCL
    fd=os.open(str(path), flags, 0o600 if private else 0o644)
    with os.fdopen(fd,'w',newline='',encoding='utf-8') as f:
        w=csv.DictWriter(f,fieldnames=cols or list(rows[0]),extrasaction='raise')
        w.writeheader()
        w.writerows(rows)

def unique_index(rows, fields):
    d={}
    for r in rows:
        k=tuple(int(r[f]) if f in ('pair_idx','crit_idx') else r[f] for f in fields)
        if k in d: raise ValueError(f'Duplicate key {k}')
        d[k]=r
    return d

def latest_one(root, pattern):
    files=sorted(root.glob(pattern))
    if not files: raise FileNotFoundError(f'No match for {pattern}')
    return files[-1]

def triage(root):
    riskfolder=root/'outputs/research_completion_sprint/risk_20261020_163122_173838'
    metrics=latest_one(root,'outputs/neha_metrics_*/baseline_pair_predictions.csv')
    sums=read_csv(riskfolder/'risk_budget_summary.csv')
    actions=read_csv(riskfolder/'proposed_review_actions_NO_GOLD.csv')
    pairs=unique_index(read_csv(metrics),('dataset','pair_idx'))
    if len(pairs)!=152: raise ValueError(f'Expected 152 development pairs; got {len(pairs)}')
    if set(r['reference'] for r in pairs.values())!={'ELIGIBLE','NOT_ELIGIBLE'}:
        raise ValueError('Unexpected reference labels')
    if sum(r['reference']=='ELIGIBLE' and r['prediction']=='NOT_ELIGIBLE' for r in pairs.values())!=28:
        raise ValueError('Expected 28 known false rejection pairs')
    if len(sums)!=70: raise ValueError(f'Expected 70 summary rows, got {len(sums)}')
    if any(r['review_policy']!='sole_rejection' and r['review_policy']!='sole_plus_checker_flag' for r in sums):
        raise ValueError('Unexpected policy')
    out=[]; comparisons=[]
    for method in STRATEGIES:
        subset=[r for r in actions if r['strategy']==method and int(r['criterion_budget'])==100 and r['review_policy']=='sole_rejection']
        targets={(r['dataset'],int(r['pair_idx'])) for r in subset}
        for p in targets:
            if p not in pairs: raise ValueError(f'Missing pair {p}')
            if pairs[p]['prediction']!='NOT_ELIGIBLE': raise ValueError(f'Invalid deferral: not a rejected pair: {p}')
        expected=[r for r in sums if r['strategy']==method and int(r['criterion_budget'])==100 and r['review_policy']=='sole_rejection']
        if len(expected)!=1: raise ValueError(f'Missing summary for {method}')
        score=expected[0]
        deferred_false=sum(pairs[p]['reference']=='ELIGIBLE' for p in targets)
        deferred_correct=sum(pairs[p]['reference']=='NOT_ELIGIBLE' for p in targets)
        if (len(targets),deferred_false,deferred_correct)!=(int(score['unique_pairs_deferred']),int(score['reference_eligible_false_rejections_reviewed']),int(score['reference_not_eligible_correct_rejections_deferred'])):
            raise ValueError(f'Deferral coverage differs from risk report for {method}')
        automatic_wrong_after=28-deferred_false
        strict_after=sum((('REVIEW' if p in targets else r['prediction'])==r['reference']) for p,r in pairs.items())
        if strict_after!=int(score['post_deferral_strict_correct_pairs']):
            raise ValueError(f'Strict correctness mismatch for {method}')
        comparisons.append({'strategy':method,'criterion_budget':100,'pair_count':152,'unique_pairs_deferred':len(targets),
           'false_rejections_deferred':deferred_false,'correct_rejections_deferred':deferred_correct,
           'automatic_false_rejections_remaining':automatic_wrong_after,
           'wrong_rejection_review_coverage':f'{deferred_false/28:.6f}',
           'strict_correct_pairs_after_deferral':strict_after,
           'strict_accuracy_after_deferral':f'{strict_after/152:.6f}',
           'clinical_repairs':0})
        for p,r in sorted(pairs.items()):
            decision='REVIEW' if p in targets else r['prediction']
            out.append({'strategy':method,'dataset':p[0],'pair_idx':p[1],
               'baseline_decision':r['prediction'],'triaged_decision':decision,
               'action':'HUMAN_REVIEW_REQUIRED' if p in targets else 'UNCHANGED',
               'reference_FOR_EVALUATION_ONLY':r['reference'],
               'baseline_correct':str(r['prediction']==r['reference']),
               'triaged_strict_correct':str(decision==r['reference']),
               'no_clinical_auto_repair':'TRUE'})
    dest=root/'outputs/research_completion_sprint'/('triage_integration_'+datetime.now().strftime('%Y%m%d_%H%M%S_%f'))
    dest.mkdir(parents=True,exist_ok=False)
    to_csv(dest/'triage_pair_decisions.csv',out)
    to_csv(dest/'triage_comparison.csv',comparisons)
    lines=['# Development patient-level review routing (budget 100)','',
      'Offline integration of an already fixed criterion priority list into patient-level REVIEW routing. No clinical truth is changed.','',
      'Reference outcome columns are included for post-hoc evaluation only. Strict accuracy counts REVIEW as not correct.','',
      '| Strategy | Pairs sent to REVIEW | False rejections routed to review | Correct rejections routed to review | Remaining automatic false rejections |',
      '|---|---:|---:|---:|---:|']
    for r in comparisons:
        lines.append(f"| {r['strategy']} | {r['unique_pairs_deferred']} | {r['false_rejections_deferred']} | {r['correct_rejections_deferred']} | {r['automatic_false_rejections_remaining']} |")
    lines+=['','These are **not** verified error fixes, achieved patient eligibility improvements, held-out metrics, or independent checker accuracy.']
    (dest/'TRIAGE_INTEGRATION_REPORT.md').write_text('\n'.join(lines)+'\n',encoding='utf-8')
    print('=== DEVELOPMENT TRIAGE PIPELINE ===')
    for x in comparisons:
        print(f"{x['strategy']} @100: deferred={x['unique_pairs_deferred']}; at-risk covered={x['false_rejections_deferred']}/28; correct rejections deferred={x['correct_rejections_deferred']}; strict accuracy={float(x['strict_accuracy_after_deferral']):.2%}")
    print('Patient-level routed decisions:',len(out),'(5 strategies x 152 pairs)')
    print('OUTPUT:',dest)
    print('Inputs changed: NO | Model/API calls: 0 | Held-out data accessed: NO')

def review(root):
    base=root/'outputs/research_completion_sprint/adjudication_20261020_163130_107196'
    src=base/'PRIVATE_BLINDED_REVIEW_FILL_LOCALLY.csv'
    dest=base/'PRIVATE_STAGE2_BASELINE_VISIBLE_REVIEW.csv'
    rows=read_csv(src)
    if len(rows)!=49: raise ValueError(f'Expected 49 review cases; got {len(rows)}')
    if any(any(str(r.get(g,'' )).strip() for g in GOLDS) for r in rows):
        raise ValueError('Source already contains labels. Do not merge blindly; preserve previous reviewer work.')
    preds=[]
    for filename in ('plain_ai_qwen_dev.jsonl','plain_ai_qwen_sigir_dev.jsonl'):
        preds.extend(read_jsonl(root/'outputs'/filename))
    index=unique_index(preds,('dataset','pair_idx','crit_idx'))
    output=[]
    for row in rows:
        k=(row['dataset'],int(row['pair_idx']),int(row['crit_idx']))
        if k not in index: raise KeyError(f'Missing baseline record {k}')
        p=index[k]
        if p['kind']!=row['criterion_kind']: raise ValueError(f'Criterion kind mismatch {k}')
        rec={key:val for key,val in row.items() if key!='sampling_cohort'}
        rec['baseline_truth']=p['truth']
        rec['baseline_verdict']=p['verdict']
        rec['baseline_evidence']=json.dumps(p.get('evidence',[]),ensure_ascii=False)
        rec['baseline_rationale']=p.get('rationale','')
        output.append(rec)
    to_csv(dest,output,private=True)
    print('=== JUDGE-BLINDED SIX-CHECK ANNOTATION WORKSHEET ===')
    print('Records:',len(output))
    print('Baseline answer/quotation/reasoning shown: YES')
    print('AI judge flags/suggested corrections shown: NO')
    print('Independent labels auto-generated: 0')
    print('PRIVATE FILE:',dest)
    print('Original 49-case stage-1 queue and all other inputs changed: NO')
    print('Model/API calls: 0 | Held-out data accessed: NO')
    print('NEXT: Independently review the six gold_* columns. Do not upload patient notes or infer labels from the AI judge.')

def selftest():
    assert unique_index([{'dataset':'nsclc100','pair_idx':'3'}],('dataset','pair_idx'))[('nsclc100',3)]['pair_idx']=='3'
    assert len(STRATEGIES)==5 and len(GOLDS)==6
    assert len(set(STRATEGIES))==5 and len(set(GOLDS))==6
    print('SELF-TEST PASS: parsing, identities, five strategies, six independent labels. No files changed.')

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root',type=Path,default=Path.cwd())
    parser.add_argument('--task',choices=['triage','review'])
    parser.add_argument('--self-test',action='store_true')
    args=parser.parse_args()
    if args.self_test: return selftest()
    if not args.task: parser.error('--task required (triage or review)')
    root=args.root.expanduser().resolve()
    if args.task=='triage': triage(root)
    else: review(root)

if __name__=='__main__':
    try: main()
    except (ValueError,FileNotFoundError,FileExistsError,KeyError) as e:
        print('ERROR:',e)
        raise SystemExit(2)
