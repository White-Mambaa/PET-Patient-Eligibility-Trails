#!/usr/bin/env python3
"""Local human recheck of MTP's QA-flagged development annotations.

No Ollama, no network, no automatic human labels. Handles original multiline CSV
safely via csv.DictReader/DictWriter, validates immutable baseline columns, writes
atomically, keeps a 0600 backup before first edit. Clinical notes stay local.

CLI:
  python3 MTP_targeted_recheck.py --self-test
  python3 MTP_targeted_recheck.py --root ~/MTP/Akash_Kit --status
  python3 MTP_targeted_recheck.py --root ~/MTP/Akash_Kit --review
  python3 MTP_targeted_recheck.py --root ~/MTP/Akash_Kit --review --case REVIEW-006
"""
from __future__ import annotations
import argparse, csv, json, os, re, shutil, sys, tempfile
from collections import Counter
from datetime import datetime
from pathlib import Path

REVIEW = Path('outputs/research_completion_sprint/adjudication_20261020_163130_107196')
QA = Path('outputs/research_completion_sprint/offline_chunks_20261022/02_cases_to_recheck_NO_NOTES.csv')
WORK = 'PRIVATE_TERMINAL_REVIEW_WORKING.csv'
ORIG = 'PRIVATE_STAGE2_BASELINE_VISIBLE_REVIEW.csv'
CHECKS = [
    ('gold_nonverbatim_quote','A purported direct quotation is absent verbatim from the note'),
    ('gold_unsupported_evidence','Evidence cited fails to support the clinical claim'),
    ('gold_context_error','Negation, historical/relative, timing, hypothetical, or qualification is misread'),
    ('gold_logic_error','Criterion logic or reasoning is wrong'),
    ('gold_contradiction','Assertion contradicts the note'),
    ('gold_missed_evidence','Relevant existing note evidence overlooked (not just missing data)'),
]
FIELD_RULES = {f: {'','0','1','uncertain','defer'} for f,_ in CHECKS}
FIELD_RULES.update({
    'gold_criterion_truth': {'','yes','no','unknown','uncertain','defer'},
    'gold_criterion_verdict': {'','met','not_met','not_stated'},
    'correction_verified': {'','0','1','yes','no','true','false','uncertain','defer'},
})
IMMUTABLE = ['case_id','dataset','pair_idx','crit_idx','criterion_kind','criterion_text',
             'patient_note_PRIVATE_DO_NOT_UPLOAD','baseline_truth','baseline_verdict',
             'baseline_evidence','baseline_rationale']


def read_csv(p):
    with p.open('r',encoding='utf-8-sig',newline='') as f:
        rd=csv.DictReader(f)
        if rd.fieldnames is None: raise ValueError('Missing CSV header: '+str(p))
        rows=list(rd)
        return list(rd.fieldnames), rows


def safe_write(p,fields,rows):
    fd,name=tempfile.mkstemp(prefix='.mtp_recheck_',suffix='.csv',dir=p.parent)
    try:
        with os.fdopen(fd,'w',encoding='utf-8',newline='') as f:
            w=csv.DictWriter(f,fieldnames=fields,extrasaction='raise')
            w.writeheader();w.writerows(rows)
            f.flush();os.fsync(f.fileno())
        os.chmod(name,0o600)
        os.replace(name,p)
    finally:
        if os.path.exists(name):os.unlink(name)


def mapping(t,kind):
    if t=='unknown': return 'not_stated'
    if t not in ('yes','no') or kind not in ('inclusion','exclusion'):
        raise ValueError('Invalid truth/kind mapping')
    return ('met' if t=='yes' else 'not_met') if kind=='inclusion' else ('not_met' if t=='yes' else 'met')


def norm(v):return re.sub(r'\s+',' ',str(v)).strip()


