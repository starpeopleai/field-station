"""Field-side activation of an explicitly selected, runtime-probed model."""
import fcntl,hashlib,json,math,subprocess,sys,time
from pathlib import Path
sys.path[:0]=[str(Path(__file__).resolve().parents[1]),str(Path(__file__).resolve().parents[1]/'recognition')]
import deploy
from model_activation import update,status
from model_settings import read,save,effective,snapshot
from crop_client import CropClassifier

def activate(data,folder,identity):
 data=Path(data);folder=Path(folder)
 with (deploy.APP/'auto-training/deployment.lock').open('a') as lock:
  try:fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
  except BlockingIOError:
   return update(data,identity,phase='queued',error='Waiting for station maintenance to release the model.')
  job=read(data/'model-inspector/activation.json',{})
  if job.get('id')!=identity or job.get('phase') not in ('queued','preparing','activating','monitoring'):raise ValueError('No pending authorization for this switch')
  policy=read(folder/'candidate-policy.json',{})
  if policy.get('version')!=job['version']:raise ValueError('Transferred model version mismatch')
  current_policy=effective(policy,job['lane'],snapshot(data))
  if current_policy.get('settings_revision',0)!=job['revision']:raise ValueError('Decision settings changed during transfer; select the model again')
  cfg=read(deploy.CONFIG);current=read(cfg['policy'])['version']
  if cfg.get('selection_request_id')==identity:return status(data)
  compiled=folder/'candidate.mlmodelc'
  if not compiled.exists():subprocess.run([str(deploy.APP/'uap-lab/recognition/bin/compile_model'),str(folder/'candidate.mlpackage'),str(compiled)],check=True,capture_output=True,timeout=300)
  images=[(folder/name).read_bytes() for name in ('probe.png',)]
  with CropClassifier(cfg['worker'],compiled,policy['version'],timeout=60) as worker:results=worker.predict(images)
  if len(results)!=1 or results[0].get('error'):raise ValueError('Selected model failed its field runtime probe')
  scores=results[0].get('scores',{})
  if not all(isinstance(scores.get(k),(int,float)) and math.isfinite(scores[k]) and 0<=scores[k]<=1 for k in ('anomalous','not_anomalous')):raise ValueError('Invalid binary runtime output')
  report=folder/'selection-authorization.json'
  save(report,dict(passed=False,baseline_version=current,candidate_version=policy['version'],manual_deployment=dict(request_id=identity,runtime_validated=True),reason='Explicit Make live selection; benchmark rank is not a promotion gate'))
  save(folder/'previous-recognition-config.json',cfg)
  cfg.update(model=str(compiled),policy=str(folder/'candidate-policy.json'),decision_lane=job['lane'],selection_request_id=identity,model_transition=dict(from_version=current,to_version=policy['version'],evaluation_path=str(report),evaluation_sha256=hashlib.sha256(report.read_bytes()).hexdigest()))
  save(deploy.CONFIG,cfg);update(data,identity,phase='monitoring',activated_epoch=time.time(),error=None);deploy.restart_recognition()
  return status(data)
if __name__=='__main__':print(json.dumps(activate(Path(sys.argv[1]),Path(sys.argv[2]),sys.argv[3])))
