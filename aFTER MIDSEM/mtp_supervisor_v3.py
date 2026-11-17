#!/usr/bin/env python3
"""Bounded supervisor for the uploaded MTP development checker. Standard library only."""
import argparse, datetime, fcntl, json, os, re, runpy, subprocess, sys, time
from pathlib import Path

OUT='outputs/mtp_completion/nsclc100/dev/plain_ai_qwen_dev_checks_theta95_fallback_exploratory.jsonl'
STM='outputs/mtp_completion/nsclc100/dev/rule_statements_dev95_with_source_fallback.csv'
def save(p, data):
    tmp=p.with_suffix(p.suffix+'.tmp'); tmp.write_text(json.dumps(data,indent=2)); tmp.replace(p)
def read(p, default):
    return json.loads(p.read_text()) if p.exists() else default

def classify(message):
    m=message.lower()
    if 'http 429' in m: return 'rate_limit'
    if any('http '+str(c) in m for c in (500,502,503,504)): return 'server_error'
    if 'budget' in m: return 'budget'
    if 'transport' in m: return 'transport_ambiguous'
    if 'http 401' in m or 'http 403' in m: return 'credentials_or_access'
    return 'validation_or_configuration'

def coverage(root):
    p=root/OUT
    if not p.exists():return 0
    keys=set()
    with p.open() as f:
        for line in f:
            if line.strip():
                r=json.loads(line); keys.add((r['pair_idx'],r['crit_idx']))
    return len(keys)

def worker(root, state):
    sys.path[:0]=[str(root/'code'),str(root)]
    import urllib.request, urllib.error
    from llm_client import CallFailed
    ledger=state/'requests.json'; failure=state/'failure.json'
    original=urllib.request.urlopen
    def guarded(req,*args,**kwargs):
        url=getattr(req,'full_url',str(req))
        if url=='https://api.groq.com/openai/v1/chat/completions':
            data=read(ledger,{})
            if data['attempts']>=data['max_attempts']:raise CallFailed('Supervisor total request budget reached')
            data['attempts']+=1;save(ledger,data)
            try:return original(req,*args,**kwargs)
            except urllib.error.HTTPError as e:
                # Do not log response bodies: they can contain clinical prompts.
                save(failure,{'message':'Groq HTTP '+str(e.code),'retry_after':e.headers.get('Retry-After','')});raise
        return original(req,*args,**kwargs)
    urllib.request.urlopen=guarded
    def trace(frame,event,arg):
        if event=='exception' and frame.f_code.co_name=='run_check':
            typ,error,_=arg
            if isinstance(error,CallFailed):
                msg=str(error).replace(os.environ.get('GROQ_API_KEY','__NO_KEY__'),'[REDACTED]')
                data=read(failure,{})
                data['message']=msg[:1000];save(failure,data)
                print('CHECK FAILURE:',msg[:1000],flush=True)
        return trace
    sys.settrace(trace)
    sys.argv=['completion.py','check','--root',str(root),'--dataset','nsclc100','--split','dev',
      '--backend','groq','--model','openai/gpt-oss-20b','--pred','outputs/plain_ai_qwen_dev.jsonl',
      '--statements',STM,'--theta','95','--limit','0','--max-calls','1000',
      '--allow-unreviewed-statements','--out',OUT]
    os.chdir(root);runpy.run_path(str(root/'completion.py'),run_name='__main__')

def configure_keys(path):
    import getpass
    if not sys.stdin.isatty():raise SystemExit('Run key setup directly in an interactive terminal.')
    print('Enter only authorised Groq keys. Input is hidden. Blank entry finishes.')
    keys=[]
    while True:
        key=getpass.getpass('Groq key '+str(len(keys)+1)+': ').strip()
        if not key:break
        if not key.startswith('gsk_'):
            print('Expected a Groq gsk_ key; entry not saved.');continue
        if key not in keys:keys.append(key)
    if not keys:raise SystemExit('No keys entered; nothing saved.')
    path=path.expanduser();path.parent.mkdir(parents=True,exist_ok=True)
    with path.open('x') as f:
        os.chmod(path,0o600);json.dump({'keys':keys},f)
    print('Saved',len(keys),'keys privately. Do not upload the key file.')

