'use strict';
(()=>{
 const titles={'/models':'Model tuning','/test-model':'Test model','/metrics':'Metrics','/label-videos':'Review detections','/tracks':'Labeled objects','/labels':'Labeled objects','/events':'Recent events','/training':'Training history','/email-review':'Review detection'};
 const root=location.pathname==='/';const old=document.querySelector('header.app-controls');
 const header=document.createElement('header');header.className='app-controls station-header';header.setAttribute('aria-label','Field Station');
 const button=document.getElementById('menuToggle')||document.createElement('button');button.id='menuToggle';button.className='station-menu-button';button.type='button';button.setAttribute('aria-label','Open navigation');button.setAttribute('aria-expanded','false');button.setAttribute('aria-controls','mainNav');button.innerHTML='<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M4 6h16M4 12h16M4 18h16"/></svg>';
 const brand=document.createElement('a');brand.className='station-brand';brand.href='/';brand.textContent='Field Station';
 let favicon=document.querySelector('link[rel=icon]');if(!favicon){favicon=document.createElement('link');favicon.rel='icon';document.head.append(favicon);}favicon.href='/favicon.png?v=exception-1';
 const modelHash=document.createElement('small');modelHash.className='station-model-hash';modelHash.textContent='Checking model…';brand.append(modelHash);let confirmedModelHash='';
 function showModelStatus(hash,state){if(hash)confirmedModelHash=hash;modelHash.textContent=(confirmedModelHash?confirmedModelHash.slice(0,12):'Model')+(state==='live'?'':state==='error'?' · runtime error':' · status delayed');modelHash.title=state==='live'?confirmedModelHash:(confirmedModelHash?'Last confirmed model: '+confirmedModelHash+'. ':'')+(state==='error'?'Recognition reported an error.':'Waiting for a fresh runtime status.');}
 async function refreshModelHash(){if(document.hidden)return;try{const r=await fetch('/api/live/status',{cache:'no-store',signal:AbortSignal.timeout(8000)});if(!r.ok)throw Error();const data=await r.json();showModelStatus(data.active_model_hash||data.last_confirmed_model_hash,data.model_runtime_error?'error':data.active_model_hash?'live':'delayed');}catch{showModelStatus(null,'delayed');}}
 refreshModelHash();setInterval(refreshModelHash,10000);
 const title=document.createElement('span');title.className='station-page-title';title.textContent=titles[location.pathname]||({label:'Review detections',test:'Test model'}[new URLSearchParams(location.search).get('view')]||'Camera feed');
 const nav=document.getElementById('mainNav')||document.createElement('nav');nav.id='mainNav';nav.setAttribute('aria-label','Main navigation');nav.hidden=true;
 if(!root){for(const [name,url]of [['Camera feed','/'],['Review detections','/label-videos'],['Model tuning','/models'],['Metrics','/metrics']]){const a=document.createElement('a');a.href=url;a.textContent=name;if(url===location.pathname||(url==='/tracks'&&location.pathname==='/labels'))a.setAttribute('aria-current','page');nav.append(a);}}
 if(root){const modelButton=document.getElementById('testTab');if(modelButton){modelButton.textContent='Model tuning';modelButton.onclick=()=>{location.href='/models'};}for(const oldLink of nav.querySelectorAll('a[href="/metrics"],a[href="/training"]'))oldLink.remove();}
 if(root){for(const name of ['Camera feed','Review detections','Model tuning']){const el=[...nav.children].find(e=>e.textContent===name);if(el)nav.append(el);}}
 if(root){const metrics=document.createElement('a');metrics.href='/metrics';metrics.textContent='Metrics';nav.append(metrics);}
 header.append(button,brand,title,nav);
 for(const id of ['infoToggle','infoPanel']){const el=document.getElementById(id);if(el)header.append(el);}
 if(old)old.remove();document.body.prepend(header);document.body.classList.add('has-station-header');
 function close(focus=false){nav.hidden=true;button.setAttribute('aria-expanded','false');if(focus)button.focus();}
 if(!root){button.onclick=()=>{const open=nav.hidden;nav.hidden=!open;button.setAttribute('aria-expanded',String(open));if(open)nav.querySelector('a')?.focus();};document.addEventListener('keydown',e=>{if(e.key==='Escape'&&!nav.hidden)close(true);});}
 document.addEventListener('click',e=>{if(!header.contains(e.target))close();});
 nav.addEventListener('keydown',e=>{const links=[...nav.querySelectorAll('a,button')];if(!['ArrowDown','ArrowUp','Home','End'].includes(e.key))return;e.preventDefault();const i=links.indexOf(document.activeElement);links[e.key==='Home'?0:e.key==='End'?links.length-1:(i+(e.key==='ArrowUp'?-1:1)+links.length)%links.length]?.focus();});
 window.addEventListener('station-view',e=>{const mode=e.detail;title.textContent={live:'Camera feed',label:'Review detections',test:'Test model'}[mode]||'Camera feed';for(const [id,value]of [['liveTab','live'],['labelTab','label'],['testTab','test']]){const el=document.getElementById(id);if(mode===value)el.setAttribute('aria-current','page');else el.removeAttribute('aria-current');}const url=new URL(location.href);if(mode==='live')url.searchParams.delete('view');else url.searchParams.set('view',mode);history.replaceState(null,'',url);});
 if(location.pathname==='/training'&&!document.querySelector('main.training-history')){
  const main=document.createElement('main');main.className='station-training-page';for(const el of [...document.body.childNodes])if(el!==header&&!(el.nodeType===1&&['SCRIPT','STYLE','LINK'].includes(el.tagName)))main.append(el);document.body.append(main);
 }
})();
// One notification region for connection, review, and training messages.
(()=>{
 const region=document.createElement('div');region.id='stationNotifications';region.setAttribute('aria-label','Notifications');document.body.append(region);
 function mount(node){node.classList.add('station-notification');region.append(node);return node;}
 function set(key,text,error=false){let node=document.getElementById(key);if(!node){node=document.createElement('div');node.id=key;node.setAttribute('role','status');mount(node);}node.textContent=text;node.classList.toggle('error',error);node.hidden=!text;return node;}
 function clear(key){const node=document.getElementById(key);if(node)node.hidden=true;}
 window.stationNotifications={mount,set,clear};
 for(const id of ['notice','queueToast']){const node=document.getElementById(id);if(node)mount(node);}
 const prior=document.getElementById('notice');if(prior?.textContent.startsWith('Connection')){set('stationConnectionNotice','Connection is slow. Waiting for the station…',true);prior.textContent='';}
})();
// Preserve the review document, playback and drafts during service recovery.
(()=>{
 let instance=null,interrupted=false,failures=0;
 function warning(message){window.stationNotifications.set('stationConnectionNotice',message,true);}
 async function poll(){
  try{
   const response=await fetch('/api/service-status',{cache:'no-store',priority:'high',signal:AbortSignal.timeout(window.FIELD_PUBLIC_READ_ONLY===true?45000:8000)});
   if(!response.ok)throw Error('Unavailable');const state=await response.json();
   if(!state.available){
    interrupted=true;
    if(++failures>=2||state.phase==='cleanup')warning(state.phase==='cleanup'?'Backlog cleanup is in progress. Waiting for the station…':'Reconnecting to the station…');
   }else{
    if(interrupted||(instance&&instance!==state.instance)){
     // Retry authorization without replacing the page or losing unsaved work.
     const r=await fetch('/api/labeled-frames/token',{cache:'no-store',priority:'high',signal:AbortSignal.timeout(window.FIELD_PUBLIC_READ_ONLY===true?45000:8000)});if(!r.ok)throw Error('Not ready');const auth=await r.json();
     window.dispatchEvent(new CustomEvent('station-reconnected',{detail:{token:auth.token}}));
     interrupted=false;
    }
    instance=state.instance;failures=0;window.stationNotifications.clear('stationConnectionNotice');
   }
  }catch{interrupted=true;if(++failures>=2)warning('Reconnecting to the station…');}
  setTimeout(poll,2500);
 }
 poll();
})();

