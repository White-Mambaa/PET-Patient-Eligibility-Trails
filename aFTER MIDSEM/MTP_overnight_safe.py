#!/usr/bin/env python3
"""Safe unattended MTP development sprint: synthetic stress probes and review QA.

Does NOT invent independent gold, edit original outputs, or access held-out trials.
No network calls except optional local Ollama via existing plain_ai.py (--run-model).
Only generated notes use entirely fictional non-person-specific clinical statements.
"""
from __future__ import annotations
import argparse
import csv
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path

REVIEW_REL = Path('outputs/research_completion_sprint/adjudication_20261020_163130_107196/PRIVATE_TERMINAL_REVIEW_WORKING.csv')
STAGE3_REL = Path('outputs/research_completion_sprint/adjudication_20261020_163130_107196/PRIVATE_STAGE3_REPAIR_ADJUDICATION.csv')
CHECKS = ('gold_nonverbatim_quote','gold_unsupported_evidence','gold_context_error','gold_logic_error','gold_contradiction','gold_missed_evidence')
KINDS = ('NEGATION','FAMILY_HISTORY','HYPOTHETICAL','OLD_VALUE','CONTRADICTION','EVIDENCE_REMOVED','THRESHOLD_SHIFT')

# (target rule index, note, expected truth) -- constructed synthetic probes, NOT independent clinical gold.
CASES = {
'NEGATION': [
(6,'For this patient, current ECOG performance status is explicitly 3, not 0 or 1.','no'),
(4,'For this patient, current predicted FEV1 is 42% and not at least 50%.','no'),
(5,'For this patient, current predicted DLCO is 35%; it is below 50%.','no'),
(16,'For this patient, active tuberculosis was explicitly ruled out and testing is negative. There is no active infection.','no'),
(14,'For this patient, no major surgery was performed in the preceding 30 days.','no'),
(10,'For this patient, there has been no prior treatment with PD-1, PD-L1, or CTLA-4 inhibitors.','no'),
],
'FAMILY_HISTORY': [
(6,'The father has an ECOG performance status of 1. No ECOG value is documented for the patient.','unknown'),
(4,'The mother had FEV1 65% predicted. There is no FEV1 measurement for the patient.','unknown'),
(5,'The brother has DLCO 59% predicted. The patient DLCO has not been reported.','unknown'),
(16,'The father has active tuberculosis. Patient infection status has not been documented.','unknown'),
(14,'The mother underwent major surgery ten days ago. The patient surgical history is unavailable.','unknown'),
(10,'The sister previously received pembrolizumab. No treatment history is available for this patient.','unknown'),
],
'HYPOTHETICAL': [
(6,'The patient might attain ECOG status 1 next month. Current ECOG was not assessed.','unknown'),
(4,'Predicted FEV1 might be 60% if measured, but there is no measurement or reliable current value.','unknown'),
(5,'A clinician speculated DLCO might exceed 50%; no DLCO result is documented.','unknown'),
(16,'The patient might have hepatitis B; laboratory results have not returned, and active infection status remains unknown.','unknown'),
(14,'If complications arise, the patient might require future major surgery. Past surgery history is not available.','unknown'),
(10,'A prior anti-PD-1 treatment is possible but the patient record is unavailable; treatment status is undetermined.','unknown'),
],
'OLD_VALUE': [
(6,'Last year the patient had ECOG 1. The current assessment instead shows ECOG 3.','no'),
(4,'Last year predicted FEV1 was 62%. Current predicted FEV1 is 41%.','no'),
(5,'An older DLCO measurement was 65% predicted. Current DLCO is 42% predicted.','no'),
(6,'An older assessment showed ECOG 3. Today the patient has ECOG 1.','yes'),
(4,'The prior predicted FEV1 was 43%. The current predicted FEV1 is 64%.','yes'),
(5,'The prior DLCO was 40% predicted. A current test shows DLCO 58% predicted.','yes'),
],
'CONTRADICTION': [
(6,'Two current records for this patient on the same date conflict: one says ECOG 1 and another says ECOG 3. There is no reconciliation.','unknown'),
(4,'Two equally current tests conflict: predicted FEV1 is 42% and predicted FEV1 is 61%, with no explanation.','unknown'),
(5,'Two current lab reports state DLCO 42% and DLCO 63% predicted, without a way to resolve them.','unknown'),
(16,'Current documentation both confirms active tuberculosis and explicitly rules out active tuberculosis. Neither result is resolved.','unknown'),
(14,'Current records state that the patient underwent major surgery 10 days ago and also that the patient had no surgery in the last 30 days. The conflict is unresolved.','unknown'),
(10,'Two conflicting records state the patient previously received nivolumab and that the patient never received checkpoint inhibitors. Both are dated today.','unknown'),
],
'EVIDENCE_REMOVED': [
(6,'Patient evaluated for a lung trial. No ECOG performance-status information is present.','unknown'),
(4,'Patient evaluated for a lung trial. No FEV1 measurement is available.','unknown'),
(5,'Patient evaluated for a lung trial. The DLCO result is absent.','unknown'),
(16,'Patient evaluated for a lung trial. There is no documented infection status.','unknown'),
(14,'Patient evaluated for a lung trial. There is no prior surgical-history documentation.','unknown'),
(10,'Patient evaluated for a lung trial. Previous treatment history was omitted.','unknown'),
],
'THRESHOLD_SHIFT': [
(4,'For this patient, the current predicted FEV1 value is exactly 49%.','no'),
(4,'For this patient, the current predicted FEV1 value is exactly 50%.','yes'),
(5,'For this patient, the current predicted DLCO value is exactly 49%.','no'),
(5,'For this patient, the current predicted DLCO value is exactly 50%.','yes'),
(6,'For this patient, current ECOG performance status is 2.','no'),
(6,'For this patient, current ECOG performance status is 1.','yes'),
],
}

