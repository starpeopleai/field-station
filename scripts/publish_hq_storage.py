import json,subprocess,time,logging
from logging.handlers import RotatingFileHandler
from pathlib import Path
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'uap-lab'))
from drive_storage import collect
out=Path('/Volumes/UFO-Working-Files/station-storage/hq.json')
if not out.parents[1].is_mount():raise SystemExit('HQ working volume is not mounted')
out.parent.mkdir(exist_ok=True)
log=logging.getLogger('storage');log.setLevel(logging.INFO);log.addHandler(RotatingFileHandler(out.parent/'collector.log',maxBytes=131072,backupCount=1))
for attempt in range(3):
 try:
  tmp=out.with_suffix('.tmp');tmp.write_text(json.dumps(collect('HQ')));tmp.replace(out)
  subprocess.run(['/usr/bin/python3','/Users/ufo-files-agent/field-migration/ssh-field.py','mkdir -p /Volumes/UFO-Field-Working-Files/storage-status'],check=True,timeout=20,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
  subprocess.run(['/opt/homebrew/bin/rsync','-a','--timeout=15','-e','/usr/bin/python3 /Users/ufo-files-agent/storage-reorganization/rsync-field.py',str(out),'field:/Volumes/UFO-Field-Working-Files/storage-status/hq.json'],check=True,timeout=25,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
  log.info('Published HQ storage at %.0f',time.time());break
 except (OSError,ValueError,subprocess.SubprocessError) as error:
  log.warning('Attempt %d failed: %s',attempt+1,type(error).__name__)
  if attempt==2:raise SystemExit(1)
  time.sleep(5*(attempt+1))