// Manual requests share the scheduled trainer and its model validation gates.
(()=>{
 if(!['/label-videos','/models','/metrics'].includes(location.pathname)||window.FIELD_PUBLIC_READ_ONLY===true)return;
 const button=document.createElement('button');button.type='button';button.id='trainNow';button.className='station-train-button';button.textContent='Train now';button.disabled=true;
 document.querySelector('.station-header').append(button);
 const notice=document.createElement('div');notice.className='station-training-notice';notice.setAttribute('role','status');notice.hidden=true;window.stationNotifications.mount(notice);
 let submitting=false,watching=false;
 const labels={cascade_training:'Training cycle…',cascade_evaluating:'Comparing…',queued:'Queued…',starting:'Starting…',snapshot:'Preparing…',building:'Preparing…',training:'Training…',refining_class_corrections:'Refining…',evaluating:'Validating…',activation_pending:'Retrying deployment…',activating:'Deploying…'};
 const messages={waiting_for_data:'Training could not start because independent training or validation data is missing.',not_promoted:'Training finished. The earlier model was kept because this run did not meet its release checks. Your labels are saved.',validated_no_improvement:'Training finished without a validated improvement. Your labels are saved and the current model remains active.',refining_class_corrections:'Checking class corrections.',queued:'Training queued. The trainer checks for requests every minute.',starting:'Training is starting.',snapshot:'Collecting human-reviewed labels.',building:'Preparing the training dataset.',training:'Training a model with your labels.',evaluating:'Checking the new model before release.',activation_pending:'Model trained. Activation needs attention and will retry automatically.',activating:'Deploying the validated model.',deployed:'The new model is live.',validated_unchanged:'Training validated. The active model already uses these labels.',rejected:'The new model did not pass validation. The current model remains active.',superseded:'Labels changed during training. A fresh run is needed.',error:'Training could not finish. See Model tuning for details.',rolled_back:'The new model was rolled back. The previous model remains active.'};
 function render(state){button.disabled=submitting||state.busy;button.textContent=state.busy?(labels[state.phase]||'Training…'):'Train now';if(watching||(state.busy&&state.phase.startsWith("cascade"))){notice.hidden=false;notice.textContent=(['building','cascade_training','cascade_evaluating','cascade_complete','cascade_partial'].includes(state.phase)&&state.reason?state.reason:messages[state.phase])||(state.busy?'Training is running.':'Training finished. See Model tuning for details.');}}
 async function poll(){try{const r=await fetch('/api/training-control',{cache:'no-store'});if(!r.ok)throw Error();render(await r.json());}catch{button.disabled=true;button.textContent='Train now';button.title='Waiting for the training service';}}
 button.onclick=async()=>{if(button.disabled)return;submitting=true;button.disabled=true;button.textContent='Queuing…';watching=true;try{const auth=await fetch('/api/labeled-frames/token',{cache:'no-store'});if(!auth.ok)throw Error();const {token}=await auth.json();const r=await fetch('/api/training-control/start',{method:'POST',headers:{'Content-Type':'application/json','X-Lab-Token':token},body:JSON.stringify({ranking_measure:(()=>{try{return localStorage.getItem('model-ranking-measure')||'false_positive_rate'}catch{return 'false_positive_rate'}})()})});if(!r.ok)throw Error();submitting=false;render(await r.json());}catch{submitting=false;notice.hidden=false;notice.textContent='Could not confirm the training request. Checking its status…';await poll();}};
 window.addEventListener('station-reconnected',poll);poll();setInterval(poll,5000);
})();