def now(): return datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ')
def write_json(path, data):
    path.write_text(json.dumps(data,indent=2,ensure_ascii=False)+'\n',encoding='utf-8')
def read_csv(path):
    with path.open(encoding='utf-8-sig',newline='') as f:
        rd=csv.DictReader(f)
        if not rd.fieldnames: raise ValueError('No header: '+str(path))
        return list(rd.fieldnames),list(rd)
def normalize(s): return re.sub(r'\s+',' ',str(s or '')).strip()
def verdict(truth,kind):
    if truth not in ('yes','no'): return 'not_stated'
    if kind=='inclusion': return 'met' if truth=='yes' else 'not_met'
    if kind=='exclusion': return 'not_met' if truth=='yes' else 'met'
    raise ValueError(kind)
def decide(vs):
    if 'not_met' in vs:return 'NOT_ELIGIBLE'
    if vs and all(v=='met' for v in vs):return 'ELIGIBLE'
    return 'REVIEW'


def source_checks(root, out):
    paths={
        'nsclc_dev':root/'outputs/plain_ai_qwen_dev.jsonl',
        'sigir_dev':root/'outputs/plain_ai_qwen_sigir_dev.jsonl',
        'six_checks':root/'outputs/evidence_checks/unified_six_checks_20261017_131121_594627/unified_six_checks.csv',
        'risk':root/'outputs/research_completion_sprint/risk_20261020_163122_173838/risk_budget_summary.csv',
        'triage':root/'outputs/research_completion_sprint/triage_integration_20261020_192850_471069/triage_comparison.csv',
        'impact':root/'outputs/decision_impact/real_priority_analysis.csv',
        'trial_rules':root/'datasets/nsclc100/criteria.csv',
    }
    result={k:{'exists':v.is_file(),'path':str(v.relative_to(root))} for k,v in paths.items()}
    for key in ('nsclc_dev','sigir_dev'):
        p=paths[key]
        if not p.exists():continue
        count=0; keys=set(); bad=0
        with p.open(encoding='utf-8') as f:
            for line in f:
                if not line.strip():continue
                try:
                    r=json.loads(line);key2=(r['pair_idx'],r['crit_idx'])
                    if key2 in keys:bad+=1
                    keys.add(key2); count+=1
                except (ValueError,KeyError,TypeError):bad+=1
        result[key].update({'record_count':count,'duplicate_or_bad':bad})
    write_json(out/'development_integrity.json',result)
    return result


