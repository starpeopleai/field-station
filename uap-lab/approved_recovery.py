"""Explicitly approved partial evidence; never inferred from a missing original."""
import hashlib,json
from pathlib import Path

def source(folder,restore=None):
 folder=Path(folder);path=folder/'recovery-publication.json'
 if not path.exists():return None
 note=json.loads(path.read_text())
 if note.get('operator_approved') is not True or note.get('scope')!='surviving_evidence' or note.get('session_id')!=folder.name or note.get('full_session_available') is not False:raise ValueError('Invalid recovery publication authorization')
 raw=folder/'recovery-original.mp4'
 if raw.is_symlink():raise ValueError('Unsafe recovered source')
 if not raw.is_file() and restore is not None:restore(raw)
 if not raw.is_file():raise ValueError('Approved recovered evidence is unavailable')
 h=hashlib.sha256()
 with raw.open('rb') as stream:
  for chunk in iter(lambda:stream.read(1024*1024),b''):h.update(chunk)
 if h.hexdigest()!=note.get('video_sha256'):raise ValueError('Recovered evidence checksum mismatch')
 return raw