// Shared operator actions on review, model tuning and metrics pages.
(()=>{
 if(!['/label-videos','/models','/metrics'].includes(location.pathname)||window.FIELD_PUBLIC_READ_ONLY===true)return;
 const button=document.createElement('button');button.id='clearBacklog';button.type='button';button.className='station-train-button';button.textContent='Clear backlog';button.title='Skip queued analysis to live and delete unreviewed detections and their media. Human-reviewed evidence is preserved.';
 document.querySelector('.station-header').append(button);
 const style=document.createElement('style');style.textContent='.station-header #clearBacklog{margin-left:0;white-space:nowrap}.station-header:has(#clearBacklog) #trainNow{margin-left:auto}@media(max-width:600px){.station-header:has(#clearBacklog) .station-page-title{display:none}.station-header:has(#trainNow):has(#clearBacklog) .station-brand{display:none}}';document.head.append(style);
 let watching=false,submitting=false,lastCompleted=null,expectedRequest=null,requestGeneration=0;
 function render(state){if(submitting||(watching&&expectedRequest&&state.request_id!==expectedRequest)||(watching&&!expectedRequest&&state.request_id===lastCompleted&&!state.busy))return;if(state.phase==='complete'&&state.request_id!==lastCompleted){lastCompleted=state.request_id;window.dispatchEvent(new CustomEvent('station-backlog-cleared'));}button.disabled=submitting||!!state.busy;button.textContent=state.busy?'Clearing…':'Clear backlog';if(!watching)return;
  let message='Clearing backlog…';
  if(state.phase==='complete'){const review=state.review||{};message=`Cleared ${(review.frames_cleared||0).toLocaleString()} unreviewed detections and ${(review.videos_cleared||0).toLocaleString()} videos. Deleted ${(review.media_files_deleted||0).toLocaleString()} media files (${((review.media_bytes_deleted||0)/1024**3).toFixed(2)} GiB). Human-reviewed evidence kept.${review.media_deferred?' Some active items are awaiting media cleanup.':''}`;if(state.analysis?.skipped==='generation_transition')message+=' Capture changed during cleanup; analysis will follow the new capture.';window.dispatchEvent(new CustomEvent('station-backlog-cleared'));watching=false;}
  if(state.phase==='error'){message='Backlog cleanup could not finish: '+state.error;watching=false;}
  window.stationNotifications.set('backlogNotice',message,state.phase==='error');
 }
 async function poll(){const generation=requestGeneration;try{const r=await fetch('/api/backlog',{cache:'no-store',signal:AbortSignal.timeout(8000)});if(r.ok){const state=await r.json();if(generation===requestGeneration&&!submitting)render(state);}}catch{}}
 button.onclick=async()=>{if(button.disabled)return;requestGeneration++;expectedRequest=null;submitting=true;watching=true;button.disabled=true;button.textContent='Clearing…';window.stationNotifications.set('backlogNotice','Clearing backlog…');try{const a=await fetch('/api/labeled-frames/token',{cache:'no-store'});if(!a.ok)throw Error('Station unavailable');const {token}=await a.json();const r=await fetch('/api/backlog/clear',{method:'POST',headers:{'X-Lab-Token':token,'Content-Type':'application/json'},body:'{}'});if(!r.ok)throw Error('Request failed');const state=await r.json();expectedRequest=state.request_id;submitting=false;render(state);window.dispatchEvent(new Event('review-filter-change'));}catch{ submitting=false;window.stationNotifications.set('backlogNotice','Checking whether the backlog cleanup started…');await poll();}};
 window.addEventListener('station-reconnected',poll);poll();setInterval(poll,3000);
})();