def review_qa(root,out):
    p=root/REVIEW_REL
    if not p.is_file():p=root/STAGE3_REL
    if not p.is_file():
        write_json(out/'review_QA_NO_NOTES.json',{'status':'no review file','reviewers_needed':True})
        return {'status':'no review file'}
    fields,rows=read_csv(p)
    required=set(CHECKS)|{'case_id','criterion_kind','gold_criterion_truth','gold_criterion_verdict','patient_note_PRIVATE_DO_NOT_UPLOAD','baseline_evidence'}
    if not required.issubset(fields):
        raise ValueError('Review file missing required fields: '+str(sorted(required-set(fields))))
    flags=[]; labeled=Counter(); truth=Counter(); labeled_cases=0
    for r in rows:
        cid=r['case_id']
        has_label=False
        for f in CHECKS:
            v=str(r.get(f) or '').strip().lower()
            if v in ('0','1'):labeled[f]+=1;has_label=True
            elif v not in ('','defer','uncertain','na','n/a'):
                flags.append({'case_id':cid,'issue':'invalid_binary','field':f})
        t=str(r.get('gold_criterion_truth') or '').strip().lower()
        v=str(r.get('gold_criterion_verdict') or '').strip().lower()
        if t in ('yes','no','unknown'):
            truth[t]+=1;has_label=True
            expected=verdict(t,r['criterion_kind'])
            if v!=expected:flags.append({'case_id':cid,'issue':'gold_mapping_conflict','expected_verdict':expected})
        elif t not in ('','uncertain','defer'):
            flags.append({'case_id':cid,'issue':'invalid_gold_truth'})
        if has_label:labeled_cases+=1
        try:
            q=json.loads(r.get('baseline_evidence') or '[]')
            if isinstance(q,str):q=[q]
            if not isinstance(q,list):raise ValueError()
        except (json.JSONDecodeError,ValueError,TypeError):
            flags.append({'case_id':cid,'issue':'invalid_quotation_list'});continue
        note=normalize(r['patient_note_PRIVATE_DO_NOT_UPLOAD'])
        mismatch=any(normalize(s) not in note for s in q if normalize(s))
        vl=str(r.get('gold_nonverbatim_quote') or '').strip()
        if q and vl in ('0','1') and vl!=str(int(mismatch)):
            flags.append({'case_id':cid,'issue':'verbatim_label_disagrees_with_literal_match'})
        if not q and vl=='1':
            flags.append({'case_id':cid,'issue':'nonverbatim_flag_without_any_quote'})
        if t in ('yes','no') and not str(r.get('verified_supporting_quote') or '').strip():
            flags.append({'case_id':cid,'issue':'truth_without_documented_verified_quote'})
    report={'file':str(p.relative_to(root)),'cases':len(rows),'cases_with_any_labels':labeled_cases,
            'binary_gold_counts':dict(labeled),'truth_counts':dict(truth),
            'potential_quality_issues':flags,
            'WARNING':'Quality flags are not clinician judgments. Existing labels are NOT independently validated.'}
    write_json(out/'review_QA_NO_NOTES.json',report)
    return report


def counterfactual(root,out):
    p=root/'outputs/decision_impact/real_priority_analysis.csv'
    if not p.is_file():
        write_json(out/'counterfactual_summary_NO_GOLD.json',{'status':'missing decision impact file'})
        return {'status':'missing decision impact file'}
    fields,rows=read_csv(p)
    necessary={'dataset','pair_idx','crit_idx','verdict'}
    if not necessary.issubset(fields):raise ValueError('Impact CSV missing '+str(necessary-set(fields)))
    groups=defaultdict(list)
    for r in rows:groups[(r['dataset'],r['pair_idx'])].append(r)
    candidates=[]; counts=Counter()
    for (dataset,pair), recs in sorted(groups.items()):
        ids=[int(r['crit_idx']) for r in recs]
        if len(ids)!=len(set(ids)):
            raise ValueError(f'Duplicate criterion in impact: {dataset}/{pair}')
        ordered=sorted(recs,key=lambda r:int(r['crit_idx']))
        vs=[r['verdict'] for r in ordered]
        if any(v not in ('met','not_met','not_stated') for v in vs):
            raise ValueError('Unknown baseline verdict in impact')
        d=decide(vs);counts['pairs']+=1;counts[d]+=1
        bad=[i for i,v in enumerate(vs) if v=='not_met']
        if len(bad)!=1:continue
        ix=bad[0]
        defer=list(vs);defer[ix]='not_stated'
        improve=list(vs);improve[ix]='met'
        candidates.append({'dataset':dataset,'pair_idx':pair,'crit_idx':ordered[ix]['crit_idx'],
              'baseline_decision':d,'if_unverified_answer_is_deferred':decide(defer),
              'if_answer_is_independently_verified_as_met':decide(improve),
              'correction_applied':'NO','clinical_error_verified':'NO'})
    path=out/'counterfactual_candidates_NO_GOLD.csv'
    with path.open('w',encoding='utf-8',newline='') as f:
        fields=['dataset','pair_idx','crit_idx','baseline_decision','if_unverified_answer_is_deferred',
                'if_answer_is_independently_verified_as_met','correction_applied','clinical_error_verified']
        w=csv.DictWriter(f,fieldnames=fields);w.writeheader();w.writerows(candidates)
    report={'pair_decisions':dict(counts),'sole_rejection_candidates':len(candidates),
        'interpretation':'Counterfactual routing only; NO clinical truth, error repair, rescued patients, or validated decision improvement.'}
    write_json(out/'counterfactual_summary_NO_GOLD.json',report)
    return report


