import fcntl,os,subprocess,sys,tempfile,time,unittest
from pathlib import Path
from backlog_control import stop_orphaned_service
from backlog_reset import capture_health

class EmptyCaptureTests(unittest.TestCase):
 def test_closed_radio_only_generation_has_no_video_frames(self):
  with tempfile.TemporaryDirectory() as directory:
   root=Path(directory)
   for name in ('generation.json','closed.json','rf-000001.jsonl'):(root/name).write_text('{}')
   self.assertEqual(capture_health(root)['captured_frames'],0)
 def test_missing_health_with_video_evidence_still_fails(self):
  with tempfile.TemporaryDirectory() as directory:
   root=Path(directory)
   for name in ('generation.json','closed.json','segments-index.jsonl'):(root/name).write_text('{}')
   with self.assertRaises(FileNotFoundError):capture_health(root)

class OrphanShutdownTests(unittest.TestCase):
 def test_unresponsive_orphan_releases_existing_lock(self):
  with tempfile.TemporaryDirectory() as d:
   p=Path(d)/'worker.py';lock=Path(d)/'service.lock';ready=Path(d)/'ready'
   p.write_text('import fcntl,signal,time\nfrom pathlib import Path\nf=open('+repr(str(lock))+',"w");fcntl.flock(f,fcntl.LOCK_EX)\nsignal.signal(signal.SIGTERM,signal.SIG_IGN)\nPath('+repr(str(ready))+').touch()\ntime.sleep(60)\n')
   child=subprocess.Popen([sys.executable,str(p)],start_new_session=True)
   try:
    for _ in range(100):
     if ready.exists():break
     time.sleep(.03)
    assert ready.exists()
    start=time.monotonic();stop_orphaned_service(p,grace=.2);child.wait(timeout=2)
    with lock.open('a') as f:fcntl.flock(f,fcntl.LOCK_EX|fcntl.LOCK_NB)
    assert lock.exists()
    print('PASS: unresponsive orphan stopped and lock released in',round(time.monotonic()-start,2),'seconds; lock file preserved')
   finally:
    if child.poll() is None:child.kill();child.wait()

if __name__=="__main__":unittest.main()

class RequestPublicationTests(unittest.TestCase):
 def test_new_request_is_visible_before_child_starts(self):
  import backlog_control as control
  from unittest.mock import patch,Mock
  with tempfile.TemporaryDirectory() as directory,patch.object(control,'RUN',Path(directory)),patch.object(control,'APP',Path(directory)),patch.object(Path,'is_mount',return_value=True):
   (Path(directory)/'uap-lab').mkdir();(Path(directory)/'.field-station-volume').write_text('test')
   control.save(Path(directory)/'environment.json',dict(CAPTURE_VOLUME=directory,CAPTURE_VOLUME_ID='test'))
   control.save(control.RUN/'latest.json',dict(phase='complete',request_id='old',review={'frames_cleared':0}))
   def spawn(*args,**kwargs):
    state=control.status()
    self.assertTrue((Path(directory)/'uap-lab/review-queue-cleared.json').exists())
    self.assertEqual(state['phase'],'queued');self.assertTrue(state['busy']);self.assertNotEqual(state['request_id'],'old')
    return Mock(pid=123)
   with patch.object(control.subprocess,'Popen',side_effect=spawn):result=control.start()
   self.assertEqual(result['pid'],123);self.assertEqual(control.status()['request_id'],result['request_id'])
 def test_spawn_failure_is_not_left_busy(self):
  import backlog_control as control
  from unittest.mock import patch
  with tempfile.TemporaryDirectory() as directory,patch.object(control,'RUN',Path(directory)),patch.object(control,'APP',Path(directory)),patch.object(Path,'is_mount',return_value=True):
   (Path(directory)/'uap-lab').mkdir();(Path(directory)/'.field-station-volume').write_text('test')
   control.save(Path(directory)/'environment.json',dict(CAPTURE_VOLUME=directory,CAPTURE_VOLUME_ID='test'))
   with patch.object(control.subprocess,'Popen',side_effect=OSError('spawn failed')):
    with self.assertRaises(OSError):control.start()
   self.assertEqual(control.status()['phase'],'error');self.assertFalse(control.status()['busy'])
 def test_abandoned_queued_request_reports_failure(self):
  import backlog_control as control
  from unittest.mock import patch
  with tempfile.TemporaryDirectory() as directory,patch.object(control,'RUN',Path(directory)),patch.object(control,'APP',Path(directory)),patch.object(Path,'is_mount',return_value=True):
   (Path(directory)/'uap-lab').mkdir();(Path(directory)/'.field-station-volume').write_text('test')
   control.save(Path(directory)/'environment.json',dict(CAPTURE_VOLUME=directory,CAPTURE_VOLUME_ID='test'))
   control.save(control.RUN/'latest.json',dict(phase='queued',request_id='new',busy=True,queued_epoch=time.time()-60))
   self.assertEqual(control.status()['phase'],'error')

class DeploymentLeaseTest(unittest.TestCase):
 def test_media_cleanup_allows_model_switch_and_retains_retention_lease(self):
  import contextlib,fcntl,json,sys,types
  from unittest.mock import patch
  import backlog_control as control

  with tempfile.TemporaryDirectory() as temporary, contextlib.ExitStack() as patches:
   app=Path(temporary);volume=app/'volume';volume.mkdir()
   (volume/'.field-station-volume').write_text('test-volume')
   for name in ('auto-training','maintenance/retention','retention-audit','volume/uap-lab/recognition'):
    (app/name).mkdir(parents=True,exist_ok=True)
   (app/'environment.json').write_text(json.dumps({'CAPTURE_VOLUME':str(volume),'CAPTURE_VOLUME_ID':'test-volume'}))
   (app/'maintenance/retention/config.json').write_text(json.dumps({'audit':str(app/'retention-audit')}))
   deployment=app/'auto-training/deployment.lock';retention=app/'retention-audit/worker.lock'
   @contextlib.contextmanager
   def lease(path):
    with path.open('a') as file:
     fcntl.flock(file,fcntl.LOCK_EX|fcntl.LOCK_NB);yield
   def reset(*args):
    with self.assertRaises(BlockingIOError),lease(deployment):pass
    return {}
   def clear(*args,**kwargs):
    with lease(deployment):pass
    with self.assertRaises(BlockingIOError),lease(retention):pass
    return {'completed':True}
   patches.enter_context(patch.object(control,'APP',app))
   patches.enter_context(patch.object(control,'RUN',app/'audit'))
   (app/'audit'/'case').mkdir(parents=True)
   patches.enter_context(patch.object(Path,'is_mount',return_value=True))
   patches.enter_context(patch.object(control,'stop_orphaned_service'))
   patches.enter_context(patch.object(control.subprocess,'run',return_value=types.SimpleNamespace(returncode=1)))
   patches.enter_context(patch.dict(sys.modules,{'provisional_station':types.SimpleNamespace(lease=lease),
       'backlog_reset':types.SimpleNamespace(reset=reset),'label_queue':types.SimpleNamespace(clear_backlog=clear)}))
   paths=sys.path[:];self.addCleanup(lambda:sys.path.__setitem__(slice(None),paths))
   control.work('case')
   receipt=json.loads((app/'audit/latest.json').read_text())
   self.assertEqual(receipt['phase'],'complete',receipt)
   self.assertEqual(receipt['review'],{'completed':True})
