"""Private station preferences, persisted on the capture volume."""
import fcntl,time
from pathlib import Path
from retired_data import read,save
SWITCHES={'daytime_detection':False,'nighttime_detection':True,'live_streaming':True}
DELAYS=(10800,21600,43200,86400)
NEGATIVE_LIMITS=(250,500,1000,2500,5000)

def settings(root):
 value=read(Path(root)/'station-settings.json',{})
 delay=value.get('after_seconds',10800)
 if type(delay) is not int or delay not in DELAYS:delay=10800
 from station_location import location_at
 from negative_backlog import policy as negative_policy
 negative=negative_policy(Path(root)/'uap-lab')
 return dict(**{key:value.get(key,default) is True for key,default in SWITCHES.items()},observation_location=location_at(root),negative_backlog_enabled=negative['enabled'],negative_backlog_limit=negative['max_items'],daytime_auto_cleanup=value.get('daytime_auto_cleanup') is True,after_seconds=delay,timezone='America/Los_Angeles',daytime_only=True)

def policy(root):
 value=settings(root)
 return dict(enabled=value['daytime_auto_cleanup'],after_seconds=value['after_seconds'])

def update(root,value):
 if not isinstance(value,dict) or not value or set(value)-({'daytime_auto_cleanup','after_seconds','negative_backlog_enabled','negative_backlog_limit'}|set(SWITCHES)):raise ValueError('Invalid cleanup settings.')
 if 'negative_backlog_limit' in value and (type(value['negative_backlog_limit']) is not int or value['negative_backlog_limit'] not in NEGATIVE_LIMITS):raise ValueError('Choose 250, 500, 1,000, 2,500, or 5,000 frames.')
 if 'negative_backlog_enabled' in value and type(value['negative_backlog_enabled']) is not bool:raise ValueError('Choose whether the non-anomalous review limit is enabled.')
 if 'daytime_auto_cleanup' in value and type(value['daytime_auto_cleanup']) is not bool:raise ValueError('Choose whether daytime auto-cleanup is enabled.')
 if 'after_seconds' in value and (type(value['after_seconds']) is not int or value['after_seconds'] not in DELAYS):raise ValueError('Choose 3, 6, 12, or 24 hours.')
 for key in SWITCHES:
  if key in value and type(value[key]) is not bool:raise ValueError('Detection and streaming switches must be true or false.')
 root=Path(root)
 with (root/'station-settings.lock').open('a') as lock:
  fcntl.flock(lock,fcntl.LOCK_EX)
  current=read(root/'station-settings.json',{})
  if 'negative_backlog_enabled' in value or 'negative_backlog_limit' in value:
   from negative_backlog import policy as negative_policy
   data=root/'uap-lab';negative=negative_policy(data)
   save(data/'negative-backlog-policy.json',dict(negative,enabled=value.get('negative_backlog_enabled',negative['enabled']),max_items=value.get('negative_backlog_limit',negative['max_items'])))
  save(root/'station-settings.json',dict(current,**{k:v for k,v in value.items() if k not in ('negative_backlog_enabled','negative_backlog_limit')},updated_epoch=time.time()))
 return settings(root)
