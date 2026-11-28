(()=>{
 'use strict';
 const viewer=document.querySelector('#liveViewer');
 if(viewer){
  const panel=document.createElement('section');panel.className='air-radar';panel.setAttribute('aria-label','Nearby aircraft');
  panel.innerHTML='<div class="air-radar-heading" style="align-items:flex-start"><div><span>Air traffic</span><div class="air-radar-camera" style="font-size:10px;margin-top:3px" hidden></div></div><div style="text-align:right"><span class="air-radar-state" role="status">Connecting…</span><div class="air-radar-fov-count" style="font-size:10px;margin-top:3px" title="Estimated aircraft inside both horizontal and vertical camera angles; not a visual identification." hidden></div></div></div><div class="air-radar-stage"><span class="air-radar-radius"></span><canvas width="520" height="520" role="img" aria-label="North-up aircraft radar with direction-of-travel arrows"></canvas><div class="air-radar-tip" hidden></div></div><canvas class="air-radar-side" width="520" height="300" role="img" aria-label="Side view of aircraft elevation and camera vertical field of view"></canvas><div class="air-radar-terrain" style="font-size:9px;margin:0 0 6px"><a href="https://open-meteo.com/en/docs/elevation-api" target="_blank" rel="noopener noreferrer" style="color:inherit" hidden>Terrain: Copernicus / Open-Meteo</a></div><div class="air-radar-footer"><span class="air-radar-center"></span><a href="https://adsb.fi/" target="_blank" rel="noopener noreferrer">adsb.fi ↗</a></div>';
  viewer.append(panel);
  const side=panel.querySelector('.air-radar-side'),sideCtx=side.getContext('2d');let sidePoints=[];
  const canvas=panel.querySelector('canvas'),ctx=canvas.getContext('2d'),state=panel.querySelector('.air-radar-state'),center=panel.querySelector('.air-radar-center'),tip=panel.querySelector('.air-radar-tip'),fovCount=panel.querySelector('.air-radar-fov-count'),cameraInfo=panel.querySelector('.air-radar-camera');let latest=null,points=[],requestFailed=false;
  const rf=document.querySelector('#rfOverlay');
  const column=document.createElement('div');column.id='liveTelemetry';viewer.append(column);if(rf)column.append(rf);column.append(panel);
  if(rf){const controls=document.createElement('div');controls.className='rf-overlay rf-controls-column';viewer.append(controls);const placeControls=()=>{const header=document.querySelector('.station-header');const divider=document.querySelector('.station-page-title');if(divider)controls.style.width=Math.max(140,divider.getBoundingClientRect().left-controls.getBoundingClientRect().left)+'px';controls.style.top=Math.max(12,Math.max(header?.getBoundingClientRect().bottom||48,window.innerWidth<=600?(document.querySelector('#liveStatus')?.getBoundingClientRect().bottom||0):0)-viewer.getBoundingClientRect().top+12)+'px';};placeControls();const header=document.querySelector('.station-header');if(header){const observer=new ResizeObserver(placeControls);observer.observe(header);const brand=header.querySelector('.station-brand');if(brand)observer.observe(brand);}document.fonts?.ready.then(placeControls);window.addEventListener('resize',placeControls);const groupControls=()=>{for(const child of [...rf.children])if(child!==controls&&!child.matches('.rf-heading,canvas'))controls.append(child);};groupControls();new MutationObserver(groupControls).observe(rf,{childList:true});}
  function ink(){const color=rf?.style.color||'#fff';panel.style.color=color;const controls=viewer.querySelector('.rf-controls-column');if(controls)controls.style.color=color;draw();}
  if(rf)new MutationObserver(ink).observe(rf,{attributes:true,attributeFilter:['style']});
  const radians=n=>n*Math.PI/180;
  function aircraftView(a,fov){
   const p=a,delta=Math.atan2(Math.sin(p.bearing-radians(latest.camera_azimuth_deg||0)),Math.cos(p.bearing-radians(latest.camera_azimuth_deg||0)));
   const result={...p,inBearing:Number.isFinite(latest.camera_azimuth_deg)&&Math.abs(delta)<=radians(fov.azimuth_span_deg/2),inFov:null,elevation:null,height:null};
   const station=latest.station_elevation?.camera_altitude_ft;
   if(!Number.isFinite(station)||!Number.isFinite(a.altitude_ft))return result;
   const arc=p.distance/3440.065,earth=3440.065*6076.11549,horizontal=(earth+a.altitude_ft)*Math.sin(arc),height=(earth+a.altitude_ft)*Math.cos(arc)-(earth+station),elevation=Math.atan2(height,horizontal);
   result.height=height;result.elevation=elevation*180/Math.PI;
   if(!Number.isFinite(latest.camera_azimuth_deg)||!Number.isFinite(fov.elevation_deg))return result;
   const pitch=radians(fov.elevation_deg),ce=Math.cos(elevation),se=Math.sin(elevation),forward=ce*Math.cos(delta)*Math.cos(pitch)+se*Math.sin(pitch),right=ce*Math.sin(delta),up=se*Math.cos(pitch)-ce*Math.cos(delta)*Math.sin(pitch);
   result.inFov=forward>0&&Math.abs(right)<=forward*Math.tan(radians(fov.horizontal_deg/2))&&Math.abs(up)<=forward*Math.tan(radians(fov.vertical_deg/2));return result;
  }
  function drawSide(fov,rows,range,color,fresh){
   const height=Math.max(300,Math.round(side.clientHeight/Math.max(1,side.clientWidth)*520));if(side.height!==height)side.height=height;const c=sideCtx,x0=0,y0=(canvas.getBoundingClientRect().top+canvas.clientWidth*519/520-side.getBoundingClientRect().top)*520/Math.max(1,side.clientWidth),w=519,top=(canvas.getBoundingClientRect().top+canvas.clientWidth/520-side.getBoundingClientRect().top)*520/Math.max(1,side.clientWidth),scale=w/range,yScale=(y0-top)/40000,aspect=yScale*6076.11549/scale;sidePoints=[];c.clearRect(0,0,520,height);c.strokeStyle=c.fillStyle=color;c.lineWidth=1.5;c.font=(canvas.clientWidth<180?'28':'20')+'px "IBM Plex Mono",monospace';c.textAlign='left';c.fillText('Side view',0,23);c.textAlign='left';c.font=(canvas.clientWidth<180?'24':'18')+'px "IBM Plex Mono",monospace';c.fillText(Number.isFinite(fov?.elevation_deg)?fov.elevation_deg+'° ↑ · '+fov.vertical_deg.toFixed(1)+'° FoV':'Elevation unavailable',0,51);
   c.globalAlpha=1;for(const fraction of [.5,1]){const y=y0-(y0-top)*fraction;c.beginPath();c.moveTo(x0,y);c.lineTo(x0+w,y);c.stroke();c.textAlign='left';c.font=(canvas.clientWidth<180?'24':'16')+'px "IBM Plex Mono",monospace';c.fillText(Math.round((y0-y)/yScale/1000)+'k ft',x0+4,y-5);}c.globalAlpha=1;
   c.beginPath();c.moveTo(x0,top);c.lineTo(x0,y0);c.lineTo(x0+w,y0);c.stroke();c.textAlign='left';c.fillText('0',x0,y0+24);c.textAlign='right';c.fillText(Math.round(range*1.150779448)+' mi',x0+w,y0+24);
   if(Number.isFinite(fov?.elevation_deg)){const pitch=radians(fov.elevation_deg),half=radians(fov.vertical_deg/2);c.save();c.beginPath();c.rect(x0,top,w,y0-top);c.clip();c.beginPath();c.moveTo(x0,y0);for(const angle of [pitch-half,pitch+half])c.lineTo(x0+Math.cos(angle)*5000,y0-Math.sin(angle)*5000*aspect);c.closePath();c.globalAlpha=.12;c.fill();c.globalAlpha=.7;c.stroke();c.setLineDash([5,5]);c.beginPath();c.moveTo(x0,y0);c.lineTo(x0+Math.cos(pitch)*5000,y0-Math.sin(pitch)*5000*aspect);c.stroke();c.restore();}
   for(const row of rows){const v=row.view;if(!v.inBearing||v.height===null)continue;const x=x0+v.distance*scale,y=y0-v.height*yScale;if(y<top||y>y0||x>x0+w)continue;c.beginPath();c.arc(x,y,v.inFov?5:3,0,Math.PI*2);c.fill();if(v.inFov)c.strokeRect(x-9,y-9,18,18);sidePoints.push({x,y,a:row.a,view:v});}
   c.beginPath();c.arc(x0,y0,3,0,2*Math.PI);c.fill();
   let note=!fresh?'Aircraft data unavailable':!Number.isFinite(latest?.station_elevation?.camera_altitude_ft)?'Station elevation unavailable':!Number.isFinite(latest?.camera_azimuth_deg)?'Bearing unavailable':null;
   if(note){c.textAlign='center';c.font='18px "IBM Plex Mono",monospace';c.fillText(note,250,155);}
   panel.querySelector('.air-radar-terrain a').hidden=latest?.station_elevation?.source!=='Copernicus / Open-Meteo';
   side.title='Estimated height above the camera. Only aircraft in the horizontal bearing wedge are shown. Reported pressure altitude, terrain elevation; no terrain occlusion correction.';
  }
  function draw(){
   fovCount.hidden=true;cameraInfo.hidden=true;
   const fov=latest?.camera_fov;
   const heading=Number.isFinite(latest?.camera_azimuth_deg)?radians(latest.camera_azimuth_deg):0;
   const color=getComputedStyle(panel).color,cx=260,cy=260,r=259;ctx.clearRect(0,0,520,520);ctx.strokeStyle=color;ctx.fillStyle=color;ctx.lineWidth=1.5;ctx.font=(canvas.clientWidth<180?'28':'19')+'px "IBM Plex Mono", monospace';ctx.textAlign='center';points=[];
   if(Number.isFinite(latest?.camera_azimuth_deg)&&Number.isFinite(fov?.azimuth_span_deg)){
    const half=radians(fov.azimuth_span_deg/2),start=-Math.PI/2-half,end=-Math.PI/2+half;
    ctx.save();ctx.beginPath();ctx.moveTo(cx,cy);ctx.arc(cx,cy,r,start,end);ctx.closePath();ctx.globalAlpha=.12;ctx.fill();ctx.globalAlpha=.55;ctx.stroke();ctx.restore();
   }
   for(const fraction of [1/3,2/3,1]){ctx.globalAlpha=.32;ctx.beginPath();ctx.arc(cx,cy,r*fraction,0,Math.PI*2);ctx.stroke();}
   ctx.globalAlpha=.24;ctx.beginPath();ctx.moveTo(cx-r,cy);ctx.lineTo(cx+r,cy);ctx.moveTo(cx,cy-r);ctx.lineTo(cx,cy+r);ctx.stroke();ctx.globalAlpha=1;
   for(const [label,degrees] of [['N',0],['E',90],['S',180],['W',270]]){const angle=radians(degrees)-heading;ctx.fillText(label,cx+Math.sin(angle)*242,cy-Math.cos(angle)*242+6);}
   ctx.beginPath();ctx.arc(cx,cy,3,0,Math.PI*2);ctx.fill();
   const range=latest?.radius_nm||(15/1.150779448);ctx.font=(canvas.clientWidth<180?'24':'16')+'px "IBM Plex Mono", monospace';panel.querySelector('.air-radar-radius').textContent=Math.round(range*1.150779448)+' mi radius';
   if(Number.isFinite(latest?.camera_azimuth_deg)){const angle=0,x=cx+Math.sin(angle)*r,y=cy-Math.cos(angle)*r;ctx.save();ctx.setLineDash([8,7]);ctx.beginPath();ctx.moveTo(cx,cy);ctx.lineTo(x,y);ctx.stroke();ctx.restore();ctx.textAlign='left';ctx.font='20px \"IBM Plex Mono\", monospace';cameraInfo.textContent='Camera '+latest.camera_azimuth_deg+'°'+(fov?' · '+fov.focal_length_mm+' mm':'');cameraInfo.hidden=false;}
   if(!['available','stale'].includes(latest?.status)){drawSide(fov,[],range,color,false);return;}
   const now=latest.sampled_epoch;const fresh=(latest.aircraft||[]).filter(a=>now-a.position_epoch>=0&&now-a.position_epoch<=30);state.textContent=fresh.length+' aircraft';
   const rows=fov?fresh.map(a=>({a,view:aircraftView(a,fov)})).filter(r=>r.view.distance<=range):[];
   drawSide(fov,rows,range,color,now-latest.sampled_epoch<=30);
   if(!requestFailed&&now-latest.sampled_epoch<=30&&Number.isFinite(latest.camera_azimuth_deg)&&fov){const known=Number.isFinite(latest.station_elevation?.camera_altitude_ft)&&Number.isFinite(fov.elevation_deg),count=rows.filter(r=>r.view.inFov).length,unknown=rows.filter(r=>r.view.inBearing&&r.view.inFov===null).length;fovCount.textContent=known?(count+' in Field of View'+(unknown?' · '+unknown+' unknown':'')):'FoV unavailable';fovCount.hidden=false;}

   for(const a of latest.aircraft||[]){
    if(now-a.position_epoch>30||now<a.position_epoch)continue;
    const p=a;if(p.distance>range)continue;
    const x=cx+Math.sin(p.bearing-heading)*p.distance/range*r,y=cy-Math.cos(p.bearing-heading)*p.distance/range*r;points.push({x,y,a});
    ctx.save();ctx.translate(x,y);if(canvas.clientWidth<180)ctx.scale(1.5,1.5);ctx.beginPath();
    if(Number.isFinite(a.track_deg)){ctx.rotate(radians(a.track_deg)-heading);ctx.moveTo(0,-9);ctx.lineTo(6,6);ctx.lineTo(0,3);ctx.lineTo(-6,6);ctx.closePath();}else ctx.arc(0,0,4,0,Math.PI*2);
    ctx.fill();if(fov&&aircraftView(a,fov).inFov)ctx.strokeRect(-13,-13,26,26);ctx.restore();
   }
  }
  function showAt(event){const rect=canvas.getBoundingClientRect(),x=(event.clientX-rect.left)*520/rect.width,y=(event.clientY-rect.top)*520/rect.height;let hit=null,d=28;for(const p of points){const n=Math.hypot(p.x-x,p.y-y);if(n<d){hit=p;d=n;}}if(!hit){tip.hidden=true;return;}if(hit.landmark){tip.textContent=hit.landmark.label+' · '+hit.landmark.address;tip.hidden=false;return;}const a=hit.a;tip.textContent=[a.t||'Aircraft',Number.isFinite(a.altitude_ft)?Math.round(a.altitude_ft).toLocaleString()+' ft':null,Number.isFinite(a.speed_knots)?Math.round(a.speed_knots)+' kt':null,Number.isFinite(a.track_deg)?Math.round(a.track_deg)+'° track':null].filter(Boolean).join(' · ');tip.hidden=false;}
  side.addEventListener('pointermove',event=>{const rect=side.getBoundingClientRect(),x=(event.clientX-rect.left)*520/rect.width,y=(event.clientY-rect.top)*300/rect.height,hit=sidePoints.find(p=>Math.hypot(p.x-x,p.y-y)<18);tip.hidden=!hit;if(hit)tip.textContent=[hit.a.t||'Aircraft',Math.round(hit.a.altitude_ft).toLocaleString()+' ft reported',hit.view.elevation.toFixed(1)+'° elevation',hit.view.inFov?'Inside estimated FoV':'Outside vertical FoV'].join(' · ');});side.addEventListener('pointerleave',()=>tip.hidden=true);
  canvas.addEventListener('pointermove',showAt);canvas.addEventListener('click',showAt);canvas.addEventListener('pointerleave',()=>tip.hidden=true);
  async function loadSample(){
   try{
    const response=await fetch('/snapshot/radar.json');
    if(!response.ok)throw Error();
    latest=await response.json();
    state.textContent='Unavailable';
    if(latest.sampled_epoch){
     const sampled=new Date(latest.sampled_epoch*1000);
     center.textContent=(latest.status==='stale'?'Delayed sample · ':'Radar snapshot · ')+sampled.toLocaleTimeString([], {hour:'numeric',minute:'2-digit'});
     center.title=sampled.toLocaleString();
    }
   }catch{state.textContent='Unavailable';}
   draw();
  }
  new ResizeObserver(draw).observe(panel);
  ink();loadSample();
 }
})();