def assert_intact(fields,rows,original):
    if len(rows)!=49 or len(original)!=49: raise ValueError('Review files must both contain 49 records')
    if len({r.get('case_id') for r in rows})!=49 or len({r.get('case_id') for r in original})!=49:
        raise ValueError('Duplicate case IDs')
    ref={r['case_id']:r for r in original}
    if {r['case_id'] for r in rows}!=set(ref):raise ValueError('Case IDs changed')
    missing=set(IMMUTABLE)|set(FIELD_RULES)|{'verified_supporting_quote','correction_reviewer_notes'}
    if not missing.issubset(fields):raise ValueError('Missing working columns: '+str(sorted(missing-set(fields))))
    for r in rows:
        cid=r['case_id']
        if None in r:raise ValueError('Unexpected CSV columns for '+cid)
        for k in IMMUTABLE:
            if r.get(k)!=ref[cid].get(k):
                raise ValueError(f'Source mismatch in {cid}/{k}; refusing edits')
        for k,accept in FIELD_RULES.items():
            value=str(r.get(k) or '').strip().lower()
            if value not in accept and k!='correction_verified':
                raise ValueError(f'Invalid label {cid}/{k}; refusing edits')
    return ref


def load_flags(path):
    _,rows=read_csv(path)
    ids=[]; reasons={}
    for r in rows:
        cid=r.get('case_id','')
        if not re.fullmatch(r'REVIEW-\d{3}',cid):raise ValueError('Invalid QA case identifier')
        if cid not in reasons:ids.append(cid);reasons[cid]=[]
        reasons[cid].append(f"{r.get('reason','')} ({r.get('column','')})")
    return ids,reasons


def prompt(name,current,accepted=None):
    while True:
        try: s=input(f'{name} [now: {current!r}] (Enter keep, clear, skip, quit): ').strip()
        except (EOFError,KeyboardInterrupt):return None,'quit'
        if not s:return current,'ok'
        if s.lower()=='quit':return None,'quit'
        if s.lower()=='skip':return None,'skip'
        if s.lower()=='clear':return '','ok'
        if accepted is not None and s.lower() not in accepted:
            print('Allowed:',', '.join(sorted(accepted)), '(Enter/clear/skip/quit)');continue
        return s.lower() if accepted is not None else s,'ok'


def one_case(row, reasons):
    cid=row['case_id']
    print('\n'+'='*70)
    print('CASE',cid,'|',row.get('dataset'), 'pair',row.get('pair_idx'),'rule',row.get('crit_idx'))
    print('QA warnings (NOT expert verdicts):', '; '.join(reasons) if reasons else 'selected by case id')
    print('CRITERION KIND:',row['criterion_kind'])
    print('CRITERION:\n'+row['criterion_text'])
    print('NOTE [PRIVATE, LOCAL ONLY]:\n'+row['patient_note_PRIVATE_DO_NOT_UPLOAD'])
    print('Original baseline truth:',row['baseline_truth'])
    print('Original baseline verdict:',row['baseline_verdict'])
    print('Baseline quote:',row['baseline_evidence'])
    print('Baseline rationale:',row['baseline_rationale'])
    try:
        q=json.loads(row.get('baseline_evidence') or '[]')
        if isinstance(q,str):q=[q]
        if isinstance(q,list) and all(isinstance(x,str) for x in q):
            matched=all(norm(x) in norm(row['patient_note_PRIVATE_DO_NOT_UPLOAD']) for x in q if norm(x))
            print('Mechanical verbatim quote check:', 'ALL QUOTES MATCH' if matched else 'QUOTE NOT MATCHED',
                  '(not evidence of clinical correctness)')
    except (ValueError,TypeError):print('Mechanical quote check unavailable')
    new=dict(row)
    print('\nEnter human-reviewed answers only. You may preserve blanks/uncertain.')
    truth,flag=prompt('gold_criterion_truth',str(new.get('gold_criterion_truth') or '').strip().lower(),FIELD_RULES['gold_criterion_truth'])
    if flag!='ok':return None,flag
    new['gold_criterion_truth']=truth
    if truth in ('yes','no','unknown'):
        new['gold_criterion_verdict']=mapping(truth,row['criterion_kind'])
        print('Deterministically mapped gold_criterion_verdict =',new['gold_criterion_verdict'])
    else:
        new['gold_criterion_verdict']=''
    for f,desc in CHECKS:
        print('  '+desc)
        value,flag=prompt(f,str(new.get(f) or '').strip().lower(),FIELD_RULES[f])
        if flag!='ok':return None,flag
        new[f]=value
    for f,desc in [('verified_supporting_quote','Exact supporting text; keep empty if unverified'),
                    ('correction_reviewer_notes','Brief justification; identify reviewer role')]:
        value,flag=prompt(f+': '+desc,str(new.get(f) or ''))
        if flag!='ok':return None,flag
        new[f]=value
    if new.get('gold_criterion_truth') in ('yes','no') and not str(new.get('verified_supporting_quote') or '').strip():
        print('WARNING: definite clinical truth has no verified supporting quote; consider uncertain.')
    print('Changes prepared for',cid,'(not yet saved).')
    while True:
        try:answer=input('Save this case? [yes/no]: ').strip().lower()
        except (EOFError,KeyboardInterrupt):return None,'quit'
        if answer in ('yes','y'):return new,'ok'
        if answer in ('no','n'):return None,'skip'


