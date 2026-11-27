#!/usr/bin/env python3
"""Install a user LaunchAgent; metadata stays on the external field working drive."""
import argparse, os, plistlib, subprocess, sys
from pathlib import Path
p=argparse.ArgumentParser();p.add_argument('--root',type=Path,required=True);args=p.parse_args()
root=args.root.resolve();repo=Path(__file__).resolve().parents[1]
if not str(root).startswith('/Volumes/') or not Path('/Volumes',root.parts[2]).is_mount():raise SystemExit('External field storage unavailable')
label='ai.starpeople.field.air-traffic';path=Path.home()/'Library/LaunchAgents'/f'{label}.plist';path.parent.mkdir(parents=True,exist_ok=True)
value=dict(Label=label,ProgramArguments=[sys.executable,str(repo/'uap-lab/air_traffic.py'),'--root',str(root)],RunAtLoad=True,KeepAlive=True,ThrottleInterval=60,ProcessType='Background',Nice=10)
path.write_bytes(plistlib.dumps(value));domain=f'gui/{os.getuid()}'
subprocess.run(['launchctl','bootout',domain,str(path)],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
subprocess.run(['launchctl','bootstrap',domain,str(path)],check=True)
print('Air-traffic collector installed')