def load_synthetic(root):
    p=root/'datasets/nsclc100/criteria.csv'
    if not p.is_file():raise FileNotFoundError(p)
    _,rows=read_csv(p)
    rules={(r['trial_id'],int(r['crit_idx'])):r for r in rows}
    result=[]
    for category,examples in CASES.items():
        for j,(idx,note,expected) in enumerate(examples):
            rule=rules.get(('T01',idx))
            if not rule:raise ValueError(f'Missing development rule T01/{idx}')
            rec={'case_idx':len(result),'trap_id':f'SYN_{category}_{j+1:02d}',
                 'trial_id':'T01','crit_idx':idx,'kind':rule['kind'],
                 'criterion':rule['criterion_text'],'note':note,'trap_type':category,
                 'expected_truth_after':expected,'expected_verdict_after':verdict(expected,rule['kind']),
                 'checked_by_hand':False,'synthetic_constructed':True,
                 'methodological_status':'PROGRAMMATIC_STRESS_TEST_NOT_EXPERT_VERIFIED'}
            result.append(rec)
    if len(result)!=42:raise ValueError('Expected 42 synthetic probes')
    return result


def prediction_evaluate(out,probes,pred):
    expected={r['case_idx']:r for r in probes}; rows=[];seen=set();counts=Counter();confusions=defaultdict(Counter)
    with pred.open(encoding='utf-8') as f:
        for line in f:
            if not line.strip():continue
            r=json.loads(line)
            # plain_ai --cases maps case_idx onto pair_idx, with one target rule per case.
            case_idx=int(r['pair_idx']); crit=int(r['crit_idx'])
            if case_idx not in expected:raise ValueError('Unexpected prediction pair_idx')
            e=expected[case_idx]
            if crit!=e['crit_idx']:raise ValueError('Prediction wrong rule index')
            if case_idx in seen:raise ValueError('Duplicate prediction')
            seen.add(case_idx)
            t=str(r.get('truth') or '').strip().lower()
            if t not in ('yes','no','unknown'):raise ValueError('Invalid predicted truth')
            counts['evaluated']+=1
            counts['agreement_with_synthetic_expectation']+=int(t==e['expected_truth_after'])
            counts['different_from_synthetic_expectation']+=int(t!=e['expected_truth_after'])
            confusions[e['trap_type']][('correct' if t==e['expected_truth_after'] else 'different')]+=1
            rows.append({'trap_id':e['trap_id'],'trap_type':e['trap_type'],
                'constructed_expected_truth':e['expected_truth_after'],'predicted_truth':t,
                'matches_constructed_expectation':int(t==e['expected_truth_after']),
                'expert_verified_gold':'NO'})
    with (out/'synthetic_probe_results_NO_CLINICAL_GOLD.csv').open('w',encoding='utf-8',newline='') as f:
        w=csv.DictWriter(f,fieldnames=list(rows[0]) if rows else ['trap_id']);w.writeheader();w.writerows(rows)
    summary={'counts':dict(counts),'per_type':{k:dict(v) for k,v in confusions.items()},
         'coverage':f'{len(seen)}/{len(probes)}',
         'CAUTION':'These are constructed synthetic expectations, not independently verified clinical gold or held-out metrics.'}
    write_json(out/'synthetic_probe_summary.json',summary)
    return summary


