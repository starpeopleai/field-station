/* Static snapshot adapter: there is deliberately no writable server behind this UI. */
'use strict';
window.FIELD_PUBLIC_READ_ONLY=true;
window.FIELD_PUBLIC_SNAPSHOT=true;
if(location.pathname.length>1&&location.pathname.endsWith('/'))history.replaceState(null,'',location.pathname.slice(0,-1)+location.search);
(()=>{
 const network=window.fetch.bind(window),memo=new Map();
 const json=(v,status=200)=>new Response(JSON.stringify(v),{status,headers:{'Content-Type':'application/json'}});
 function load(path){if(!memo.has(path))memo.set(path,network(path).then(r=>{if(!r.ok)throw Error('Snapshot data unavailable');return r.json()}).catch(e=>{memo.delete(path);throw e}));return memo.get(path)}
 let chosenScene;
 function cameraScene(){
  if(!chosenScene)chosenScene=load('/snapshot/manifest.json').then(meta=>{
   const videos=meta.starred_videos||[];
   if(videos.length)return videos[Math.floor(Math.random()*videos.length)];
   const scenes=meta.starred_scenes||[];
   return {poster:scenes.length?scenes[Math.floor(Math.random()*scenes.length)]:'/unavailable.svg'};
  }).catch(error=>{chosenScene=null;throw error;});
  return chosenScene;
 }
 function unpack(r,fields){return Object.fromEntries(fields.map((k,i)=>[k,r[i]]).filter(([,v])=>v!==null))}
 async function objects(q){
  const data=await load('/snapshot/objects.json');const f=Object.fromEntries(data.fields.map((k,i)=>[k,i]));
  const view=q.get('view')||'all',classification=q.get('classification')||'all',review=q.get('review_status')||'all';
  if(view==='manual_recordings')return load('/snapshot/manual.json');
  const base=data.rows.filter(r=>view!=='starred'||r[f.starred]);
  const isClass=r=>classification==='all'||r[f.label]===classification;
  const isReview=r=>review==='all'||Boolean(r[f.human_reviewed])===(review==='human_reviewed');
  const count={classification:{all:0,anomalous:0,not_anomalous:0},review_status:{all:0,needs_review:0,human_reviewed:0}};
  const selected=[];
  for(const r of base){if(isReview(r)){count.classification.all++;count.classification[r[f.label]]++;}if(isClass(r)){count.review_status.all++;count.review_status[r[f.human_reviewed]?'human_reviewed':'needs_review']++;}if(isClass(r)&&isReview(r))selected.push(r);}
  const offset=Math.max(0,Number(q.get('before')||0)||0),limit=Math.min(100,Math.max(1,Number(q.get('limit')||100)||100));
  return {items:selected.slice(offset,offset+limit).map(r=>{const row=unpack(r,data.fields);row.model_classifications=data.model_sets[row.model_classifications]||[];return row}),total:selected.length,counts:data.counts,source_counts:data.source_counts,filter_counts:count,counts_indexing:false,indexing:false,ready:true,labels:['anomalous','not_anomalous'],next_cursor:offset+limit<selected.length?String(offset+limit):null};
 }
 window.fetch=async(input,options={})=>{
  const method=String(options.method||(input instanceof Request?input.method:'GET')).toUpperCase();
  if(!['GET','HEAD'].includes(method))return json({error:'Public snapshot is read only.'},405);
  const u=new URL(input instanceof Request?input.url:String(input),location.href);
  if(u.origin!==location.origin||!u.pathname.startsWith('/api/'))return network(input,options);
  try{
   if(u.pathname==='/api/objects')return json(await objects(u.searchParams));
   if(u.pathname==='/api/labeled-frames/token')return json({read_only:true});
   if(u.pathname==='/api/live/frame')return network((await cameraScene()).poster,options);
   if(u.pathname==='/api/detections/latest')return json({latest:null});
   const manifest=await load('/snapshot/manifest.json'),path=manifest.routes[u.pathname];
   if(path)return json(await load(path));
   return json({error:'Not included in this read-only snapshot.'},404);
  }catch{return json({error:'Snapshot data is temporarily unavailable.'},503)}
 };
 document.addEventListener('DOMContentLoaded',async()=>{
  const meta=await load('/snapshot/manifest.json');
  const note=document.createElement('div');note.id='snapshotFreshness';note.setAttribute('role','status');
  note.textContent='Snapshot · '+new Date(meta.captured_epoch*1000).toLocaleString();note.title='Last successful sync from the Field Station. This site remains available when the station is offline.';
  (document.querySelector('.station-header')||document.body).append(note);

  const style=document.createElement('style');style.textContent='#liveBoxes{display:none!important}#snapshotFreshness{font:10px var(--app-font,monospace);opacity:.75;margin-left:auto;padding:4px 12px;max-width:45vw;line-height:1.4}#publicReadOnly{display:none!important}.public-readonly #trainNow,.public-readonly #pauseCapture,.public-readonly #clearBacklog,.public-readonly #uploadDetections{display:none!important}';document.head.append(style);
  if(location.pathname==='/'){
   const overlay=document.querySelector('#rfOverlay');
   document.documentElement.classList.add('snapshot-camera-controls');
   const controlStyle=document.createElement('style');controlStyle.textContent='.snapshot-camera-controls .rf-overlay .session-control{display:flex!important}.snapshot-camera-controls #sessionToggle,.snapshot-camera-controls #sessionLabel{display:inline-block!important}.snapshot-camera-controls #rfOverlay input:disabled{opacity:.65;cursor:default}.snapshot-camera-controls .snapshot-rf-link{display:flex;width:100%;justify-content:space-between;background:transparent;color:inherit;border:0;padding:4px 0 10px;margin-bottom:8px;border-bottom:1px solid currentColor;font:inherit;font-size:11px;opacity:.65}';document.head.append(controlStyle);
   if(overlay){
    const controls=await load('/snapshot/camera-controls.json').catch(()=>({}));
    const addSwitch=(id,text,value)=>{let input=document.getElementById(id);if(!input){const row=document.createElement('div');row.className='ce5-control';const label=document.createElement('label');label.htmlFor=id;label.textContent=text;input=document.createElement('input');input.id=id;input.type='checkbox';input.setAttribute('role','switch');input.setAttribute('aria-label',text);row.append(label,input);overlay.prepend(row);}input.disabled=true;input.checked=value===true;input.title=typeof value==='boolean'?'Read only · state at snapshot':'Read only · state unavailable in this snapshot';input.closest('.ce5-control,.session-control')?.removeAttribute('hidden');};
    addSwitch('ce5Toggle','CE5 Tones',controls.ce5_playing);addSwitch('liveStreamToggle','Live stream',controls.live_streaming);
    const rfTrigger=overlay.querySelector('.rf-message-trigger');if(rfTrigger)overlay.prepend(rfTrigger);
    const manual=document.getElementById('sessionToggle');if(manual){manual.disabled=true;manual.title='Read only · state at snapshot';}
   }
   const label=()=>{const e=document.querySelector('#liveStatus');if(e){e.querySelector('span:last-child').textContent='Snapshot';e.title=document.querySelector('#starredCameraVideo')?'Starred recording':'Saved camera frame';e.dataset.state='snapshot';e.setAttribute('aria-label','Saved camera snapshot');}const card=document.querySelector('#noSignalCard');if(card)card.hidden=true;document.querySelector('#liveViewer')?.classList.remove('no-camera-signal');};window.updateLiveHealth=label;const photo=document.querySelector('#liveImage');const scene=await cameraScene();const still=scene.poster;photo.alt=still==='/unavailable.svg'?'No starred scene available':'Starred Field Station scene';photo.src=still;
   if(scene.url){
    const video=document.createElement('video');
    video.id='starredCameraVideo';video.autoplay=true;video.loop=false;video.muted=true;video.playsInline=true;
    video.poster=still;video.setAttribute('aria-label','Starred Field Station recording');
    video.style.cssText='display:block!important;position:absolute;inset:0;width:100%;height:100%;object-fit:contain';
    const playlist=meta.starred_videos.filter(item=>item.url!==scene.url);
    for(let i=playlist.length-1;i>0;i--){
     const j=Math.floor(Math.random()*(i+1));
     [playlist[i],playlist[j]]=[playlist[j],playlist[i]];
    }
    playlist.unshift(scene);
    let index=0;
    function startClip(){
     const item=playlist[index];
     chosenScene=Promise.resolve(item);
     photo.src=item.poster;video.poster=item.poster;video.src=item.url;
     video.play().catch(error=>{if(error.name==='NotAllowedError')video.controls=true;});
    }
    video.addEventListener('ended',()=>{index=(index+1)%playlist.length;startClip();});
    video.addEventListener('error',()=>{
     playlist.splice(index,1);
     if(!playlist.length){video.remove();return;}
     index%=playlist.length;startClip();
    });
    photo.after(video);startClip();
   }
   const radarCSS=document.createElement('link');radarCSS.rel='stylesheet';radarCSS.href='/snapshot-radar.css?v=1';document.head.append(radarCSS);
   const radar=document.createElement('script');radar.src='/snapshot-radar.js?v=1';document.head.append(radar);
   label();setInterval(label,1000);
  }
 });
})();