// Capture controls stay private across the operator workspaces.
(()=>{
 if(!['/label-videos','/models','/metrics'].includes(location.pathname)||window.FIELD_PUBLIC_READ_ONLY===true)return;
 const header=document.querySelector('.station-header');if(!header)return;
 const button=document.createElement('button');button.id='pauseCapture';button.type='button';button.className='station-train-button';button.style.marginLeft='0';button.style.whiteSpace='nowrap';button.textContent='Pause capture';button.disabled=true;
 header.insertBefore(button,document.getElementById('clearBacklog'));
 let paused=false,busy=false;
 function render(value,pending=false){paused=value;button.textContent=pending?(paused?'Pausing…':'Resuming…'):(paused?'Resume capture':'Pause capture');button.setAttribute('aria-pressed',String(paused));button.disabled=busy||pending;}
 async function poll(){if(busy)return;try{const r=await fetch('/api/live/capture',{cache:'no-store',signal:AbortSignal.timeout(8000)});if(!r.ok)throw Error();const state=await r.json();render(state.capture_paused===true,state.pending===true);}catch{button.disabled=true;button.title='Waiting for capture status';}}
 button.onclick=async()=>{if(busy)return;busy=true;button.disabled=true;try{
  const auth=await fetch('/api/labeled-frames/token',{cache:'no-store'});if(!auth.ok)throw Error('Station unavailable');const {token}=await auth.json();
  const response=await fetch('/api/live/pause',{method:'POST',headers:{'Content-Type':'application/json','X-Lab-Token':token},body:JSON.stringify({paused:!paused}),signal:AbortSignal.timeout(65000)});const result=await response.json();if(!response.ok)throw Error(result.error||'Capture control failed');render(result.paused,result.pending);
  window.stationNotifications.set('capturePauseNotice',result.pending?'Capture change requested. Waiting for the capture worker.':(result.paused?'Capture paused. Live preview stays on.':'Capture resumed.'));
 }catch(e){window.stationNotifications.set('capturePauseNotice',e.message,true);}finally{busy=false;await poll();}};
 poll();setInterval(poll,5000);window.addEventListener('station-reconnected',poll);
})();

