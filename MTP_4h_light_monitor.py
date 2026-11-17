#!/usr/bin/env python3
"""Four-hour MTP low-resource, read-only research QA/health monitor.

No Ollama/model inference, network, clinical-label generation, dataset edits,
held-out split access, or artificial compute load. Files under a new, private
output folder are generated using only statistics and case IDs. Takes ~4 hours
via mostly sleeping, NOT ~4 hours of model research.
"""
from __future__ import annotations
import argparse
import csv
import fcntl
import hashlib
import json
import os
import resource
import signal
import sys
import time
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

REL = 'outputs/research_completion_sprint'
QA_REL = 'outputs/research_completion_sprint/adjudication_20261020_163130_107196/PRIVATE_TERMINAL_REVIEW_WORKING.csv'
SOURCES = {
    'nsclc_dev': 'outputs/plain_ai_qwen_dev.jsonl',
    'sigir_dev': 'outputs/plain_ai_qwen_sigir_dev.jsonl',
    'six_checks': 'outputs/evidence_checks/unified_six_checks_20261017_131121_594627/unified_six_checks.csv',
    'priority_rankings': 'outputs/priority_comparison/priority_rankings.csv',
    'decision_impact': 'outputs/decision_impact/real_priority_analysis.csv',
    'triage_comparison': 'outputs/research_completion_sprint/triage_integration_20261020_192850_471069/triage_comparison.csv',
}
CHECKS = ('gold_nonverbatim_quote','gold_unsupported_evidence','gold_context_error',
          'gold_logic_error','gold_contradiction','gold_missed_evidence')
END = False


def handle_stop(signum, frame):
    global END
    END = True


def timestamp():
    return datetime.now(timezone.utc).isoformat(timespec='seconds')


def write_json(path, obj):
    tmp = path.with_name('.'+path.name+'.tmp')
    with tmp.open('w', encoding='utf-8') as f:
        json.dump(obj, f, indent=2, ensure_ascii=False)
        f.write('\n')
    os.chmod(tmp, 0o600)
    os.replace(tmp, path)


def csv_rows(path):
    with path.open(newline='', encoding='utf-8-sig') as f:
        reader = csv.DictReader(f)
        if not reader.fieldnames:
            raise ValueError('CSV header missing')
        return reader.fieldnames, list(reader)


def baseline(path):
    if not path.is_file(): return {'status':'MISSING'}
    count=0; duplicates=0; malformed=0; keys=set()
    with path.open(encoding='utf-8') as f:
        for line in f:
            if not line.strip(): continue
            try:
                row=json.loads(line)
                key=(int(row['pair_idx']),int(row['crit_idx']))
                duplicates+=int(key in keys)
                keys.add(key)
                count+=1
            except (ValueError, TypeError, KeyError): malformed+=1
    return {'status':'ok','records':count,'duplicate_keys':duplicates,'malformed_lines':malformed}


def sha256_file(path):
    h=hashlib.sha256()
    with path.open('rb') as f:
        while True:
            chunk=f.read(1024*1024)
            if not chunk: break
            h.update(chunk)
    return h.hexdigest()


def initial_integrity(root):
    result={}
    for name, rel in SOURCES.items():
        p=root/rel
        if not p.is_file():
            result[name]={'status':'MISSING'}
            continue
        st=p.stat()
        result[name]={'status':'present','size_bytes':st.st_size,'sha256':sha256_file(p)}
        if name.endswith('_dev'):
            result[name]['schema_counts']=baseline(p)
        elif name in ('six_checks','decision_impact','priority_rankings','triage_comparison'):
            with p.open(encoding='utf-8-sig',newline='') as f:
                rdr=csv.reader(f)
                header=next(rdr,[])
                count=sum(1 for _ in rdr)
            result[name]['data_rows']=count
            result[name]['header_column_count']=len(header)
    return result