def load_keys(path):
    import stat
    path=path.expanduser()
    if path.is_symlink():raise SystemExit('Key file must not be a symlink.')
    if not path.exists():return []
    if stat.S_IMODE(path.stat().st_mode)&0o077:raise SystemExit('Key file permissions must be 600.')
    keys=read(path,{}).get('keys',[])
    if not isinstance(keys,list) or not keys or any(not isinstance(k,str) or not k.startswith('gsk_') for k in keys):raise SystemExit('Invalid Groq key file.')
    return list(dict.fromkeys(keys))

def main():
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--key-file',type=Path,default=Path.home()/'.config/mtp/groq_keys.json');ap.add_argument('--configure-keys',action='store_true');ap.add_argument('--root',type=Path,default=Path.cwd());ap.add_argument('--max-attempts',type=int,default=2500)
    ap.add_argument('--hours',type=float,default=24);ap.add_argument('--max-restarts',type=int,default=30)
    ap.add_argument('--retry-ambiguous-network',action='store_true',help='Allow at most 3 retries without saved-row progress after network errors; a timed-out request may still be charged');ap.add_argument('--worker',type=Path,help=argparse.SUPPRESS);ap.add_argument('--self-test',action='store_true')
    a=ap.parse_args();os.umask(0o077)
    if a.self_test:
        import tempfile
        assert classify('Groq HTTP 429')=='rate_limit'
        assert classify('Transport failed')=='transport_ambiguous'
        assert classify('Model response is not a JSON object')=='validation_or_configuration'
        assert classify('API attempt budget reached')=='budget'
        with tempfile.TemporaryDirectory() as d:
            p=Path(d)/'state.json';save(p,{'attempts':3});assert read(p,{})['attempts']==3
            r=Path(d);p=r/OUT;p.parent.mkdir(parents=True);p.write_text('{"pair_idx":1,"crit_idx":2}\n'*2)
            assert coverage(r)==1
        print('SELF-TEST PASS: error classification, atomic state, duplicate-safe coverage');return
    if a.configure_keys:return configure_keys(a.key_file)
    root=a.root.expanduser().resolve()
    if a.worker:return worker(root,a.worker)
    if a.max_attempts<1 or a.hours<=0 or a.max_restarts<0:ap.error('Limits must be positive (restarts may be zero)')
    keys=load_keys(a.key_file)
    current=os.environ.get('GROQ_API_KEY','').strip()
    if current:keys=list(dict.fromkeys([current]+keys))
    if not keys:raise SystemExit('No keys configured; run --configure-keys first.')
    key_index=0;os.environ['GROQ_API_KEY']=keys[key_index]
    for rel in ('completion.py','mtp_completion/workflow.py',STM,'outputs/plain_ai_qwen_dev.jsonl'):
        if not (root/rel).is_file():raise SystemExit('Missing input: '+rel)
    base=root/'outputs/mtp_supervisor';base.mkdir(parents=True,exist_ok=True)
    lock=(base/'supervisor.lock').open('w')
    try:fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
    except BlockingIOError:raise SystemExit('Another supervisor is already running')
    stamp=datetime.datetime.now().strftime('%Y%m%d_%H%M%S_%f');state=base/stamp;state.mkdir()
    save(state/'requests.json',{'attempts':0,'max_attempts':a.max_attempts})
    start=time.monotonic();deadline=start+a.hours*3600;process=None;last_count=coverage(root);stalled=0
    def status(label,restarts):
        n=coverage(root);data={'status':label,'completed':n,'expected':950,'remaining':max(0,950-n),
         'requests_this_session':read(state/'requests.json',{}),'restarts':restarts,'session':str(state),
         'updated_utc':datetime.datetime.now(datetime.timezone.utc).isoformat(),
         'scope':'NSCLC development; exploratory; no human labels created', 'last_failure':read(state/'failure.json',{}), 'retry_ambiguous_network':a.retry_ambiguous_network}
        save(base/'STATUS.json',data);return data
    print('STATUS FILE:',base/'STATUS.json',flush=True)
    try:
        for restart in range(a.max_restarts+1):
            if time.monotonic()>=deadline:status('TIME_LIMIT',restart);return
            (state/'failure.json').unlink(missing_ok=True)
            status('RUNNING',restart)
            env=os.environ.copy();env['LOGURU_LEVEL']='WARNING'
            with (state/'console.log').open('a') as log:
                process=subprocess.Popen([sys.executable,'-u',str(Path(__file__).resolve()),'--root',str(root),'--worker',str(state)],stdout=log,stderr=subprocess.STDOUT,env=env)
                while process.poll() is None:
                    if time.monotonic()>=deadline:
                        process.send_signal(2)
                        try:process.wait(timeout=15)
                        except subprocess.TimeoutExpired:process.terminate();process.wait()
                        status('TIME_LIMIT',restart);return
                    data=status('RUNNING',restart)
                    print('Saved:',data['completed'],'/ 950 | API attempts:',data['requests_this_session']['attempts'],flush=True)
                    time.sleep(10)
            process=None
            manifest=read(Path(str(root/OUT)+'.manifest.json'),{})
            if manifest.get('status')=='COMPLETE' and coverage(root)==950:
                status('COMPLETE',restart);print('COMPLETE: 950/950 exploratory checks saved.');return
            fail=read(state/'failure.json',{});msg=fail.get('message','No classified error; inspect console.log')
            kind=classify(msg);print('STOP DETAIL:',msg,flush=True)
            count=coverage(root)
            stalled=stalled+1 if count==last_count else 0
            last_count=count
            retryable=kind in ('rate_limit','server_error') or (kind=='transport_ambiguous' and a.retry_ambiguous_network and stalled<3)
            # One automatic retry for a malformed response; repeated cached/schema
            # failures require a fix, never a fabricated successful annotation.
            retryable=retryable or (kind=='validation_or_configuration' and 'response' in msg.lower() and stalled<1)
            if kind=='credentials_or_access' and key_index+1<len(keys) and restart<a.max_restarts:
                key_index+=1;os.environ['GROQ_API_KEY']=keys[key_index]
                status('SWITCHING_REJECTED_KEY',restart)
                print('Key rejected; switching to next configured authorised key.',flush=True)
                continue
            if not retryable or restart==a.max_restarts:
                status('NEEDS_ATTENTION: '+kind,restart);return
            wait=min(1800,60*2**min(restart,5))
            retry=fail.get('retry_after','')
            if kind=='transport_ambiguous':print('Network retry may incur a duplicate charge; bounded retry enabled.',flush=True)
            if retry:
                import email.utils
                try:wait=max(wait,float(retry))
                except ValueError:
                    try:wait=max(wait,email.utils.parsedate_to_datetime(retry).timestamp()-time.time())
                    except (TypeError,ValueError):pass
            status('WAITING: '+kind,restart)
            if time.monotonic()+wait>=deadline:status('PAUSED_UNTIL_QUOTA_OR_TIME_RESET',restart);return
            end=time.monotonic()+wait
            while time.monotonic()<end:
                status('WAITING: '+kind,restart);time.sleep(min(10,max(0,end-time.monotonic())))
        status('RESTART_LIMIT',a.max_restarts)
    except KeyboardInterrupt:
        if process and process.poll() is None:
            process.send_signal(2)
            try:process.wait(timeout=15)
            except subprocess.TimeoutExpired:process.terminate();process.wait()
        status('INTERRUPTED',0);print('Stopped; checkpoints retained.')
    except Exception as e:
        if process and process.poll() is None:
            process.send_signal(2)
            try:process.wait(timeout=15)
            except subprocess.TimeoutExpired:process.terminate();process.wait()
        status('SUPERVISOR_ERROR: '+type(e).__name__,0)
        print('Supervisor error:',type(e).__name__,'; checkpoints retained.');raise
if __name__=='__main__':main()