// A lightweight arrival hint; never fetch the object library just to show a dot.
(()=>{
 if(window.FIELD_PUBLIC_READ_ONLY===true||!['/','/models','/label-videos','/email-review'].includes(location.pathname))return;
 const button=document.getElementById('menuToggle');if(!button)return;
 const dot=document.createElement('span');dot.className='station-detection-dot';dot.hidden=true;dot.setAttribute('aria-hidden','true');button.append(dot);
 const reviewLink=document.querySelector('#mainNav a[href="/label-videos"]')||document.getElementById('labelTab');
 const reviewDot=document.createElement('span');reviewDot.className='station-review-dot';reviewDot.hidden=true;reviewDot.setAttribute('aria-hidden','true');reviewLink?.append(reviewDot);
 const key='field-station.detections-seen';let latest=null,seen=null,busy=false;
 let reviewing=['/label-videos','/email-review'].includes(location.pathname)||(location.pathname==='/'&&new URLSearchParams(location.search).get('view')==='label');
 try{seen=JSON.parse(localStorage.getItem(key));}catch{}
 function render(){const unread=!reviewing&&latest?.id&&seen&&latest.epoch>seen.epoch;dot.hidden=!unread;reviewDot.hidden=!unread;reviewLink?.setAttribute('aria-label',unread?'Review detections — new detections':'Review detections');button.setAttribute('aria-label',unread?'Open navigation — new detections':'Open navigation');}
 function acknowledge(){if(latest){seen=latest;try{localStorage.setItem(key,JSON.stringify(seen));}catch{}}render();}
 async function poll(){if(busy||document.hidden)return;busy=true;try{
  const r=await fetch('/api/detections/latest',{cache:'no-store',signal:AbortSignal.timeout(5000)});if(!r.ok)return;
  const value=await r.json();latest=typeof value.id==='string'&&Number.isFinite(value.epoch)?value:{id:null,epoch:0};
  if(!seen||reviewing)acknowledge();else render();
 }catch{}finally{busy=false;}}
 window.addEventListener('station-view',e=>{reviewing=e.detail==='label';if(reviewing)acknowledge();else render();void poll();});
 window.addEventListener('storage',e=>{if(e.key===key){try{seen=JSON.parse(e.newValue);}catch{}render();}});
 document.addEventListener('visibilitychange',()=>{if(!document.hidden)void poll();});
 window.addEventListener('station-reconnected',poll);void poll();setInterval(poll,5000);
})();

