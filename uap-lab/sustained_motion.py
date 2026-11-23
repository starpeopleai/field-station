"""One full-session recording for moving anomalous proposals in a camera generation."""
import hashlib
import json
import math
import sqlite3
from contextlib import closing
from datetime import datetime, timezone
from pathlib import Path
from spool_events import atomic

PRE_ROLL = 10
QUIET_SECONDS = 10
MIN_DURATION = 2
MIN_TRAVEL = 12

class SustainedMotion:
    def __init__(self, root):
        self.root = Path(root)
        self.generation = None
        self.event = None
        self.tracks = []
        self.saved = None

    def checkpoint(self):
        if self.event:
            atomic(self.root/self.generation/'open-sustained.json',dict(self.event, tracks=self.tracks))
            self.saved = self.event['last_seen_pts']

    def finish(self, interrupted=False):
        if self.event:
            event = self.event
            path = self.root/self.generation/'events'/(event['session_id']+'.json')
            if not path.exists():
                atomic(path,dict(event,state='ready',interrupted=interrupted,finish_reason='capture_interrupted' if interrupted else 'post_roll_complete'))
            (self.root/self.generation/'open-sustained.json').unlink(missing_ok=True)
        self.event = self.saved = None
        self.tracks = []

    def update(self,generation,row,model):
        if generation != self.generation:
            self.finish(True)
            self.generation = generation
            pin = self.root/generation/'open-sustained.json'
            if pin.exists():
                self.event = json.loads(pin.read_text())
                self.tracks = self.event.pop('tracks',[])
        pts = row['pts_seconds']
        if self.event and pts <= self.event['last_seen_pts']:
            return
        if self.event and pts > self.event['end_pts']:
            self.finish()
        self.tracks = [t for t in self.tracks if pts-t['seen'] <= (QUIET_SECONDS if t['qualified'] else 2)]
        available = []
        for obj in row['observations']:
            x,y,w,h = obj['box']
            available.append((x+w/2,y+h/2,obj.get('suggested_label')=='anomalous'))
        # Associate by position; reject large, unrelated jumps after a blink.
        for t in sorted(self.tracks,key=lambda t:not t['qualified']):
            if not available:
                break
            dt = pts-t['seen']
            px=t['x']+t['vx']*dt
            py=t['y']+t['vy']*dt
            dist,i=min((math.hypot(x-px,y-py),i) for i,(x,y,_) in enumerate(available))
            if dist>min(100,12+45*dt):
                continue
            x,y,_=available.pop(i)
            if dt>0:
                weight=min(1,dt/.3)
                t['vx']+=(max(-250,min(250,(x-t['x'])/dt))-t['vx'])*weight
                t['vy']+=(max(-250,min(250,(y-t['y'])/dt))-t['vy'])*weight
            t.update(x=x,y=y,seen=pts)
            if math.hypot(x-t['anchor_x'],y-t['anchor_y']) < (3 if t['qualified'] else MIN_TRAVEL):
                continue
            if pts-t['first'] < MIN_DURATION:
                continue
            t.update(qualified=True,anchor_x=x,anchor_y=y)
            if self.event is None:
                first=t['first']
                epoch=row['received_epoch']-(pts-first)
                suffix=hashlib.sha256(f"sustained:{generation}:{t['sequence']}".encode()).hexdigest()[:6]
                sid=datetime.fromtimestamp(epoch,timezone.utc).strftime('%Y%m%dT%H%M%SZ')+'-'+suffix
                self.event=dict(kind='sustained_motion',generation=generation,session_id=sid,
                                created=epoch,frame_epoch=epoch,onset_pts=first,start_pts=max(0,first-PRE_ROLL),
                                model_id=model,first_sequence=t['sequence'],state='open')
            self.event.update(last_seen_pts=pts,end_pts=pts+QUIET_SECONDS)
        for x,y,anomalous in available:
            if anomalous and len(self.tracks)<64:
                self.tracks.append(dict(first=pts,seen=pts,sequence=row['sequence'],x=x,y=y,
                                        anchor_x=x,anchor_y=y,vx=0.,vy=0.,qualified=False))
        if self.event and (self.saved is None or self.event['last_seen_pts']-self.saved>=1):
            self.checkpoint()
        if self.event and pts>=self.event['end_pts']:
            self.finish()

def index_session(data,event):
    with closing(sqlite3.connect(Path(data)/'sustained-sessions.sqlite3',timeout=10)) as db,db:
        db.execute('CREATE TABLE IF NOT EXISTS sessions(id TEXT PRIMARY KEY,generation TEXT,start REAL,end REAL)')
        db.execute('CREATE INDEX IF NOT EXISTS by_generation ON sessions(generation,start)')
        db.execute('INSERT OR REPLACE INTO sessions VALUES(?,?,?,?)',(event['session_id'],event['generation'],event['start_pts'],event['end_pts']))

def playback_url(data,station,event):
    path=Path(data)/'sustained-sessions.sqlite3'
    if not path.is_file() or event.get('pts_seconds') is None:
        return None
    with closing(sqlite3.connect(path.resolve().as_uri()+'?mode=ro',uri=True)) as db:
        records=db.execute('SELECT id FROM sessions WHERE generation=? AND start<=? AND end>=? ORDER BY start DESC',(event.get('generation'),event['pts_seconds'],event['pts_seconds'])).fetchall()
    for sid, in records:
        if (Path(station)/'sessions'/sid/'video.mp4').is_file():
            return '/api/live/artifact?session='+sid+'&name=video.mp4'
