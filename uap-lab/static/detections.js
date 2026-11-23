'use strict';
(()=>{
 const $=id=>document.getElementById(id),views=[['starred','Starred'],['all','All'],['anomalous','Anomalous'],['not_anomalous','Not Anomalous'],['needs_review','Machine-only review'],['human_reviewed','Human-reviewed'],['human_reviewed_anomalous','Human-reviewed anomalous']];
 let view=new URLSearchParams(location.search).get('view')||'all',token='',cursor='',more=true,loading=false,version=0,anchor=null,draining=false;
 if(!views.some(([v])=>v===view))view='all';
 window.REVIEW_FILTERS.enableStarred(views.some(([v])=>v==='starred'));view=window.REVIEW_FILTERS.view();
 const rows=new Map(),selected=new Set(),pending=new Map(),deleting=new Set(),starring=new Set(),deletedIds=new Set(),dismissed=new Set(),prefix='field-station.object-review.';
 const retainedFields=['id','kind','label','human_reviewed','created','image_url','frame_url','frame_bounds','review_url','starred','archive_url','archive_bundle_url','archive_bundle_updating'];
 function persist(item){const row=Object.fromEntries(retainedFields.filter(k=>item.row[k]!==undefined).map(k=>[k,item.row[k]]));try{localStorage.setItem(prefix+item.body.request_id,JSON.stringify({...item,row,durable:undefined}));item.durable=true;return true;}catch{item.durable=false;return false;}}
 function forget(key){try{localStorage.removeItem(key);}catch{}}
 window.addEventListener('beforeunload',e=>{if([...pending.values()].some(i=>i.durable===false)){e.preventDefault();e.returnValue='';}});
 const pretty=label=>label==='anomalous'?'Anomalous':'Not Anomalous';
 const el=(tag,text)=>{const n=document.createElement(tag);if(text!==undefined)n.textContent=text;return n;};
 async function api(path,body){try{const r=await fetch(path,{signal:AbortSignal.timeout(path==='/api/objects/labels'?180000:30000),...(body?{method:'POST',headers:{'Content-Type':'application/json','X-Lab-Token':token},body:JSON.stringify(body)}:{})});const d=await r.json();if(!r.ok){const error=Error(d.error||'Request failed');error.status=r.status;throw error;}return d;}catch(e){if(e.name==='AbortError'||e.name==='TimeoutError'||e instanceof TypeError){const error=Error(body?'Connection interrupted. Labels will retry; keep this page open until saves are confirmed.':'Connection to the station is delayed. Retrying automatically.');error.transient=true;throw error;}throw e;}}
 let noticeTimer;function notice(text){clearTimeout(noticeTimer);$('queueSaved').textContent=text;$('queueToast').hidden=false;if(!pending.size)noticeTimer=setTimeout(()=>{$('queueToast').hidden=true;},6000);}
 function saving(id){return pending.has(id)&&!pending.get(id).failed;}
 function progress(){if(!pending.size)return;const failed=[...pending.values()].filter(i=>i.failed).length;notice((pending.size-failed)+' waiting for confirmation'+(failed?' · '+failed+' need attention; choose a label on the returned frames to retry.':([...pending.values()].some(i=>i.durable===false)?'. Browser storage unavailable; keep this page open until saves are confirmed.':'. Labels are retained on this device.')));}
 function restore(item){dismissed.delete(item.row.id);if(!deletedIds.has(item.row.id)&&matches(item.row)&&!rows.has(item.row.id)){rows.set(item.row.id,item.row);$('detectionQueue').prepend(card(item.row));}$('queueEmpty').hidden=rows.size>0;}
 function storageFailure(message){return /\[Errno (28|69|122)\]|no space left on device|disk quota exceeded/i.test(message||'');}
 function missingCropFailure(message){return /\[Errno 2\].*notifications\/outbox\/.*native-object\.png/i.test(message||'');}
 function retrySave(item,error,delay=30000){item.failed=false;item.error=error;item.attempts=0;item.retryAt=Date.now()+delay;persist(item);}
 function fail(item,message){item.failed=true;item.error=message;persist(item);restore(item);}
 function matches(row){return window.REVIEW_FILTERS.matches(row);}
 function selection(){
  const cards=new Map([...$('detectionQueue').children].map(n=>[n.dataset.id,n]));for(const [id,row] of rows){const card=cards.get(id);if(!card)continue;card.classList.toggle('selected',selected.has(id));const checkbox=card.querySelector('.frame-select');if(checkbox)checkbox.checked=selected.has(id);card.querySelectorAll('button,input').forEach(b=>b.disabled=b.dataset.bundleUpdating==='true'||saving(id)||deleting.has(id)||starring.has(id));}
  $('bulkReview').hidden=!selected.size;$('selectionCount').textContent=selected.size+' selected';
 }
 function select(id,event){if(saving(id)||deleting.has(id))return;const ids=[...rows.keys()],a=ids.indexOf(anchor),b=ids.indexOf(id);if(event.shiftKey&&a>=0){for(const k of ids.slice(Math.min(a,b),Math.max(a,b)+1))if(!saving(k))selected.add(k);}else{selected.has(id)?selected.delete(id):selected.add(id);anchor=id;}selection();}
 function thumbnail(image,url,alt){
  const img=el('img'),status=el('span');let attempts=0,timer=null,failed=false;
  img.alt=alt;img.loading='lazy';img.decoding='async';status.hidden=true;status.setAttribute('role','status');status.style.cssText='position:absolute;inset:0;align-items:center;justify-content:center;padding:16px;display:none;font-size:12px';
  function message(text){status.textContent=text;status.hidden=!text;status.style.display=text?'flex':'none';img.style.visibility=text?'hidden':'';}
  function retry(){if(!image.isConnected)return;clearTimeout(timer);failed=false;img.loading='eager';message('Retrying thumbnail…');const next=new URL(url,location.href);next.searchParams.set('_thumbnail_retry',Date.now()+'-'+attempts);img.src=next.href;}
  img.onload=()=>{failed=false;clearTimeout(timer);message('');};
  img.onerror=()=>{failed=true;message('Thumbnail unavailable · retrying…');const delays=[1000,3000,8000,20000];if(attempts<delays.length)timer=setTimeout(retry,delays[attempts++]);else message('Thumbnail unavailable · click to retry');};
  image.addEventListener('click',event=>{if(!failed)return;event.preventDefault();event.stopImmediatePropagation();attempts=0;retry();},true);
  image.append(img,status);img.src=url;
 }
 function manualCard(row){
  const n=el('article');n.className='detection-card manual-recording-card';n.dataset.id=row.id;
  const heading=el('h2',new Date(row.created*1000).toLocaleString([], {month:'short',day:'numeric',hour:'numeric',minute:'2-digit'}));
  const state=el('span',row.state==='recording'?'Recording':row.state==='ready'?'Ready':row.state==='failed'?'Preparation needs attention':'Preparing video');state.className='manual-state';
  const duration=Number(row.duration_seconds),meta=el('p',Number.isFinite(duration)&&duration>0?Math.floor(duration/60)+'m '+Math.round(duration%60)+'s':'Manual recording');
  n.append(heading,state,meta);
  if(row.deletion?.state){state.textContent='Deleting';n.append(el('p',row.deletion.error?'Deletion will retry: '+row.deletion.error:row.deletion.state==='removing_from_archive'?'Removing from Internet Archive…':'Deleting recording and its Internet Archive upload…'));return n;}
  if(window.FIELD_PUBLIC_READ_ONLY!==true&&row.state!=='recording'){
   const remove=el('button','Delete recording');remove.type='button';remove.className='delete-manual-recording';
   remove.onclick=async()=>{if(!confirm('Delete this manual recording and remove its Internet Archive upload? Saved training frames and labels will remain.'))return;remove.disabled=true;deleting.add(row.id);try{const result=await api('/api/manual-recordings/delete',{session_id:row.session_id});row.deletion=result;const replacement=manualCard(row);n.replaceWith(replacement);notice('Deletion requested. Internet Archive removal will retry automatically until confirmed.');}catch(error){remove.disabled=false;notice('Delete needs attention: '+error.message);}finally{deleting.delete(row.id);}};
   n.append(remove);
  }
  if(row.video_url){const video=el('video');video.controls=true;video.playsInline=true;video.preload='none';video.src=row.video_url;video.setAttribute('aria-label','Manual recording from '+heading.textContent);n.append(video);const download=el('a','Download video');download.href=row.video_url;download.download=row.session_id+'.mp4';n.append(download);}
  else n.append(el('p',row.state==='recording'?'Video will be available when recording stops.':row.state==='failed'?'Original footage is retained.':'Preparing the full-quality video…'));
  if(row.review_url){const link=el('a','Review video');link.href=row.review_url;n.append(link);}
  if(row.label)n.append(el('p',pretty(row.label)+' · Human-reviewed recording'));
  if(row.archive_url){const a=el('a','Internet Archive');a.href=row.archive_url;a.target='_blank';a.rel='noopener noreferrer';n.append(a);}
  if(row.upload_state&&!['verified','retaining','cleaned'].includes(row.upload_state))n.append(el('p',row.upload_state==='verifying'?'Verifying Internet Archive upload…':row.upload_state==='uploading'||row.upload_state==='completing'?'Uploading to Internet Archive…':'Preparing Internet Archive upload…'));
  return n;
 }
 function modelResults(row){
  const models=el('div');models.className='object-model-results';models.setAttribute('aria-label','Current model classifications');
  for(const [lane,name] of [['human','Stable'],['experimental','Experimental'],['hybrid','Hybrid'],['machine','Machine-only'],['rotation','Rotation']]){const result=row.model_classifications?.find(r=>r.lane===lane);const line=el('div');line.append(el('span',name),el('span',result?.state==='ready'?pretty(result.label):result?.state==='unavailable'?'Unavailable':'Pending'));line.title=result?.state==='ready'?`${result.version?.slice(0,12)} · anomaly score ${(result.anomaly_score*100).toFixed(1)}% · ${result.scope==='review_box'?'whole review box':result.scope==='detection_context'?'original detection and night context':'annotated crop'}`:'Waiting for HQ model scoring';models.append(line);}
  return models;
 }
 function card(row){
  if(row.kind==='manual_recording')return manualCard(row);
  const n=el('article');n.className='detection-card';n.dataset.id=row.id;
  if(window.FIELD_PUBLIC_READ_ONLY!==true){
   const star=el('button');star.className='detection-star';star.type='button';
   function showStar(){star.textContent=row.starred?'★':'☆';star.setAttribute('aria-pressed',String(!!row.starred));star.setAttribute('aria-label',row.starred?'Unstar frame':'Star frame');star.title=row.starred?'Unstar frame':'Star frame';}
   showStar();star.onclick=async event=>{event.preventDefault();event.stopPropagation();if(starring.has(row.id)||saving(row.id)||deleting.has(row.id))return;const wanted=!row.starred;starring.add(row.id);selection();star.disabled=true;
    try{const result=await api('/api/objects/star',{id:row.id,starred:wanted});if(result.starred!==wanted)throw Error('Star change was not confirmed');row.starred=result.starred;showStar();if(!matches(row)){rows.delete(row.id);selected.delete(row.id);n.remove();$('queueEmpty').hidden=rows.size>0;}notice(wanted?'Frame starred.':'Star removed.');}
    catch(error){notice('Star needs attention: '+error.message);}finally{starring.delete(row.id);star.disabled=false;selection();}
   };n.append(star);
  }
  const image=el('button');image.className='detection-image';image.type='button';image.setAttribute('aria-label','Select '+pretty(row.label)+' object');thumbnail(image,row.image_url,pretty(row.label)+' detected object');image.onclick=e=>{select(row.id,e);n.classList.toggle('controls-open');};
  const actions=el('div');actions.className='category-actions';const grid=el('div');grid.className='category-grid';
  for(const label of ['anomalous','not_anomalous']){const b=el('button',pretty(label));b.type='button';b.setAttribute('aria-label','Label as '+pretty(label));b.onclick=()=>enqueue(row,label);grid.append(b);}
  const links=el('div');links.className='review-actions';const inspect=el('button','Inspect frame');inspect.onclick=()=>{$('queueFrameBox').hidden=true;$('queueFullFrame').onload=()=>{const b=row.frame_bounds,img=$('queueFullFrame'),box=$('queueFrameBox');if(!b)return;Object.assign(box.style,{left:(img.offsetLeft+b.x*img.clientWidth)+'px',top:(img.offsetTop+b.y*img.clientHeight)+'px',width:(b.w*img.clientWidth)+'px',height:(b.h*img.clientHeight)+'px'});box.hidden=false;};$('queueFullFrame').src=row.frame_url;$('queueVideoLink').hidden=!row.review_url;if(row.review_url)$('queueVideoLink').href=row.review_url;$('queueFrame').showModal();};links.append(inspect);
  if(row.review_url){const link=el('a','Review video');link.href=row.review_url;if(row.kind==='review'&&row.sample_id){const url=new URL(link.href);url.searchParams.set('sample',row.sample_id);link.href=url.href;}links.append(link);}
  const archive=/^https:\/\/archive\.org\/details\/[A-Za-z0-9_.-]+$/.test(row.archive_url||'')?el('a','View archived bundle'):null;
  if(archive){archive.href=row.archive_url;archive.target='_blank';archive.rel='noopener noreferrer';archive.className='frame-archive-link';}
  if(archive&&/^https:\/\/archive\.org\/compress\/[A-Za-z0-9_.-]+$/.test(row.archive_bundle_url||'')){const bundle=el('a','Download bundle');bundle.href=row.archive_bundle_url;links.append(bundle);}
  if(row.archive_bundle_updating){const bundle=el('button','Bundle updating…');bundle.disabled=true;bundle.dataset.bundleUpdating='true';links.append(bundle);}
  const omit=el('button','Omit data');omit.type='button';omit.title='Delete this object and its unshared local media';omit.onclick=async()=>{if(saving(row.id)||omit.disabled)return;deleting.add(row.id);omit.disabled=true;omit.textContent='Deleting…';n.querySelectorAll('button,input').forEach(b=>b.disabled=true);try{const result=await api('/api/objects/omit',{id:row.id});if(!result.deleted)throw Error('Deletion not confirmed');deletedIds.add(row.id);const queued=pending.get(row.id);if(queued){forget(prefix+queued.body.request_id);if(queued.legacyKey)forget(queued.legacyKey);pending.delete(row.id);}rows.delete(row.id);selected.delete(row.id);n.remove();selection();notice(result.cleanup_pending?'Object deleted; shared recording cleanup is pending.':'Object and unshared media deleted.');for(const [key]of views){const included=key==='all'||(key==='human_reviewed_anomalous'?row.human_reviewed&&row.label==='anomalous':key==='human_reviewed'?row.human_reviewed:key==='needs_review'?(!row.human_reviewed&&row.label==='anomalous'):row.label===key);if(included&&Number.isFinite(tabCounts[key]))tabCounts[key]=Math.max(0,tabCounts[key]-1);}renderTabs();$('queueEmpty').hidden=rows.size>0;}catch(e){omit.textContent='Omit data';notice('Delete needs attention: '+e.message);}finally{deleting.delete(row.id);selection();}};if(window.FIELD_PUBLIC_READ_ONLY!==true)links.append(omit);
  const error=el('p');error.className='queue-error';error.setAttribute('role','status');
  if(pending.get(row.id)?.failed)error.textContent='Save needs attention: '+pending.get(row.id).error+'. Choose a label to retry.';
  actions.append(grid,links,error);const box=el('input');box.type='checkbox';box.className='frame-select';box.setAttribute('aria-label','Select object for bulk classification');box.onclick=e=>{e.stopPropagation();select(row.id,e);};
  n.addEventListener('click',e=>{if(e.shiftKey&&!e.target.closest('a,input,.detection-star')){e.preventDefault();e.stopImmediatePropagation();select(row.id,e);}},true);
  const models=modelResults(row);
  n.append(image,models,actions,box);if(archive)n.append(archive);return n;
 }
 const tabButtons=new Map(),tabCounts={};let completeCounts=false;
 function renderTabs(counts,indexing=false,filters,sources){
  if(counts&&!indexing){for(const [key]of views)if(Number.isFinite(counts[key]))tabCounts[key]=counts[key];completeCounts=true;}
  window.REVIEW_FILTERS.render(filters,indexing,sources,counts);
 }
 window.addEventListener('review-filter-change',event=>{view=window.REVIEW_FILTERS.view();dismissed.clear();event.detail.completion=reset();});

 let refreshFailed=false;
 async function refresh(countsOnly=false){
  if(loading)return;loading=true;const rev=version;
  try{
   const data=await api('/api/objects?'+window.REVIEW_FILTERS.query(''));if(rev!==version)return;
   refreshFailed=false;renderTabs(data.counts,(data.counts_indexing??data.indexing)||data.ready===false,data.filter_counts,data.source_counts);
   if(countsOnly)return;
   for(const row of data.items){const node=[...$('detectionQueue').children].find(n=>n.dataset.id===row.id);if(node?.querySelector('.object-model-results')&&JSON.stringify(rows.get(row.id)?.model_classifications)!==JSON.stringify(row.model_classifications)){node.querySelector('.object-model-results').replaceWith(modelResults(row));if(rows.has(row.id))rows.get(row.id).model_classifications=row.model_classifications;}}
   // An incomplete index is not evidence that existing cards disappeared.
   if(data.ready===false||selected.size||deleting.size||starring.size||$('queueFrame').open||document.querySelector('.detection-card:hover,.controls-open')||[...$('detectionQueue').querySelectorAll('video')].some(v=>!v.paused))return;
   const items=data.items.filter(row=>!deletedIds.has(row.id)&&!saving(row.id)&&!dismissed.has(row.id)),wanted=new Set(items.map(row=>row.id)),grid=$('detectionQueue'),nodes=new Map([...grid.children].map(node=>[node.dataset.id,node]));
   if(pending.size||data.indexing){for(const row of [...items].reverse())if(!rows.has(row.id)){rows.set(row.id,row);grid.prepend(card(row));}$('queueEmpty').hidden=rows.size>0;selection();return;}
   for(const [id,node]of nodes)if(!wanted.has(id)){node.remove();rows.delete(id);}
   for(const [index,row]of items.entries()){
    let node=nodes.get(row.id);
    if(!node||JSON.stringify(rows.get(row.id))!==JSON.stringify(row)){const replacement=card(row);if(node)node.replaceWith(replacement);node=replacement;}
    if(grid.children[index]!==node)grid.insertBefore(node,grid.children[index]||null);
   }
   rows.clear();for(const row of items)rows.set(row.id,row);
   cursor=data.next_cursor||'';more=!!cursor;$('moreDetections').hidden=!more;$('queueEmpty').hidden=rows.size>0;selection();
  }catch(e){if(rev===version){if(!refreshFailed&&!pending.size)notice(e.message);refreshFailed=true;}}finally{if(rev===version)loading=false;}
 }
 async function reset(){window.REVIEW_FILTERS.showClips([]);version++;loading=false;cursor='';more=true;rows.clear();selected.clear();anchor=null;$('detectionQueue').replaceChildren();renderTabs(undefined,true);selection();await load();}
 async function load(){if(loading||!more)return;loading=true;const rev=version;$('moreDetections').disabled=true;
  try{const data=await api('/api/objects?'+window.REVIEW_FILTERS.query(cursor));if(rev!==version)return;window.REVIEW_FILTERS.showClips(data.capture_clips||[]);if(data.index_error&&data.ready===false)notice('Could not load detections: '+data.index_error);cursor=data.next_cursor||'';more=!!cursor;renderTabs(data.counts,(data.counts_indexing??data.indexing)||data.ready===false,data.filter_counts,data.source_counts);
   for(const row of data.items)if(!rows.has(row.id)&&!deletedIds.has(row.id)&&!saving(row.id)&&!dismissed.has(row.id)){rows.set(row.id,row);$('detectionQueue').append(card(row));}
   $('queueStatus').textContent=data.ready===false?(data.index_error?'Library could not be loaded: '+data.index_error:'Loading the object library…'):(data.indexing?'Updating library…':'');$('queueEmpty').hidden=rows.size>0||data.ready===false||data.indexing;if(data.ready===false&&data.indexing)setTimeout(()=>{if(rev===version)refresh();},2000);$('moreDetections').hidden=!more;for(const item of pending.values())if(item.failed)restore(item);selection();if(!rows.size&&more)setTimeout(load,0);
  }catch(e){if(rev===version)notice(e.message);}finally{if(rev===version){loading=false;$('moreDetections').disabled=false;}}
 }
 function enqueue(row,label,bulk=false){if(saving(row.id)||deleting.has(row.id))return;const previous=pending.get(row.id);const item={row,body:{id:row.id,label,queued_at:Date.now()/1000,request_id:Array.from(crypto.getRandomValues(new Uint8Array(16)),v=>v.toString(16).padStart(2,'0')).join('')}};
  persist(item);
  if(previous){forget(prefix+previous.body.request_id);if(previous.legacyKey)forget(previous.legacyKey);}pending.set(row.id,item);dismissed.add(row.id);selected.delete(row.id);rows.delete(row.id);[...$('detectionQueue').children].find(n=>n.dataset.id===row.id)?.remove();$('queueEmpty').hidden=rows.size>0;progress();if(!bulk){selection();drain();}
 }
 async function drain(){if(draining||!token)return;draining=true;let saved=0,failures=0;
  try{const work=[...pending].filter(([,item])=>!item.failed&&(!item.retryAt||item.retryAt<=Date.now()));for(let offset=0;offset<work.length;offset+=50){const batch=work.slice(offset,offset+50);let results;
   try{const response=await api('/api/objects/labels',{items:batch.map(([,item])=>item.body)});results=new Map((response.results||[]).map(r=>[r.request_id,r]));}
   catch(e){if(e.status===403){try{token=(await api('/api/labeled-frames/token')).token;}catch{}}else if(e.status>=400&&e.status<500&&![408,429].includes(e.status)){for(const [,item]of batch)fail(item,e.message);}failures++;break;}
   for(const [id,item]of batch){const result=results.get(item.body.request_id);
    if(result?.discarded){forget(prefix+item.body.request_id);if(item.legacyKey)forget(item.legacyKey);pending.delete(id);continue;}
    if(!result?.saved){failures++;if(result?.retryable||storageFailure(result?.error)){retrySave(item,result?.error);continue;}item.attempts=(item.attempts||0)+1;if(item.attempts>=3)fail(item,result?.error||'Save was not confirmed');continue;}
    forget(prefix+item.body.request_id);if(item.legacyKey)forget(item.legacyKey);pending.delete(id);dismissed.add(id);saved++;
    const row=rows.get(id);if(row){row.label=result.label;row.human_reviewed=true;const old=[...$('detectionQueue').children].find(n=>n.dataset.id===id);if(matches(row)){old?.replaceWith(card(row));}else{old?.remove();rows.delete(id);}}selected.delete(id);
   }
   progress();selection();if(rows.size<100&&!selected.size)void refresh();
  }}finally{draining=false;selection();if(pending.size)progress();else if(saved)notice(saved+' object'+(saved===1?'':'s')+' reviewed');if(saved&&!pending.size&&!selected.size)await refresh();else if(!rows.size&&more)await load();}
 }
 for(const label of ['anomalous','not_anomalous']){const b=el('button',pretty(label));b.onclick=()=>{for(const id of [...selected])enqueue(rows.get(id),label,true);selection();drain();};$('bulkCategories').append(b);}
 new ResizeObserver(()=>document.documentElement.style.setProperty('--bulk-review-height',$('bulkReview').getBoundingClientRect().height+'px')).observe($('bulkReview'));
 $('selectAll').onclick=()=>{for(const id of rows.keys())if(!saving(id))selected.add(id);selection();};$('clearSelection').onclick=()=>{selected.clear();anchor=null;selection();};
 $('moreDetections').onclick=load;$('closeQueueFrame').onclick=()=>$('queueFrame').close();
 document.addEventListener('keydown',e=>{if(e.key==='Escape'){selected.clear();selection();return;}if(e.defaultPrevented||e.repeat||e.isComposing||e.ctrlKey||e.metaKey||e.altKey||!selected.size||e.target.closest?.('input:not([type="checkbox"]):not([type="radio"]):not([type="button"]),textarea,select,[contenteditable]:not([contenteditable="false"]),[role="textbox"]')||document.querySelector('dialog[open],[aria-modal="true"]')||window.FIELD_PUBLIC_READ_ONLY===true)return;const index={a:0,n:1}[e.key.toLowerCase()];if(index===undefined)return;e.preventDefault();$('bulkCategories').children[index]?.click();});
 try{const keys=Array.from({length:localStorage.length},(_,i)=>localStorage.key(i));for(const k of keys){if(k?.startsWith(prefix)||k?.startsWith('field-station.pending-label.')){try{const item=JSON.parse(localStorage.getItem(k));if(!item.row?.id||!item.body?.request_id||item.row.kind==='video')continue;if(!k.startsWith(prefix))item.legacyKey=k;if(item.failed&&(storageFailure(item.error)||missingCropFailure(item.error)))retrySave(item,item.error,0);persist(item);pending.set(item.row.id,item);}catch{notice('A retained review could not be read. Other labels will still save.');}}}}catch{notice('Browser storage unavailable; keep this page open until saves are confirmed.');}
 window.fieldReviewHasPending=()=>pending.size>0;
 window.addEventListener('station-backlog-cleared',()=>{void reset();});
 window.addEventListener('online',drain);window.addEventListener('station-reconnected',e=>{token=e.detail.token;drain();});
 setInterval(()=>{if(pending.size)drain();},5000);
 // Refresh only when idle; never replace a selection or open inspection.
 setInterval(()=>{if(!document.hidden&&!loading)refresh(rows.size>100||selected.size>0||deleting.size>0||starring.size>0||$('queueFrame').open||window.scrollY>=150||!!document.querySelector('.detection-card:hover,.controls-open'));},15000);
 new IntersectionObserver(entries=>{if(entries.some(e=>e.isIntersecting)&&rows.size)load();},{rootMargin:'200px'}).observe($('moreDetections'));
 api('/api/labeled-frames/token').then(async d=>{const cutoff=d.pending_reset?.epoch||0;let discarded=0;for(const [id,item] of pending){if(cutoff&&(!item.body.queued_at||item.body.queued_at<=cutoff)){forget(prefix+item.body.request_id);if(item.legacyKey)forget(item.legacyKey);pending.delete(id);discarded++;}}token=d.token;await reset();progress();if(discarded)notice(discarded+' pending labels discarded as requested');await drain();}).catch(e=>{notice(e.message);});
})();