// Small live preview on the review and model workspaces; one request at a time.
(()=>{
 if(!['/label-videos','/models'].includes(location.pathname))return;
 const pip=document.createElement('a');pip.id='stationLivePip';pip.href='/';pip.setAttribute('aria-label','Open Camera feed');
 const image=document.createElement('img');image.alt='Live camera preview';image.hidden=true;
 const status=document.createElement('span');status.className='pip-status';status.setAttribute('role','status');status.textContent='Connecting…';
 const badge=document.createElement('span');badge.className='pip-badge';badge.textContent='Connecting';badge.setAttribute('role','status');pip.append(image,status,badge);document.body.append(pip);
 let busy=false,timer=null,controller=null,currentUrl=null,stopped=false,frameAt=0,session=null,sessionAt=0,signal=null,signalAt=0,stateBusy=false,stateTimer=null;
 function renderBadge(){let text='Connecting',state='connecting';if(signal?.camera_no_signal===true&&Date.now()-signalAt<7000){text='No signal';state='no-signal';}else if(frameAt&&Date.now()-frameAt<5000){if(session?.active?.state==='recording'&&Date.now()-sessionAt<7000&&!session.capture_paused&&!session.recording_paused){text='Recording';state='recording';}else{text='Live';state='live';}}badge.textContent=text;badge.dataset.state=state;}
 async function pollState(){if(stopped||stateBusy||document.hidden)return;stateBusy=true;try{await Promise.allSettled([['/api/live/session',v=>{session=v;sessionAt=Date.now();}],['/api/live/status',v=>{signal=v;signalAt=Date.now();}]].map(async([path,save])=>{const r=await fetch(path,{cache:'no-store',signal:AbortSignal.timeout(5000)});if(r.ok)save(await r.json());}));}finally{stateBusy=false;renderBadge();if(!stopped&&!document.hidden)stateTimer=setTimeout(pollState,3000);}}
 async function frame(){
  if(stopped||busy||document.hidden)return;busy=true;let failed=false,nextUrl=null;
  controller=new AbortController();const timeout=setTimeout(()=>controller?.abort(),8000);
  try{
   const response=await fetch('/api/live/frame?t='+Date.now(),{cache:'no-store',signal:controller.signal});
   if(!response.ok)throw Error('Camera unavailable');
   nextUrl=URL.createObjectURL(await response.blob());const decoded=new Image();decoded.src=nextUrl;await decoded.decode();
   if(stopped||document.hidden)return;
   const previous=currentUrl;currentUrl=nextUrl;nextUrl=null;image.src=currentUrl;image.hidden=false;status.hidden=true;frameAt=Date.now();renderBadge();if(previous)URL.revokeObjectURL(previous);
  }catch{if(!stopped&&!document.hidden){failed=true;frameAt=0;renderBadge();image.hidden=true;status.textContent='Camera unavailable';status.hidden=false;}}
  finally{clearTimeout(timeout);if(nextUrl)URL.revokeObjectURL(nextUrl);busy=false;controller=null;if(!stopped&&!document.hidden)timer=setTimeout(frame,failed?2000:500);}
 }
 document.addEventListener('visibilitychange',()=>{clearTimeout(timer);clearTimeout(stateTimer);if(document.hidden)controller?.abort();else{void frame();void pollState();}});
 window.addEventListener('pagehide',()=>{stopped=true;clearTimeout(timer);clearTimeout(stateTimer);controller?.abort();if(currentUrl)URL.revokeObjectURL(currentUrl);});
 window.addEventListener('pageshow',()=>{if(stopped){stopped=false;void frame();void pollState();}});
 void frame();void pollState();
})();

// Private station hardware status. Public pages neither render nor request it.
(()=>{
 if(window.FIELD_PUBLIC_READ_ONLY===true)return;
 const header=document.querySelector('.station-header');if(!header)return;
 const temperature=document.createElement('span');temperature.id='systemTemperature';temperature.textContent='CPU —';temperature.title='Field Mac CPU temperature';
 temperature.style.cssText='white-space:nowrap;font-size:11px;font-weight:400;font-variant-numeric:tabular-nums';header.insertBefore(temperature,document.getElementById('infoToggle'));
 async function poll(){
  let delay=15000;
  if(!document.hidden){try{
   const response=await fetch('/api/system-temperature',{cache:'no-store',signal:AbortSignal.timeout(5000)});if(!response.ok)throw Error();const value=await response.json();
   temperature.textContent=value.available&&Number.isFinite(value.celsius)?'CPU '+Math.round(value.celsius*9/5+32)+'°F':'CPU —';temperature.title=value.available?'Field Mac CPU temperature':'Field Mac CPU temperature unavailable';
   if(value.sampling&&!value.available)delay=2000;
  }catch{temperature.textContent='CPU —';temperature.title='Field Mac CPU temperature unavailable';}}
  setTimeout(poll,delay);
 }
 poll();
})();