def main():
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--root',type=Path,default=Path.cwd())
    ap.add_argument('--run-model',action='store_true',help='Run 42 synthetic inputs through local Qwen with existing plain_ai.py')
    ap.add_argument('--self-test',action='store_true')
    args=ap.parse_args()
    if args.self_test:
        assert verdict('yes','exclusion')=='not_met'
        assert verdict('unknown','inclusion')=='not_stated'
        assert decide(['met','not_stated'])=='REVIEW'
        assert all(len(v)==6 for v in CASES.values())
        assert len(KINDS)==7
        print('SELF-TEST PASS: 7 categories x 6 = 42 synthetic probes; no files modified.');return
    root=args.root.expanduser().resolve()
    if not (root/'code/plain_ai.py').is_file():raise FileNotFoundError('Project plain_ai.py missing; incorrect root?')
    root_out=root/'outputs/research_completion_sprint'
    root_out.mkdir(parents=True,exist_ok=True)
    out=root_out/('overnight_safe_'+datetime.now().strftime('%Y%m%d_%H%M%S'))
    out.mkdir(mode=0o700)
    os.chmod(out,0o700)
    print('OUTPUT:',out,flush=True)
    manifest={'start_time_utc':now(),'root':str(root),'run_model_requested':args.run_model,'outputs':str(out),
      'no_held_out_access':True,'no_human_labels_generated':True,'original_results_changed':False}
    write_json(out/'manifest.json',manifest)
    results={}
    try:
        results['development_integrity']=source_checks(root,out)
        print('Development baseline counts:',{k:(results['development_integrity'][k].get('record_count'),results['development_integrity'][k].get('duplicate_or_bad')) for k in ('nsclc_dev','sigir_dev')},flush=True)
        results['review']=review_qa(root,out)
        print('Review QA: cases with any label:',results['review'].get('cases_with_any_labels'),'; flags:',len(results['review'].get('potential_quality_issues',[])),flush=True)
        results['counterfactual']=counterfactual(root,out)
        print('Sole rejection routing candidates:',results['counterfactual'].get('sole_rejection_candidates'),flush=True)
        probes=load_synthetic(root)
        path=out/'synthetic_42_cases.jsonl'
        with path.open('w',encoding='utf-8') as f:
            for r in probes:f.write(json.dumps(r,ensure_ascii=False)+'\n')
        write_json(out/'synthetic_probe_protocol.json',{'n':42,'categories':{k:len(v) for k,v in CASES.items()},
                 'development_trial_only':'T01','checked_by_hand':False,
                 'warning':'Constructed synthetic stress probes, not independently adjudicated controlled trap study.'})
        print('Prepared 42 synthetic probes across 7 categories. No patient notes included.',flush=True)
        if args.run_model:
            pred=out/'synthetic_42_qwen_predictions.jsonl'
            inter=root/'.venv/bin/python'
            if not inter.is_file():inter=Path(sys.executable)
            cmd=[str(inter),str(root/'code/plain_ai.py'),'--model','qwen2.5:7b','--dataset','trap_set',
                 '--cases',str(path),'--num-ctx','2048','--out',str(pred)]
            print('Launching ONE local Ollama model job; no external API.',flush=True)
            # Store ALL model output in the private report folder; no shell pipes or data uploads.
            with (out/'synthetic_model_run.log').open('w',encoding='utf-8') as f:
                subprocess.run(cmd,cwd=root/'code',stdout=f,stderr=subprocess.STDOUT,check=True,timeout=9*60*60)
            if pred.with_name(pred.name+'.INCOMPLETE').exists():
                raise RuntimeError('Model prediction file has INCOMPLETE marker; not evaluating')
            if not pred.is_file():raise RuntimeError('Model job returned no expected prediction file')
            results['synthetic_model']=prediction_evaluate(out,probes,pred)
            print('Synthetic prediction coverage:',results['synthetic_model']['coverage'],flush=True)
        else:
            print('Model run disabled; add --run-model to execute local Qwen 42-case synthetic stress test.',flush=True)
        manifest.update({'status':'FINISHED','end_time_utc':now()})
        write_json(out/'manifest.json',manifest)
        with (out/'OVERNIGHT_README.txt').open('w',encoding='utf-8') as f:
            f.write('MTP UNATTENDED DEVELOPMENT REPORT\n\n')
            f.write('Read: development_integrity.json, review_QA_NO_NOTES.json, counterfactual_summary_NO_GOLD.json\n')
            f.write('Synthetic: synthetic_probe_protocol.json, synthetic_probe_summary.json if the model finished\n')
            f.write('No independent labels generated; no verified clinical corrections; no held-out evaluation.\n')
            f.write('Human experts must verify any questionable clinical label or constructed trap expectation.\n')
        print('DONE. Reports:',out,flush=True)
    except Exception as e:
        manifest.update({'status':'FAILED','error_type':type(e).__name__,'error':str(e),'end_time_utc':now()})
        write_json(out/'manifest.json',manifest)
        print('ERROR:',type(e).__name__,str(e),file=sys.stderr,flush=True)
        raise

if __name__=='__main__':
    try:main()
    except Exception:sys.exit(2)
