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
 const css=document.createElement('link');css.rel='stylesheet';css.href='/air-traffic.css?v=1';document.head.append(css);
 const settings=document.querySelector('#stationSettings');
 if(settings){
  const area=document.createElement('div');area.className='air-traffic-settings';
  area.innerHTML='<label for="radarAddress">Radar center address</label><div class="radar-address-row"><input id="radarAddress" type="text" autocomplete="off" maxlength="250" placeholder="Address or landmark"></div><label for="radarRadius">Radar radius (miles)</label><div class="radar-address-row"><input id="radarRadius" type="number" min="1" max="100" step="1" value="15"><button id="radarAddressSave" type="button">Save</button></div><p id="radarAddressStatus" role="status"></p>';
  settings.insertBefore(area,settings.querySelector('#stationLocation'));
  const input=area.querySelector('#radarAddress'),radius=area.querySelector('#radarRadius'),button=area.querySelector('button'),status=area.querySelector('p');let dirty=false,busy=false;
  for(const control of [input,radius])control.addEventListener('input',()=>{dirty=true;status.textContent='';});
  async function load(){if(dirty||busy)return;try{const s=await api('/api/air-traffic/settings');input.value=s.address;radius.value=Math.round(s.radius_nm*1.150779448);}catch(e){status.textContent=e.message;}}
  document.querySelector('#stationSettingsOpen')?.addEventListener('click',load);
  async function save(){if(busy)return;busy=true;button.disabled=true;input.disabled=true;radius.disabled=true;status.textContent='Saving radar settings…';try{const s=await api('/api/air-traffic/settings',{address:input.value,radius_miles:Number(radius.value)});input.value=s.address;radius.value=Math.round(s.radius_nm*1.150779448);dirty=false;status.textContent='Saved · '+(s.resolved_address||s.address);window.dispatchEvent(new Event('radar-center-changed'));}catch(e){status.textContent=e.message;}finally{busy=false;button.disabled=false;input.disabled=false;radius.disabled=false;}}
  button.addEventListener('click',save);input.addEventListener('keydown',e=>{if(e.key==='Enter'){e.preventDefault();save();}});
 }
 const viewer=document.querySelector('#liveViewer');
 if(viewer){
  const panel=document.createElement('section');panel.className='air-radar';panel.setAttribute('aria-label','Nearby aircraft');
  panel.innerHTML='<div class="air-radar-heading"><span>Air traffic</span><span class="air-radar-state" role="status">Connecting…</span></div><div class="air-radar-stage"><canvas width="520" height="520" role="img" aria-label="North-up aircraft radar with direction-of-travel arrows"></canvas><div class="air-radar-tip" hidden></div></div><div class="air-radar-footer"><span class="air-radar-center"></span><a href="https://adsb.fi/" target="_blank" rel="noopener noreferrer">adsb.fi ↗</a></div>';
  viewer.append(panel);
  const canvas=panel.querySelector('canvas'),ctx=canvas.getContext('2d'),state=panel.querySelector('.air-radar-state'),center=panel.querySelector('.air-radar-center'),tip=panel.querySelector('.air-radar-tip');let latest=null,points=[],busy=false,timer;
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
   const color=getComputedStyle(panel).color,cx=260,cy=260,r=218;ctx.clearRect(0,0,520,520);ctx.strokeStyle=color;ctx.fillStyle=color;ctx.lineWidth=1.5;ctx.font=(canvas.clientWidth<180?'28':'19')+'px "IBM Plex Mono", monospace';ctx.textAlign='center';points=[];
   for(const fraction of [1/3,2/3,1]){ctx.globalAlpha=.32;ctx.beginPath();ctx.arc(cx,cy,r*fraction,0,Math.PI*2);ctx.stroke();}
   ctx.globalAlpha=.24;ctx.beginPath();ctx.moveTo(cx-r,cy);ctx.lineTo(cx+r,cy);ctx.moveTo(cx,cy-r);ctx.lineTo(cx,cy+r);ctx.stroke();ctx.globalAlpha=1;
   for(const [label,x,y] of [['N',cx,26],['E',502,cy+6],['S',cx,508],['W',18,cy+6]])ctx.fillText(label,x,y);
   ctx.beginPath();ctx.arc(cx,cy,3,0,Math.PI*2);ctx.fill();
   const range=latest?.radius_nm||(15/1.150779448);ctx.font=(canvas.clientWidth<180?'24':'16')+'px "IBM Plex Mono", monospace';ctx.textAlign='right';ctx.fillText(Math.round(range*1.150779448)+' mi',464,468);
   if(latest?.status!=='available')return;
   const now=Date.now()/1000;
   for(const a of latest.aircraft||[]){
    if(now-a.position_epoch>30)continue;
    const p=position(a,latest.center);if(p.distance>range)continue;
    const x=cx+Math.sin(p.bearing)*p.distance/range*r,y=cy-Math.cos(p.bearing)*p.distance/range*r;points.push({x,y,a});
    ctx.save();ctx.translate(x,y);if(canvas.clientWidth<180)ctx.scale(1.5,1.5);ctx.beginPath();
    if(Number.isFinite(a.track_deg)){ctx.rotate(radians(a.track_deg));ctx.moveTo(0,-9);ctx.lineTo(6,6);ctx.lineTo(0,3);ctx.lineTo(-6,6);ctx.closePath();}else ctx.arc(0,0,4,0,Math.PI*2);
    ctx.fill();ctx.restore();
   }
  }
  function showAt(event){const rect=canvas.getBoundingClientRect(),x=(event.clientX-rect.left)*520/rect.width,y=(event.clientY-rect.top)*520/rect.height;let hit=null,d=28;for(const p of points){const n=Math.hypot(p.x-x,p.y-y);if(n<d){hit=p;d=n;}}if(!hit){tip.hidden=true;return;}const a=hit.a;tip.textContent=[a.flight||a.r||a.hex,a.t,Number.isFinite(a.altitude_ft)?Math.round(a.altitude_ft).toLocaleString()+' ft':null,Number.isFinite(a.speed_knots)?Math.round(a.speed_knots)+' kt':null,Number.isFinite(a.track_deg)?Math.round(a.track_deg)+'° track':null].filter(Boolean).join(' · ');tip.hidden=false;}
  canvas.addEventListener('pointermove',showAt);canvas.addEventListener('click',showAt);canvas.addEventListener('pointerleave',()=>tip.hidden=true);
  async function refresh(){clearTimeout(timer);if(busy)return;busy=true;try{latest=await api('/api/air-traffic');state.textContent=latest.status==='available'?(latest.aircraft.length+' aircraft'):latest.status==='stale'?'Feed delayed':latest.status==='waiting'?'Updating center…':'Unavailable';center.textContent=(latest.center?.address||'').split(',')[0];center.title=latest.center?.address||'';canvas.setAttribute('aria-label',`North-up aircraft radar. ${state.textContent}. Arrows show reported ground track.`);}catch(e){latest=null;state.textContent='Unavailable';}finally{busy=false;draw();timer=setTimeout(refresh,15000);}}
  window.addEventListener('radar-center-changed',()=>{latest=null;draw();refresh();});document.addEventListener('visibilitychange',()=>{if(!document.hidden)refresh();});ink();refresh();setInterval(draw,5000);
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