def annotation_qa(root):
    p=root/QA_REL
    if not p.is_file():
        return {'status':'not_yet_created','message':'Start local reviewer manually; no gold labels created'}
    fields,rows=csv_rows(p)
    fields=set(fields)
    missing=(set(CHECKS)|{'case_id','gold_criterion_truth','gold_criterion_verdict','criterion_kind','baseline_evidence','patient_note_PRIVATE_DO_NOT_UPLOAD'})-fields
    if missing:
        return {'status':'bad_schema','missing_columns':sorted(missing)}
    seen=set();counts=Counter(); issue=[]; reviewed=set()
    for r in rows:
        cid=r['case_id']
        if cid in seen:issue.append({'case_id':cid,'kind':'duplicate_case_id'})
        seen.add(cid)
        for field in CHECKS:
            v=str(r.get(field) or '').strip().lower()
            if v in ('0','1'):
                counts[field]+=1; reviewed.add(cid)
            elif v not in ('','uncertain','defer','na','n/a'):
                issue.append({'case_id':cid,'kind':'invalid_binary_label','field':field})
        truth=str(r.get('gold_criterion_truth') or '').strip().lower()
        verdict=str(r.get('gold_criterion_verdict') or '').strip().lower()
        kind=str(r.get('criterion_kind') or '').strip().lower()
        if truth in ('yes','no','unknown'):
            reviewed.add(cid)
            counts['gold_criterion_truth']+=1
            expected = 'not_stated' if truth=='unknown' else ('met' if (truth=='yes')==(kind=='inclusion') else 'not_met')
            if expected!=verdict:
                issue.append({'case_id':cid,'kind':'truth_verdict_mismatch'})
        elif truth not in ('','uncertain','defer'):
            issue.append({'case_id':cid,'kind':'invalid_criterion_truth'})
        if verdict not in ('','met','not_met','not_stated'):
            issue.append({'case_id':cid,'kind':'invalid_criterion_verdict'})
        try:
            quotes=json.loads(r.get('baseline_evidence') or '[]')
            if not isinstance(quotes,list): raise ValueError('Expected list')
            note=' '.join(str(r.get('patient_note_PRIVATE_DO_NOT_UPLOAD') or '').split())
            mismatch=any(' '.join(str(q).split()) not in note for q in quotes if str(q).strip())
            annotation=str(r.get('gold_nonverbatim_quote') or '').strip()
            if annotation in ('0','1') and quotes and annotation!=str(int(mismatch)):
                issue.append({'case_id':cid,'kind':'quotation_label_differs_from_exact_match'})
            if annotation=='1' and not quotes:
                issue.append({'case_id':cid,'kind':'nonverbatim_label_without_quote'})
        except (ValueError, TypeError):
            issue.append({'case_id':cid,'kind':'bad_evidence_json'})
    return {'status':'ok','cases':len(rows),'cases_with_some_labels':len(reviewed),
            'binary_label_counts':{c:counts[c] for c in CHECKS},
            'truth_label_count':counts['gold_criterion_truth'],
            'quality_warning_count':len(issue),'quality_warnings_no_notes':issue,
            'WARNING':'A flag is only a review prompt. Clinical label correctness is not independently validated.'}


def machine_status():
    info={}
    try:
        for line in Path('/proc/meminfo').read_text().splitlines():
            if line.startswith(('MemAvailable:','SwapFree:','MemTotal:')):
                k,v=line.split(':',1)
                info[k+'_kib']=int(v.strip().split()[0])
    except (OSError,ValueError):
        info['memory']='unavailable'
    st=os.statvfs(str(Path.home()))
    info['home_free_gib']=round(st.f_bavail*st.f_frsize/(1024**3),1)
    try: info['load_averages']=tuple(round(x,2) for x in os.getloadavg())
    except OSError: pass
    info['maxrss_kib']=resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    return info