// Private station settings persist on the external capture volume.
(()=>{
 if(window.FIELD_PUBLIC_READ_ONLY===true)return;
 const nav=document.getElementById('mainNav');if(!nav)return;
 const open=document.createElement('button');open.type='button';open.id='stationSettingsOpen';open.textContent='Settings';nav.append(open);
 const dialog=document.createElement('dialog');dialog.id='stationSettings';dialog.setAttribute('aria-labelledby','stationSettingsTitle');
 dialog.innerHTML='<form method="dialog" class="settings-heading"><h2 id="stationSettingsTitle">Settings</h2><button aria-label="Close settings" value="close">×</button></form><label class="settings-option" for="daytimeDetection"><span>Daytime detection</span><input id="daytimeDetection" type="checkbox" role="switch" disabled></label><label class="settings-option" for="nighttimeDetection"><span>Nighttime detection</span><input id="nighttimeDetection" type="checkbox" role="switch" disabled></label><label class="settings-option" for="negativeBacklogLimit"><span>Limit non-anomalous frames</span><input id="negativeBacklogLimit" type="checkbox" role="switch" aria-describedby="negativeBacklogHelp" disabled></label><label id="negativeBacklogCountRow" class="settings-option settings-delay" for="negativeBacklogCount" hidden><span>Frame limit</span><select id="negativeBacklogCount" disabled><option value="250">250</option><option value="500">500</option><option value="1000" selected>1,000</option><option value="2500">2,500</option><option value="5000">5,000</option></select></label><p id="negativeBacklogHelp">Automatically remove excess machine-only, non-anomalous detections, day or night. Human-reviewed frames, starred evidence, and manual recordings are kept. New and actively reviewed frames may temporarily exceed the limit.</p><label class="settings-option" for="daytimeAutoCleanup"><span>Daytime auto-cleanup</span><input id="daytimeAutoCleanup" type="checkbox" role="switch" disabled></label><label class="settings-option settings-delay" for="daytimeCleanupDelay"><span>Delete after</span><select id="daytimeCleanupDelay" disabled><option value="10800">3 hours</option><option value="21600">6 hours</option><option value="43200">12 hours</option><option value="86400">24 hours</option></select></label><p id="daytimeCleanupHelp">Delete machine-only, non-anomalous daytime detections after the selected time from capture. Runs during daylight; nighttime detections, human-reviewed training data, starred evidence, and manual recordings are kept.</p><p id="stationLocation">Automatic location: unknown</p><p id="stationSettingsStatus" role="status"></p>';
 document.body.append(dialog);const dayDetection=dialog.querySelector('#daytimeDetection'),nightDetection=dialog.querySelector('#nighttimeDetection');const cap=dialog.querySelector('#negativeBacklogLimit'),capCount=dialog.querySelector('#negativeBacklogCount'),toggle=dialog.querySelector('#daytimeAutoCleanup'),delay=dialog.querySelector('#daytimeCleanupDelay'),status=dialog.querySelector('[role=status]');toggle.setAttribute('aria-describedby','daytimeCleanupHelp');delay.setAttribute('aria-describedby','daytimeCleanupHelp');let confirmed={negative_backlog_enabled:false,negative_backlog_limit:1000,daytime_auto_cleanup:false,after_seconds:10800},busy=false;
 function render(state){dayDetection.checked=state.daytime_detection===true;nightDetection.checked=state.nighttime_detection===true;dayDetection.disabled=busy;nightDetection.disabled=busy;const place=state.observation_location;dialog.querySelector('#stationLocation').textContent=place?.status==='known'?'Location: '+[place.county,place.state,place.country].join(', ')+' · automatic, county only':'Automatic location: unknown';confirmed=state;cap.checked=state.negative_backlog_enabled===true;cap.disabled=busy;capCount.value=String(state.negative_backlog_limit??1000);capCount.disabled=busy||!cap.checked;dialog.querySelector('#negativeBacklogCountRow').hidden=!cap.checked;toggle.checked=state.daytime_auto_cleanup===true;delay.value=String(state.after_seconds);toggle.disabled=busy;delay.disabled=busy||!toggle.checked;}
 async function load(){dayDetection.disabled=true;nightDetection.disabled=true;cap.disabled=true;capCount.disabled=true;toggle.disabled=true;delay.disabled=true;status.textContent='Loading…';try{const r=await fetch('/api/settings',{cache:'no-store',signal:AbortSignal.timeout(10000)});if(!r.ok)throw Error();const state=await r.json();render(state);status.textContent='';}catch{status.textContent='Settings unavailable. Close and reopen to retry.';}}
 open.onclick=()=>{nav.hidden=true;document.getElementById('menuToggle').setAttribute('aria-expanded','false');dialog.showModal();void load();};
 dialog.addEventListener('close',()=>document.getElementById('menuToggle').focus());
 const saveSettings=async()=>{if(busy)return;const requested={daytime_detection:dayDetection.checked,nighttime_detection:nightDetection.checked,negative_backlog_enabled:cap.checked,negative_backlog_limit:Number(capCount.value),daytime_auto_cleanup:toggle.checked,after_seconds:Number(delay.value)};busy=true;cap.disabled=true;capCount.disabled=true;toggle.disabled=true;delay.disabled=true;dayDetection.disabled=true;nightDetection.disabled=true;status.textContent='Saving…';try{const auth=await fetch('/api/labeled-frames/token',{cache:'no-store',signal:AbortSignal.timeout(10000)});if(!auth.ok)throw Error();const {token}=await auth.json();const response=await fetch('/api/settings',{method:'POST',headers:{'Content-Type':'application/json','X-Lab-Token':token},body:JSON.stringify(requested),signal:AbortSignal.timeout(10000)});if(!response.ok)throw Error();const state=await response.json();render(state);status.textContent='Saved';}catch{render(confirmed);status.textContent='Save could not be confirmed. Reopen settings to check.';}finally{busy=false;render(confirmed);}};
 dayDetection.onchange=saveSettings;nightDetection.onchange=saveSettings;
 cap.onchange=()=>{dialog.querySelector('#negativeBacklogCountRow').hidden=!cap.checked;void saveSettings();};capCount.onchange=saveSettings;toggle.onchange=saveSettings;delay.onchange=saveSettings;
})();