def test():
    assert mapping('no','inclusion')=='not_met'
    assert mapping('yes','exclusion')=='not_met'
    assert mapping('unknown','inclusion')=='not_stated'
    assert norm('a  b\nc')=='a b c'
    assert 'gold_contradiction' in FIELD_RULES
    print('SELF-TEST PASS: 5 checks. No data files changed, no model calls.')


def main():
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--root',type=Path,default=Path.cwd())
    ap.add_argument('--status',action='store_true')
    ap.add_argument('--review',action='store_true')
    ap.add_argument('--case',default=None)
    ap.add_argument('--all-labeled',action='store_true',help='Recheck all cases having an entered human label')
    ap.add_argument('--self-test',action='store_true')
    a=ap.parse_args()
    if a.self_test:test();return
    root=a.root.expanduser().resolve()
    folder=root/REVIEW
    working=folder/WORK
    original=folder/ORIG
    if not working.is_file() or not original.is_file():raise FileNotFoundError('Missing working or original review worksheet')
    fields, rows=read_csv(working)
    _, orig=read_csv(original)
    assert_intact(fields,rows,orig)
    ids, why=load_flags(root/QA)
    rby={r['case_id']:i for i,r in enumerate(rows)}
    if any(cid not in rby for cid in ids):raise ValueError('QA case ID missing from review worksheet')
    print('=== MTP TARGETED HUMAN REVIEW ===')
    print('Existing working cases:',len(rows))
    print('Flagged cases:',len(ids))
    print('Selected case IDs:',', '.join(ids))
    print('Patient notes will NOT be printed in --status mode.')
    print('No inference or networking in this tool.')
    if a.status:return
    if not a.review:
        print('Use --review to begin, or --review --case REVIEW-006 for one case.');return
    if a.case and a.all_labeled:raise ValueError('Choose either --case or --all-labeled')
    if a.all_labeled:
        ids=[r['case_id'] for r in rows if (any(str(r.get(k) or '').strip().lower() in ('0','1') for k,_ in CHECKS) or str(r.get('gold_criterion_truth') or '').strip().lower() in ('yes','no','unknown'))]
        print('Recheck ALL previously labeled cases:',len(ids))
    if a.case:
        if a.case not in rby:raise ValueError('Case ID absent')
        ids=[a.case]
    backup=None
    for cid in ids:
        i=rby[cid]
        updated, action=one_case(rows[i],why.get(cid,[]))
        if action=='quit':break
        if updated is None:continue
        if updated==rows[i]:
            print('No change for',cid);continue
        if backup is None:
            backup=folder/('PRIVATE_TERMINAL_REVIEW_BEFORE_RECHECK_'+datetime.now().strftime('%Y%m%d_%H%M%S_%f')+'.csv')
            shutil.copy2(working,backup)
            os.chmod(backup,0o600)
            print('Private backup:',backup.name)
        rows[i]=updated
        safe_write(working,fields,rows)
        print('SAVED:',cid)
    print('Done. Files stay local. Clinical labels require qualified review.')
    print('To rerun QA use two-hour chunks --task review with a NEW --out directory.')

if __name__=='__main__':
    try:main()
    except (ValueError,FileNotFoundError) as e:
        print('ERROR:',e,file=sys.stderr);sys.exit(2)
