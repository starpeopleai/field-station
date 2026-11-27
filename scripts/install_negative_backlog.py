"""Install the bounded-negative sampler as a per-user macOS service."""
import argparse,json,os,plistlib,subprocess,time
from pathlib import Path

def main():
    parser=argparse.ArgumentParser();parser.add_argument('--app',required=True);parser.add_argument('--data',required=True);parser.add_argument('--enable',action='store_true');args=parser.parse_args()
    app=Path(args.app).resolve();data=Path(args.data)
    if not data.is_dir() or not data.parent.is_mount():raise ValueError('Field volume must be mounted')
    python=app/'venv/bin/python';worker=app/'uap-lab/negative_backlog.py'
    if not python.is_file() or not worker.is_file():raise ValueError('Station installation unavailable')
    environment=json.loads((app/'environment.json').read_text())
    policy=data/'negative-backlog-policy.json'
    current=json.loads(policy.read_text()) if policy.exists() else {}
    current.update(enabled=args.enable,max_items=1000,max_bytes=25*1024**3,grace_seconds=900)
    temp=policy.with_suffix('.tmp');temp.write_text(json.dumps(current));temp.replace(policy)
    label='app.starpeople.field.negative-backlog';domain='gui/'+str(os.getuid())
    # launchd cannot reliably open removable-volume logs before Python starts.
    logs=Path.home()/'Library/Logs/field-station';logs.mkdir(parents=True,exist_ok=True)
    agents=Path.home()/'Library/LaunchAgents';agents.mkdir(parents=True,exist_ok=True)
    plist=agents/(label+'.plist')
    spec=dict(Label=label,ProgramArguments=[str(python),str(worker),'--data',str(data),'--apply','--watch'],WorkingDirectory=str(app),EnvironmentVariables={'XDG_RUNTIME_DIR':environment.get('XDG_RUNTIME_DIR',str(data.parent/'station-runtime')),'PATH':'/opt/homebrew/bin:/usr/bin:/bin','PYTHONUNBUFFERED':'1'},RunAtLoad=True,KeepAlive=True,ThrottleInterval=30,ProcessType='Standard',StandardOutPath='/dev/null',StandardErrorPath=str(logs/'negative-backlog.error.log'))
    subprocess.run(['launchctl','bootout',domain+'/'+label],capture_output=True)
    for attempt in range(60):
        if subprocess.run(['launchctl','print',domain+'/'+label],capture_output=True).returncode:break
        time.sleep(.5)
    else:raise RuntimeError('Previous sampler is still stopping; retry installation')
    plist.write_bytes(plistlib.dumps(spec))
    subprocess.run(['launchctl','bootstrap',domain,str(plist)],check=True)
    print(json.dumps(dict(service=label,policy=current,status=str(data/'negative-backlog-status.json'))))

if __name__=='__main__':main()