// The station's coarse location, never the reviewing device's location.
(()=>{
 const viewer=document.getElementById('liveViewer');if(!viewer)return;
 const label=document.createElement('span');label.id='cameraLocation';label.className='camera-location';label.hidden=true;viewer.append(label);
 const rf=document.getElementById('rfOverlay');
 if(rf){const syncInk=()=>{const ink=rf.style.color||'#fff';if(label.style.color!==ink)label.style.color=ink;};new MutationObserver(syncInk).observe(rf,{attributes:true,attributeFilter:['style']});syncInk();}
 let timer,busy=false;
 async function refresh(){
  if(busy)return;busy=true;clearTimeout(timer);
  try{
   const response=await fetch('/api/location',{cache:'no-store',signal:AbortSignal.timeout(5000)});
   if(!response.ok)throw Error();const place=await response.json();
   const text=place.status==='known'&&typeof place.label==='string'?place.label:'';
   if(label.textContent!==text)label.textContent=text;label.hidden=!text;
  }catch{label.hidden=true;label.textContent='';}
  finally{busy=false;timer=setTimeout(refresh,30000);}
 }
 document.addEventListener('visibilitychange',()=>{if(!document.hidden)void refresh();});
 void refresh();
})();

// Aircraft radar and private center settings.
if(window.FIELD_PUBLIC_READ_ONLY!==true){const script=document.createElement("script");script.src="/air-traffic.js?v=labels-adaptive-5";document.head.append(script);}

if(window.FIELD_PUBLIC_READ_ONLY!==true&&document.querySelector(".observation-metrics")){const script=document.createElement("script");script.src="/drive-storage.js?v=1";document.head.append(script);}
