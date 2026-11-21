/* Private aircraft context: no radar centers or provider data in public snapshots. */
(()=>{
 'use strict';
 if(window.FIELD_PUBLIC_READ_ONLY===true)return;
 let token='', tokenAt=0;
 async function api(path,body){
  if(!token||Date.now()-tokenAt>60000){const r=await fetch('/api/labeled-frames/token',{cache:'no-store',signal:AbortSignal.timeout(8000)});if(!r.ok)throw Error('Station unavailable');token=(await r.json()).token;tokenAt=Date.now();}
  const r=await fetch(path,{method:body?'POST':'GET',headers:{'X-Lab-Token':token,...(body?{'Content-Type':'application/json'}:{})},...(body?{body:JSON.stringify(body)}:{}),cache:'no-store',signal:AbortSignal.timeout(12000)});
  if(r.status===403){token='';throw Error('Reconnecting to station');}const v=await r.json();if(!r.ok)throw Error(v.error||'Air traffic unavailable');return v;
 }
 const css=document.createElement('link');css.rel='stylesheet';css.href='/air-traffic.css?v=6';document.head.append(css);
 const settings=document.querySelector('#stationSettings');
 if(settings){
  const area=document.createElement('div');area.className='air-traffic-settings';
  area.innerHTML='<label for="radarAddress">Radar center address</label><div class="radar-address-row"><input id="radarAddress" type="text" autocomplete="off" maxlength="250" placeholder="Address or latitude, longitude" aria-describedby="radarResolvedAddress"></div><p id="radarResolvedAddress"></p><label for="radarRadius">Radar radius (miles)</label><div class="radar-address-row"><input id="radarRadius" type="number" min="1" max="100" step="1" value="15"></div><label for="cameraAzimuth">Camera azimuth (° true)</label><div class="radar-address-row"><input id="cameraAzimuth" type="number" min="0" max="359.9" step="0.1" placeholder="Not set" aria-describedby="cameraAzimuthHelp"></div><p id="cameraAzimuthHelp">0° N · 90° E · 180° S · 270° W</p><label for="cameraElevation">Camera elevation (°)</label><div class="radar-address-row"><input id="cameraElevation" type="number" min="-90" max="90" step="0.1" placeholder="Not set" aria-describedby="cameraElevationHelp"><button id="radarAddressSave" type="button">Save</button></div><p id="cameraElevationHelp">0° horizon · 90° straight up · negative below horizon</p><p id="radarAddressStatus" role="status"></p>';
  settings.insertBefore(area,settings.querySelector('#stationLocation'));
  const input=area.querySelector('#radarAddress'),radius=area.querySelector('#radarRadius'),azimuth=area.querySelector('#cameraAzimuth'),elevation=area.querySelector('#cameraElevation'),button=area.querySelector('button'),status=area.querySelector('#radarAddressStatus');let dirty=false,busy=false;
  for(const control of [input,radius,azimuth,elevation])control.addEventListener('input',()=>{dirty=true;status.textContent='';});
  async function load(){if(dirty||busy)return;try{const s=await api('/api/air-traffic/settings');input.value=s.address;area.querySelector('#radarResolvedAddress').textContent=s.resolved_address||s.address;radius.value=Math.round(s.radius_nm*1.150779448);azimuth.value=s.camera_azimuth_deg??'';elevation.value=s.camera_elevation_deg??'';renderLandmarks(s.landmarks);}catch(e){status.textContent=e.message;}}
  document.querySelector('#stationSettingsOpen')?.addEventListener('click',load);
  async function save(){if(busy)return;busy=true;button.disabled=true;input.disabled=true;radius.disabled=true;azimuth.disabled=true;elevation.disabled=true;status.textContent='Saving radar settings…';try{const s=await api('/api/air-traffic/settings',{address:input.value,radius_miles:Number(radius.value),camera_azimuth_deg:azimuth.value.trim()===''?null:Number(azimuth.value),camera_elevation_deg:elevation.value.trim()===''?null:Number(elevation.value)});input.value=s.address;area.querySelector('#radarResolvedAddress').textContent=s.resolved_address||s.address;radius.value=Math.round(s.radius_nm*1.150779448);azimuth.value=s.camera_azimuth_deg??'';elevation.value=s.camera_elevation_deg??'';renderLandmarks(s.landmarks);dirty=false;status.textContent='Saved · '+(s.resolved_address||s.address);window.dispatchEvent(new Event('radar-center-changed'));}catch(e){status.textContent=e.message;}finally{busy=false;button.disabled=false;input.disabled=false;radius.disabled=false;azimuth.disabled=false;elevation.disabled=false;}}
  const landmarks=document.createElement('div');landmarks.className='radar-landmark-settings';
  landmarks.innerHTML='<label for="radarLandmarkAddress">Radar landmarks</label><input id="radarLandmarkName" aria-label="Landmark name (optional)" maxlength="60" placeholder="Name (optional)"><div class="radar-address-row"><input id="radarLandmarkAddress" maxlength="250" placeholder="Address or landmark" autocomplete="off"><button type="button" id="radarLandmarkAdd">Add</button></div><p role="status" id="radarLandmarkStatus"></p><ul class="radar-landmark-list"></ul>';
  area.append(landmarks);
  const landmarkName=landmarks.querySelector('#radarLandmarkName'),landmarkAddress=landmarks.querySelector('#radarLandmarkAddress'),landmarkAdd=landmarks.querySelector('#radarLandmarkAdd'),landmarkStatus=landmarks.querySelector('#radarLandmarkStatus'),list=landmarks.querySelector('ul');let landmarkBusy=false;
  function renderLandmarks(items){list.replaceChildren();for(const item of items||[]){const row=document.createElement('li'),text=document.createElement('span'),remove=document.createElement('button');text.textContent=item.label;text.title=item.address;remove.type='button';remove.textContent='Remove';remove.setAttribute('aria-label','Remove '+item.label);remove.disabled=landmarkBusy;remove.addEventListener('click',()=>changeLandmark({action:'remove_landmark',id:item.id}));row.append(text,remove);list.append(row);}}
  async function changeLandmark(body){if(landmarkBusy)return;landmarkBusy=true;landmarkAdd.disabled=true;list.querySelectorAll('button').forEach(b=>b.disabled=true);landmarkStatus.textContent=body.action==='add_landmark'?'Finding landmark…':'Removing…';try{const config=await api('/api/air-traffic/settings',body);if(body.action==='add_landmark'){landmarkName.value='';landmarkAddress.value='';}renderLandmarks(config.landmarks);landmarkStatus.textContent='Saved';window.dispatchEvent(new Event('radar-center-changed'));}catch(e){landmarkStatus.textContent=e.message;}finally{landmarkBusy=false;landmarkAdd.disabled=false;list.querySelectorAll('button').forEach(b=>b.disabled=false);}}
  landmarkAdd.addEventListener('click',()=>changeLandmark({action:'add_landmark',address:landmarkAddress.value,label:landmarkName.value}));
  for(const control of [landmarkName,landmarkAddress])control.addEventListener('keydown',e=>{if(e.key==='Enter'){e.preventDefault();landmarkAdd.click();}});
  button.addEventListener('click',save);input.addEventListener('keydown',e=>{if(e.key==='Enter'){e.preventDefault();save();}});
 }
 const viewer=document.querySelector('#liveViewer');
 if(viewer){
  const panel=document.createElement('section');panel.className='air-radar';panel.setAttribute('aria-label','Nearby aircraft');
  panel.innerHTML='<div class="air-radar-heading"><span>Air traffic</span><span class="air-radar-state" role="status">Connecting…</span></div><div class="air-radar-stage"><canvas width="520" height="520" role="img" aria-label="North-up aircraft radar with direction-of-travel arrows"></canvas><div class="air-radar-tip" hidden></div></div><div class="air-radar-footer"><span class="air-radar-center"></span><a href="https://adsb.fi/" target="_blank" rel="noopener noreferrer">adsb.fi ↗</a></div>';
  viewer.append(panel);
  const canvas=panel.querySelector('canvas'),ctx=canvas.getContext('2d'),state=panel.querySelector('.air-radar-state'),center=panel.querySelector('.air-radar-center'),tip=panel.querySelector('.air-radar-tip');let latest=null,points=[],busy=false,timer,requestFailed=false;
  const rf=document.querySelector('#rfOverlay');
  function ink(){panel.style.color=rf?.style.color||'#fff';draw();}
  if(rf)new MutationObserver(ink).observe(rf,{attributes:true,attributeFilter:['style']});
  const radians=n=>n*Math.PI/180;
  function position(a,c){
   const p1=radians(c.latitude),p2=radians(a.latitude),dl=radians(a.longitude-c.longitude),dp=p2-p1;
   const h=Math.sin(dp/2)**2+Math.cos(p1)*Math.cos(p2)*Math.sin(dl/2)**2;
   const distance=3440.065*2*Math.atan2(Math.sqrt(h),Math.sqrt(Math.max(0,1-h)));
   const bearing=Math.atan2(Math.sin(dl)*Math.cos(p2),Math.cos(p1)*Math.sin(p2)-Math.sin(p1)*Math.cos(p2)*Math.cos(dl));return {distance,bearing};
  }
  function draw(){
   const heading=Number.isFinite(latest?.camera_azimuth_deg)?radians(latest.camera_azimuth_deg):0;
   const color=getComputedStyle(panel).color,cx=260,cy=260,r=218;ctx.clearRect(0,0,520,520);ctx.strokeStyle=color;ctx.fillStyle=color;ctx.lineWidth=1.5;ctx.font=(canvas.clientWidth<180?'28':'19')+'px "IBM Plex Mono", monospace';ctx.textAlign='center';points=[];
   for(const fraction of [1/3,2/3,1]){ctx.globalAlpha=.32;ctx.beginPath();ctx.arc(cx,cy,r*fraction,0,Math.PI*2);ctx.stroke();}
   ctx.globalAlpha=.24;ctx.beginPath();ctx.moveTo(cx-r,cy);ctx.lineTo(cx+r,cy);ctx.moveTo(cx,cy-r);ctx.lineTo(cx,cy+r);ctx.stroke();ctx.globalAlpha=1;
   for(const [label,degrees] of [['N',0],['E',90],['S',180],['W',270]]){const angle=radians(degrees)-heading;ctx.fillText(label,cx+Math.sin(angle)*242,cy-Math.cos(angle)*242+6);}
   ctx.beginPath();ctx.arc(cx,cy,3,0,Math.PI*2);ctx.fill();
   const range=latest?.radius_nm||(15/1.150779448);ctx.font=(canvas.clientWidth<180?'24':'16')+'px "IBM Plex Mono", monospace';ctx.textAlign='right';ctx.fillText(Math.round(range*1.150779448)+' mi radius',464,468);
   if(Number.isFinite(latest?.camera_azimuth_deg)){const angle=0,x=cx+Math.sin(angle)*r,y=cy-Math.cos(angle)*r;ctx.save();ctx.setLineDash([8,7]);ctx.beginPath();ctx.moveTo(cx,cy);ctx.lineTo(x,y);ctx.stroke();ctx.restore();ctx.textAlign='left';ctx.font='20px \"IBM Plex Mono\", monospace';ctx.fillText('Camera '+latest.camera_azimuth_deg+'°',26,48);}
   if(latest?.center){
    const fontSize=canvas.clientWidth<180?25:18,marks=[],placed=[];
    ctx.font=fontSize+'px "IBM Plex Mono", monospace';
    for(const landmark of latest.landmarks||[]){const p=position(landmark,latest.center);if(p.distance>range)continue;
     marks.push({landmark,x:cx+Math.sin(p.bearing-heading)*p.distance/range*r,y:cy-Math.cos(p.bearing-heading)*p.distance/range*r});
    }
    const overlaps=(a,b)=>a.left<b.right&&a.right>b.left&&a.top<b.bottom&&a.bottom>b.top;
    for(const mark of marks){const {x,y,landmark}=mark,label=landmark.label.length>18?landmark.label.slice(0,17)+'…':landmark.label,w=ctx.measureText(label).width,h=fontSize*1.2;
     // Prefer centered below. Move only labels that collide, leaving all geographic markers fixed.
     let box=null;
     for(let gap=12;gap<=180&&!box;gap+=h+10){
      for(const [left,top] of [[x-w/2,y+gap],[x-w/2,y-gap-h],[x+gap,y-h/2],[x-gap-w,y-h/2]]){
       const candidate={left,right:left+w,top,bottom:top+h};
       if(left<10||candidate.right>510||top<60||candidate.bottom>450)continue;
       const padded={left:left-4,right:candidate.right+4,top:top-4,bottom:candidate.bottom+4};
       if(placed.some(v=>overlaps(padded,v))||marks.some(v=>overlaps(padded,{left:v.x-8,right:v.x+8,top:v.y-8,bottom:v.y+8})))continue;
       box=candidate;break;
      }
     }
     if(box){placed.push(box);ctx.save();
      if(box.left!==x-w/2||box.top!==y+12){
       const endX=Math.max(box.left,Math.min(box.right,x)),endY=Math.max(box.top,Math.min(box.bottom,y)),dx=endX-x,dy=endY-y,length=Math.hypot(dx,dy);
       ctx.globalAlpha=.6;ctx.lineWidth=1;ctx.beginPath();ctx.moveTo(x+dx/length*8,y+dy/length*8);ctx.lineTo(endX,endY);ctx.stroke();ctx.globalAlpha=1;
      }
      ctx.textAlign='center';ctx.textBaseline='top';ctx.fillText(label,(box.left+box.right)/2,box.top);ctx.restore();
     }
    }
    for(const {x,y,landmark} of marks){ctx.save();ctx.translate(x,y);ctx.rotate(Math.PI/4);ctx.strokeRect(-5,-5,10,10);ctx.restore();points.push({x,y,landmark});}

   }
   if(latest?.status!=='available')return;
   const now=Date.now()/1000;const fresh=(latest.aircraft||[]).filter(a=>now-a.position_epoch>=0&&now-a.position_epoch<=30);state.textContent=requestFailed?'Reconnecting…':now-latest.sampled_epoch>30?'Feed delayed':fresh.length+' aircraft';
   for(const a of latest.aircraft||[]){
    if(now-a.position_epoch>30||now<a.position_epoch)continue;
    const p=position(a,latest.center);if(p.distance>range)continue;
    const x=cx+Math.sin(p.bearing-heading)*p.distance/range*r,y=cy-Math.cos(p.bearing-heading)*p.distance/range*r;points.push({x,y,a});
    ctx.save();ctx.translate(x,y);if(canvas.clientWidth<180)ctx.scale(1.5,1.5);ctx.beginPath();
    if(Number.isFinite(a.track_deg)){ctx.rotate(radians(a.track_deg)-heading);ctx.moveTo(0,-9);ctx.lineTo(6,6);ctx.lineTo(0,3);ctx.lineTo(-6,6);ctx.closePath();}else ctx.arc(0,0,4,0,Math.PI*2);
    ctx.fill();ctx.restore();
   }
  }
  function showAt(event){const rect=canvas.getBoundingClientRect(),x=(event.clientX-rect.left)*520/rect.width,y=(event.clientY-rect.top)*520/rect.height;let hit=null,d=28;for(const p of points){const n=Math.hypot(p.x-x,p.y-y);if(n<d){hit=p;d=n;}}if(!hit){tip.hidden=true;return;}if(hit.landmark){tip.textContent=hit.landmark.label+' · '+hit.landmark.address;tip.hidden=false;return;}const a=hit.a;tip.textContent=[a.flight||a.r||a.hex,a.t,Number.isFinite(a.altitude_ft)?Math.round(a.altitude_ft).toLocaleString()+' ft':null,Number.isFinite(a.speed_knots)?Math.round(a.speed_knots)+' kt':null,Number.isFinite(a.track_deg)?Math.round(a.track_deg)+'° track':null].filter(Boolean).join(' · ');tip.hidden=false;}
  canvas.addEventListener('pointermove',showAt);canvas.addEventListener('click',showAt);canvas.addEventListener('pointerleave',()=>tip.hidden=true);
  async function refresh(){clearTimeout(timer);if(busy)return;busy=true;try{latest=await api('/api/air-traffic');requestFailed=false;state.textContent=latest.status==='available'?(latest.aircraft.length+' aircraft'):latest.status==='stale'?'Feed delayed':latest.status==='waiting'?'Updating center…':'Unavailable';center.textContent=latest.center?.resolved_address||latest.center?.address||'';center.title=center.textContent;canvas.setAttribute('aria-label',`${Number.isFinite(latest.camera_azimuth_deg)?'Camera-up':'North-up'} aircraft radar. ${state.textContent}. Arrows show reported ground track.`);}catch(e){requestFailed=true;state.textContent='Reconnecting…';}finally{busy=false;draw();timer=setTimeout(refresh,requestFailed?2500:5000);}}
  window.addEventListener('radar-center-changed',()=>{latest=null;draw();refresh();});document.addEventListener('visibilitychange',()=>{if(!document.hidden)refresh();});ink();refresh();setInterval(draw,1000);
 }
 const key=new URLSearchParams(location.search).get('id');
 if(key&&document.querySelector('#video')&&!viewer){
  const section=document.createElement('details');section.className='air-traffic-review';section.innerHTML='<summary>Air traffic at detection time</summary><p role="status">Loading…</p><div class="air-traffic-table"></div>';
  document.querySelector('#annotations')?.before(section);
  api('/api/air-traffic/detection?id='+encodeURIComponent(key)).then(data=>{
   const note=section.querySelector('p');if(data.status!=='available'){note.textContent=data.reason||'Air-traffic coverage unavailable for this detection.';return;}
   note.textContent=`${data.aircraft.length} reporting aircraft · ${new Date(data.sampled_epoch*1000).toISOString().replace('T',' ').replace('.000Z',' UTC')} · ${data.sample_offset_seconds??0}s before capture. Nearby traffic is context, not identification of the visual object.`;
   const table=document.createElement('table');const head=document.createElement('tr');for(const label of ['Aircraft','Type','Altitude','Speed','Track']){const th=document.createElement('th');th.textContent=label;head.append(th);}table.append(head);
   for(const a of data.aircraft){const row=document.createElement('tr');for(const value of [a.flight||a.r||a.hex,a.t||'—',Number.isFinite(a.altitude_ft)?a.altitude_ft.toLocaleString()+' ft':'—',Number.isFinite(a.speed_knots)?Math.round(a.speed_knots)+' kt':'—',Number.isFinite(a.track_deg)?Math.round(a.track_deg)+'°':'—']){const cell=document.createElement('td');cell.textContent=value;row.append(cell);}table.append(row);}
   section.querySelector('.air-traffic-table').append(table);const credit=document.createElement('a');credit.href='https://adsb.fi/';credit.textContent='Aircraft data: adsb.fi';credit.target='_blank';credit.rel='noopener noreferrer';section.append(credit);
  }).catch(()=>{section.querySelector('p').textContent='Air-traffic context unavailable. Reload to retry.';});
 }
})();