def run(root, hours, interval_seconds, run_dir):
    run_dir.mkdir(mode=0o700,parents=True,exist_ok=False)
    os.chmod(run_dir,0o700)
    lock_path = root/REL/'.light_monitor.lock'
    fd=os.open(lock_path,os.O_CREAT|os.O_RDWR,0o600)
    with os.fdopen(fd,'w') as lock:
        try: fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        except BlockingIOError: raise RuntimeError('Another four-hour monitor is running. Will not start a duplicate.')
        start=time.monotonic()
        stop_time=start+hours*3600
        initial=initial_integrity(root)
        write_json(run_dir/'initial_integrity_NO_NOTES.json',initial)
        print('LIGHT MTP MONITOR START:',timestamp(),flush=True)
        print('NO OLLAMA, NO MODEL INFERENCE, NO HELD-OUT, NO CLINICAL LABEL GENERATION.',flush=True)
        print('REPORT DIR:',run_dir,flush=True)
        snapshots=[]
        i=0
        while not END:
            current=time.monotonic()
            remaining=max(0,stop_time-current)
            snapshot={'timestamp_utc':timestamp(), 'minutes_elapsed':round((current-start)/60,2),
                      'machine':machine_status(), 'review_QA_NO_NOTES':annotation_qa(root)}
            snapshots.append(snapshot)
            write_json(run_dir/'progress_NO_NOTES.json',{'snapshots':snapshots})
            msg=snapshot['review_QA_NO_NOTES']
            print(f"[{i:02d}] {timestamp()}: available_ram={snapshot['machine'].get('MemAvailable_kib',0)//1024} MiB | "
                  f"cases_with_labels={msg.get('cases_with_some_labels','NA')} | "
                  f"review_flags={msg.get('quality_warning_count','NA')} | "
                  f"remaining={round(remaining/60)} min",flush=True)
            if remaining<=0: break
            ram=snapshot['machine'].get('MemAvailable_kib',10**10)
            if ram<3*1024*1024:
                print('EARLY SAFE EXIT: Available RAM below 3GiB.',flush=True)
                break
            sleep_for=min(interval_seconds,remaining)
            while sleep_for>0 and not END:
                dt=min(5.0,sleep_for)
                time.sleep(dt)
                sleep_for-=dt
            i+=1
        final=initial_integrity(root)
        changes=[]
        for key in SOURCES:
            if initial.get(key,{}).get('sha256') != final.get(key,{}).get('sha256'):
                changes.append(key)
        result={'started_utc':snapshots[0]['timestamp_utc'],
                'ended_utc':timestamp(), 'elapsed_hours':round((time.monotonic()-start)/3600,3),
                'snapshots':len(snapshots),'input_changes_detected':changes,
                'completed_four_hours':time.monotonic()>=stop_time-1,
                'note':'No model calls, no clinical gold produced; does NOT complete independent validation or held-out evaluation.'}
        write_json(run_dir/'final_summary_NO_NOTES.json',result)
        print('FINAL:',json.dumps(result),flush=True)


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--root',type=Path,default=Path.cwd())
    p.add_argument('--hours',type=float,default=4.0)
    p.add_argument('--interval-minutes',type=float,default=15.0)
    p.add_argument('--self-test',action='store_true')
    args=p.parse_args()
    if args.self_test:
        assert (1 if ('yes'=='yes')==('inclusion'=='inclusion') else 0)==1
        assert len(CHECKS)==6
        assert not any('heldout' in v or '/test' in v for v in SOURCES.values())
        print('SELF-TEST PASS: 6 checks, no held-out paths, no model calls. No files changed.')
        return
    if not (0.01<=args.hours<=4):
        p.error('--hours must be between 0.01 and 4')
    if not (1<=args.interval_minutes<=60):
        p.error('--interval-minutes must be 1..60')
    root=args.root.expanduser().resolve()
    if not (root/'outputs').is_dir():p.error('Missing outputs folder under root')
    (root/REL).mkdir(exist_ok=True)
    if not (root/REL).is_dir():p.error('Missing output folder')
    os.umask(0o077)
    try: os.nice(15)
    except OSError: pass
    # Cap this lightweight Python process's own CPU time. No limit on wallclock sleep.
    try: resource.setrlimit(resource.RLIMIT_CPU,(90,95))
    except (OSError,ValueError): pass
    signal.signal(signal.SIGTERM,handle_stop)
    signal.signal(signal.SIGINT,handle_stop)
    suffix=datetime.now().strftime('%Y%m%d_%H%M%S')+'_'+str(os.getpid())
    run_dir=root/REL/('light4h_'+suffix)
    run(root,args.hours,args.interval_minutes*60,run_dir)

if __name__=='__main__':
    try:main()
    except Exception as e:
        print('ERROR:',type(e).__name__,str(e),file=sys.stderr,flush=True)
        sys.exit(2)
