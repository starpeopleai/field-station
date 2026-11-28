'use strict';
(()=>{
 const row=document.getElementById('ce5Control'),toggle=document.getElementById('ce5Toggle');
 if(!row||window.FIELD_PUBLIC_READ_ONLY===true)return;
 row.hidden=false;let polling=false,busy=false,playing=false,lastError='';
 function render(state){playing=state.playing===true;toggle.checked=playing;toggle.disabled=busy||!state.available;toggle.title=state.error||(state.available?'Play '+state.track+' through the field station audio output':'Downloaded CE5 audio is not available on the station yet.');if(state.error&&state.error!==lastError)notice(state.error,true);lastError=state.error||'';}
 async function poll(){if(polling||busy||document.hidden)return;polling=true;try{const state=await api('/api/ce5',undefined,5000);if(!busy)render(state);}catch{toggle.title='Waiting for station audio status';}finally{polling=false;}}
 toggle.onchange=async()=>{if(busy)return;const enabled=toggle.checked;busy=true;toggle.disabled=true;try{render(await api('/api/ce5',{enabled}));}catch(e){toggle.checked=playing;notice(e.message,true);}finally{busy=false;await poll();}};
 void poll();setInterval(poll,3000);
})();

// Camera-feed shortcut for the same persisted setting used by Settings.
(()=>{
 if(window.FIELD_PUBLIC_READ_ONLY===true)return;
 const group=document.getElementById('rfOverlay');if(!group)return;
 const row=document.createElement('div');row.id='liveStreamControl';row.className='ce5-control';
 const label=document.createElement('label');label.htmlFor='liveStreamToggle';label.textContent='Live stream';
 const toggle=document.createElement('input');toggle.id='liveStreamToggle';toggle.type='checkbox';toggle.setAttribute('role','switch');toggle.setAttribute('aria-label','Live stream');toggle.disabled=true;
 toggle.title='Show the camera on YouTube when on; show the YouTube standby screen when off. Local camera viewing and capture are independent.';
 row.append(label,toggle);group.prepend(row);
 let busy=false,polling=false,confirmed=false,revision=0;
 function render(state){if(typeof state.live_streaming!=='boolean')return;confirmed=state.live_streaming;toggle.checked=confirmed;toggle.disabled=busy;}
 async function poll(){if(busy||polling||document.hidden)return;polling=true;const version=revision;try{const state=await api('/api/settings',undefined,5000);if(!busy&&version===revision)render(state);}catch{if(!busy)toggle.disabled=true;}finally{polling=false;}}
 toggle.onchange=async()=>{
  if(busy)return;const value=toggle.checked;busy=true;revision++;toggle.disabled=true;
  try{
   const auth=await api('/api/labeled-frames/token',undefined,5000);
   const response=await fetch('/api/settings',{method:'POST',headers:{'Content-Type':'application/json','X-Lab-Token':auth.token},body:JSON.stringify({live_streaming:value}),signal:AbortSignal.timeout(10000)});
   const state=await response.json();if(!response.ok)throw Error(state.error||'Live stream change could not be saved.');
   render(state);window.dispatchEvent(new CustomEvent('station-settings-updated',{detail:state}));
  }catch(error){toggle.checked=confirmed;notice(error.message,true);}
  finally{busy=false;toggle.disabled=false;void poll();}
 };
 window.addEventListener('station-settings-updated',event=>{revision++;if(!busy)render(event.detail);});
 window.addEventListener('station-reconnected',poll);
 document.addEventListener('visibilitychange',()=>{if(!document.hidden)void poll();});
 void poll();setInterval(poll,5000);
})();
