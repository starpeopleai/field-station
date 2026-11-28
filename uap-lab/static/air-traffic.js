/* Private aircraft context: no radar centers or provider data in public snapshots. */
(()=>{
 'use strict';
 if(window.FIELD_PUBLIC_READ_ONLY===true)return;
 let token='', tokenAt=0,previewOptics=null;
 function cameraFov(focal,elevation){
  const h=22.3/(2*focal),v=h*9/16,pitch=(Number.isFinite(elevation)?elevation:0)*Math.PI/180,forward=Math.cos(pitch)-Math.abs(Math.sin(pitch))*v;
  return {focal_length_mm:focal,horizontal_deg:2*Math.atan(h)*180/Math.PI,vertical_deg:2*Math.atan(v)*180/Math.PI,azimuth_span_deg:forward<=0?360:2*Math.atan2(h,forward)*180/Math.PI,elevation_deg:elevation};
 }

 async function api(path,body){
  if(!token||Date.now()-tokenAt>60000){const r=await fetch('/api/labeled-frames/token',{cache:'no-store',signal:AbortSignal.timeout(8000)});if(!r.ok)throw Error('Station unavailable');token=(await r.json()).token;tokenAt=Date.now();}
  const r=await fetch(path,{method:body?'POST':'GET',headers:{'X-Lab-Token':token,...(body?{'Content-Type':'application/json'}:{})},...(body?{body:JSON.stringify(body)}:{}),cache:'no-store',signal:AbortSignal.timeout(12000)});
  if(r.status===403){token='';throw Error('Reconnecting to station');}const v=await r.json();if(!r.ok)throw Error(v.error||'Air traffic unavailable');return v;
 }
 const css=document.createElement('link');css.rel='stylesheet';css.href='/air-traffic.css?v=26';document.head.append(css);
 const settings=document.querySelector('#stationSettings');
 if(settings){
  const area=document.createElement('div');area.className='air-traffic-settings';
  area.innerHTML='<label for="radarAddress">Radar center address</label><div class="radar-address-row"><input id="radarAddress" type="text" autocomplete="off" maxlength="250" placeholder="Address or latitude, longitude" aria-describedby="radarResolvedAddress"></div><p id="radarResolvedAddress"></p><label for="radarRadius">Radar radius (miles)</label><div class="radar-address-row"><input id="radarRadius" type="number" min="1" max="100" step="1" value="15"></div><label for="cameraAzimuth">Camera azimuth (° true)</label><div class="radar-address-row"><input id="cameraAzimuth" type="number" min="0" max="359.9" step="0.1" placeholder="Not set" aria-describedby="cameraAzimuthHelp"></div><p id="cameraAzimuthHelp">0° N · 90° E · 180° S · 270° W</p><label for="cameraElevation">Camera elevation (°)</label><div class="radar-address-row"><input id="cameraElevation" type="number" min="-90" max="90" step="0.1" placeholder="Not set" aria-describedby="cameraElevationHelp"></div><p id="cameraElevationHelp">0° horizon · 90° straight up · negative below horizon</p><label for="stationGroundAltitude">Station ground altitude (ft above sea level)</label><div class="radar-address-row"><input id="stationGroundAltitude" type="number" min="-1500" max="30000" step="1" placeholder="Automatic terrain lookup"></div><label for="cameraHeight">Camera height above ground (ft)</label><div class="radar-address-row"><input id="cameraHeight" type="number" min="0" max="2000" step="0.1" value="0"></div><p>Leave altitude blank for automatic lookup. Aircraft elevation is estimated from reported pressure altitude; terrain and atmospheric effects can affect visibility.</p><label for="cameraFovZoom">FoV Zoom</label><input id="cameraFovZoom" type="range" min="100" max="400" step="1" value="100" aria-describedby="cameraFovValue cameraFovHelp" style="width:100%;margin:4px 0;accent-color:var(--ink)"><div style="display:flex;justify-content:space-between;font-size:11px"><span>Wider · 100 mm</span><span>Telephoto · 400 mm</span></div><canvas id="cameraFovPreview" width="320" height="160" style="display:block;width:100%;max-width:320px;height:auto;margin:12px auto 4px" role="img" aria-label="Camera field-of-view preview"></canvas><output id="cameraFovValue" style="display:block;font-size:11px;margin-bottom:12px"></output><div class="radar-address-row"><input id="cameraFocalLength" type="number" min="100" max="400" step="1" value="100" aria-label="Lens focal length in millimeters" aria-describedby="cameraFovHelp"><button id="radarAddressSave" type="button">Save</button></div><p id="cameraFovHelp">Estimated R100 field of view at 1080p. Assumes no additional camera crop. The wedge shows viewing direction, not aircraft identification.</p><p id="radarAddressStatus" role="status"></p>';
  settings.insertBefore(area,settings.querySelector('#stationLocation'));
  const input=area.querySelector('#radarAddress'),radius=area.querySelector('#radarRadius'),azimuth=area.querySelector('#cameraAzimuth'),elevation=area.querySelector('#cameraElevation'),ground=area.querySelector('#stationGroundAltitude'),height=area.querySelector('#cameraHeight'),focal=area.querySelector('#cameraFocalLength'),button=area.querySelector('#radarAddressSave'),status=area.querySelector('#radarAddressStatus');let dirty=false,busy=false;
  const zoom=area.querySelector('#cameraFovZoom'),opticsCanvas=area.querySelector('#cameraFovPreview'),opticsValue=area.querySelector('#cameraFovValue');
  function opticsPreview(live=false){
   const value=Number(focal.value);if(!Number.isFinite(value)||value<100||value>400)return;
   zoom.value=value;const optics=cameraFov(value,elevation.value.trim()===''?null:Number(elevation.value)),c=opticsCanvas.getContext('2d'),half=optics.azimuth_span_deg*Math.PI/360;
   c.clearRect(0,0,320,160);c.strokeStyle=c.fillStyle=getComputedStyle(area).color;c.lineWidth=1.5;
   const cy=optics.azimuth_span_deg>180?80:148,r=optics.azimuth_span_deg>180?68:130;
   c.globalAlpha=.2;for(const radius of [r/2,r]){c.beginPath();c.arc(160,cy,radius,optics.azimuth_span_deg>180?0:Math.PI,2*Math.PI);c.stroke();}
   c.beginPath();c.moveTo(160,cy);c.arc(160,cy,r,-Math.PI/2-half,-Math.PI/2+half);c.closePath();c.globalAlpha=.14;c.fill();c.globalAlpha=1;c.stroke();c.beginPath();c.arc(160,cy,3,0,Math.PI*2);c.fill();
   opticsValue.textContent=value+' mm · '+optics.horizontal_deg.toFixed(1)+'° wide × '+optics.vertical_deg.toFixed(1)+'° tall';opticsCanvas.setAttribute('aria-label',opticsValue.textContent);
   if(live){previewOptics=optics;window.dispatchEvent(new Event('camera-fov-preview'));}
  }
  zoom.addEventListener('input',()=>{focal.value=zoom.value;dirty=true;status.textContent='';opticsPreview(true);});
  for(const control of [focal,elevation])control.addEventListener('input',()=>opticsPreview(true));
  settings.addEventListener('close',()=>{previewOptics=null;window.dispatchEvent(new Event('camera-fov-preview'));});

  for(const control of [input,radius,azimuth,elevation,focal,ground,height])control.addEventListener('input',()=>{dirty=true;status.textContent='';});
  async function load(){if(dirty||busy)return;try{const s=await api('/api/air-traffic/settings');input.value=s.address;area.querySelector('#radarResolvedAddress').textContent=s.resolved_address||s.address;radius.value=Math.round(s.radius_nm*1.150779448);azimuth.value=s.camera_azimuth_deg??'';elevation.value=s.camera_elevation_deg??'';ground.value=s.station_altitude_ft??'';height.value=s.camera_height_ft??0;focal.value=s.camera_focal_length_mm??100;opticsPreview();renderLandmarks(s.landmarks);}catch(e){status.textContent=e.message;}}
  document.querySelector('#stationSettingsOpen')?.addEventListener('click',load);
  async function save(){if(busy)return;busy=true;button.disabled=true;input.disabled=true;radius.disabled=true;azimuth.disabled=true;elevation.disabled=true;ground.disabled=true;height.disabled=true;focal.disabled=true;zoom.disabled=true;status.textContent='Saving radar settings…';try{const s=await api('/api/air-traffic/settings',{address:input.value,radius_miles:Number(radius.value),camera_azimuth_deg:azimuth.value.trim()===''?null:Number(azimuth.value),camera_elevation_deg:elevation.value.trim()===''?null:Number(elevation.value),camera_focal_length_mm:Number(focal.value),station_altitude_ft:ground.value.trim()===''?null:Number(ground.value),camera_height_ft:Number(height.value)});input.value=s.address;area.querySelector('#radarResolvedAddress').textContent=s.resolved_address||s.address;radius.value=Math.round(s.radius_nm*1.150779448);azimuth.value=s.camera_azimuth_deg??'';elevation.value=s.camera_elevation_deg??'';ground.value=s.station_altitude_ft??'';height.value=s.camera_height_ft??0;focal.value=s.camera_focal_length_mm??100;opticsPreview();renderLandmarks(s.landmarks);previewOptics=null;dirty=false;status.textContent='Saved · '+(s.resolved_address||s.address);window.dispatchEvent(new Event('radar-center-changed'));}catch(e){status.textContent=e.message;}finally{busy=false;button.disabled=false;input.disabled=false;radius.disabled=false;azimuth.disabled=false;elevation.disabled=false;ground.disabled=false;height.disabled=false;focal.disabled=false;zoom.disabled=false;}}
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
  panel.innerHTML='<div class="air-radar-heading" style="align-items:flex-start"><div><span>Air traffic</span><div class="air-radar-camera" style="font-size:10px;margin-top:3px" hidden></div></div><div style="text-align:right"><span class="air-radar-state" role="status">Connecting…</span><div class="air-radar-fov-count" style="font-size:10px;margin-top:3px" title="Estimated aircraft inside both horizontal and vertical camera angles; not a visual identification." hidden></div></div></div><div class="air-radar-stage"><span class="air-radar-radius"></span><canvas width="520" height="520" role="img" aria-label="North-up aircraft radar with direction-of-travel arrows"></canvas><div class="air-radar-tip" hidden></div></div><canvas class="air-radar-side" width="520" height="300" role="img" aria-label="Side view of aircraft elevation and camera vertical field of view"></canvas><div class="air-radar-terrain" style="font-size:9px;margin:0 0 6px"><a href="https://open-meteo.com/en/docs/elevation-api" target="_blank" rel="noopener noreferrer" style="color:inherit" hidden>Terrain: Copernicus / Open-Meteo</a></div><div class="air-radar-footer"><span class="air-radar-center"></span><a href="https://adsb.fi/" target="_blank" rel="noopener noreferrer">adsb.fi ↗</a></div>';
  viewer.append(panel);
  const side=panel.querySelector('.air-radar-side'),sideCtx=side.getContext('2d');let sidePoints=[];
  const canvas=panel.querySelector('canvas'),ctx=canvas.getContext('2d'),state=panel.querySelector('.air-radar-state'),center=panel.querySelector('.air-radar-center'),tip=panel.querySelector('.air-radar-tip'),fovCount=panel.querySelector('.air-radar-fov-count'),cameraInfo=panel.querySelector('.air-radar-camera');let latest=null,points=[],busy=false,timer,requestFailed=false;
  const rf=document.querySelector('#rfOverlay');
  const column=document.createElement('div');column.id='liveTelemetry';viewer.append(column);if(rf)column.append(rf);column.append(panel);
  if(rf){const controls=document.createElement('div');controls.className='rf-overlay rf-controls-column';viewer.append(controls);const placeControls=()=>{const header=document.querySelector('.station-header');const divider=document.querySelector('.station-page-title');if(divider)controls.style.width=Math.max(140,divider.getBoundingClientRect().left-controls.getBoundingClientRect().left)+'px';controls.style.top=Math.max(12,Math.max(header?.getBoundingClientRect().bottom||48,window.innerWidth<=600?(document.querySelector('#liveStatus')?.getBoundingClientRect().bottom||0):0)-viewer.getBoundingClientRect().top+12)+'px';};placeControls();const header=document.querySelector('.station-header');if(header){const observer=new ResizeObserver(placeControls);observer.observe(header);const brand=header.querySelector('.station-brand');if(brand)observer.observe(brand);}document.fonts?.ready.then(placeControls);window.addEventListener('resize',placeControls);const groupControls=()=>{for(const child of [...rf.children])if(child!==controls&&!child.matches('.rf-heading,canvas'))controls.append(child);};groupControls();new MutationObserver(groupControls).observe(rf,{childList:true});}
  function ink(){const color=rf?.style.color||'#fff';panel.style.color=color;const controls=viewer.querySelector('.rf-controls-column');if(controls)controls.style.color=color;draw();}
  if(rf)new MutationObserver(ink).observe(rf,{attributes:true,attributeFilter:['style']});
  const radians=n=>n*Math.PI/180;
  function position(a,c){
   const p1=radians(c.latitude),p2=radians(a.latitude),dl=radians(a.longitude-c.longitude),dp=p2-p1;
   const h=Math.sin(dp/2)**2+Math.cos(p1)*Math.cos(p2)*Math.sin(dl/2)**2;
   const distance=3440.065*2*Math.atan2(Math.sqrt(h),Math.sqrt(Math.max(0,1-h)));
   const bearing=Math.atan2(Math.sin(dl)*Math.cos(p2),Math.cos(p1)*Math.sin(p2)-Math.sin(p1)*Math.cos(p2)*Math.cos(dl));return {distance,bearing};
  }
  function aircraftView(a,fov){
   const p=position(a,latest.center),delta=Math.atan2(Math.sin(p.bearing-radians(latest.camera_azimuth_deg||0)),Math.cos(p.bearing-radians(latest.camera_azimuth_deg||0)));
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
   const height=Math.max(300,Math.round(side.clientHeight/Math.max(1,side.clientWidth)*520));if(side.height!==height)side.height=height;const c=sideCtx,x0=0,y0=(canvas.getBoundingClientRect().top+canvas.clientWidth*519/520-side.getBoundingClientRect().top)*520/Math.max(1,side.clientWidth),w=519,top=(canvas.getBoundingClientRect().top+canvas.clientWidth/520-side.getBoundingClientRect().top)*520/Math.max(1,side.clientWidth),scale=w/range,yScale=(y0-top)/40000,aspect=yScale*6076.11549/scale;sidePoints=[];c.clearRect(0,0,520,height);c.strokeStyle=c.fillStyle=color;c.lineWidth=1.5;c.font=(canvas.clientWidth<180?'28':'20')+'px "IBM Plex Mono",monospace';c.textAlign='left';c.fillText('Side view',0,23);c.textAlign='left';c.font=(canvas.clientWidth<180?'24':'18')+'px "IBM Plex Mono",monospace';c.fillText(Number.isFinite(fov?.elevation_deg)?fov.elevation_deg+'° ↑ · '+fov.vertical_deg.toFixed(1)+'° FoV':'Set camera elevation',0,51);
   c.globalAlpha=1;for(const fraction of [.5,1]){const y=y0-(y0-top)*fraction;c.beginPath();c.moveTo(x0,y);c.lineTo(x0+w,y);c.stroke();c.textAlign='left';c.font=(canvas.clientWidth<180?'24':'16')+'px "IBM Plex Mono",monospace';c.fillText(Math.round((y0-y)/yScale/1000)+'k ft',x0+4,y-5);}c.globalAlpha=1;
   c.beginPath();c.moveTo(x0,top);c.lineTo(x0,y0);c.lineTo(x0+w,y0);c.stroke();c.textAlign='left';c.fillText('0',x0,y0+24);c.textAlign='right';c.fillText(Math.round(range*1.150779448)+' mi',x0+w,y0+24);
   if(Number.isFinite(fov?.elevation_deg)){const pitch=radians(fov.elevation_deg),half=radians(fov.vertical_deg/2);c.save();c.beginPath();c.rect(x0,top,w,y0-top);c.clip();c.beginPath();c.moveTo(x0,y0);for(const angle of [pitch-half,pitch+half])c.lineTo(x0+Math.cos(angle)*5000,y0-Math.sin(angle)*5000*aspect);c.closePath();c.globalAlpha=.12;c.fill();c.globalAlpha=.7;c.stroke();c.setLineDash([5,5]);c.beginPath();c.moveTo(x0,y0);c.lineTo(x0+Math.cos(pitch)*5000,y0-Math.sin(pitch)*5000*aspect);c.stroke();c.restore();}
   for(const row of rows){const v=row.view;if(!v.inBearing||v.height===null)continue;const x=x0+v.distance*scale,y=y0-v.height*yScale;if(y<top||y>y0||x>x0+w)continue;c.beginPath();c.arc(x,y,v.inFov?5:3,0,Math.PI*2);c.fill();if(v.inFov)c.strokeRect(x-9,y-9,18,18);sidePoints.push({x,y,a:row.a,view:v});}
   c.beginPath();c.arc(x0,y0,3,0,2*Math.PI);c.fill();
   let note=!fresh?'Awaiting fresh aircraft data':!Number.isFinite(latest?.station_elevation?.camera_altitude_ft)?'Station elevation unavailable':!Number.isFinite(latest?.camera_azimuth_deg)?'Set camera azimuth':null;
   if(note){c.textAlign='center';c.font='18px "IBM Plex Mono",monospace';c.fillText(note,250,155);}
   panel.querySelector('.air-radar-terrain a').hidden=latest?.station_elevation?.source!=='Copernicus / Open-Meteo';
   side.title='Estimated height above the camera. Only aircraft in the horizontal bearing wedge are shown. Reported pressure altitude, terrain elevation; no terrain occlusion correction.';
  }
  function draw(){
   fovCount.hidden=true;cameraInfo.hidden=true;
   const fov=previewOptics||latest?.camera_fov;
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
   if(latest?.status!=='available'){drawSide(fov,[],range,color,false);return;}
   const now=Date.now()/1000;const fresh=(latest.aircraft||[]).filter(a=>now-a.position_epoch>=0&&now-a.position_epoch<=30);state.textContent=requestFailed?'Reconnecting…':now-latest.sampled_epoch>30?'Feed delayed':fresh.length+' aircraft'+(latest.faa_live?' · FAA '+fresh.filter(a=>a.faa).length:'');
   const rows=fov?fresh.map(a=>({a,view:aircraftView(a,fov)})).filter(r=>r.view.distance<=range):[];
   drawSide(fov,rows,range,color,now-latest.sampled_epoch<=30);
   if(!requestFailed&&now-latest.sampled_epoch<=30&&Number.isFinite(latest.camera_azimuth_deg)&&fov){const known=Number.isFinite(latest.station_elevation?.camera_altitude_ft)&&Number.isFinite(fov.elevation_deg),count=rows.filter(r=>r.view.inFov).length,unknown=rows.filter(r=>r.view.inBearing&&r.view.inFov===null).length;fovCount.textContent=known?(count+' in Field of View'+(unknown?' · '+unknown+' unknown':'')):'FoV unavailable';fovCount.hidden=false;}

   for(const a of latest.aircraft||[]){
    if(now-a.position_epoch>30||now<a.position_epoch)continue;
    const p=position(a,latest.center);if(p.distance>range)continue;
    const x=cx+Math.sin(p.bearing-heading)*p.distance/range*r,y=cy-Math.cos(p.bearing-heading)*p.distance/range*r;points.push({x,y,a});
    ctx.save();ctx.translate(x,y);if(canvas.clientWidth<180)ctx.scale(1.5,1.5);ctx.beginPath();
    if(Number.isFinite(a.track_deg)){ctx.rotate(radians(a.track_deg)-heading);ctx.moveTo(0,-9);ctx.lineTo(6,6);ctx.lineTo(0,3);ctx.lineTo(-6,6);ctx.closePath();}else ctx.arc(0,0,4,0,Math.PI*2);
    ctx.fill();if(fov&&aircraftView(a,fov).inFov)ctx.strokeRect(-13,-13,26,26);ctx.restore();
   }
  }
  function showAt(event){const rect=canvas.getBoundingClientRect(),x=(event.clientX-rect.left)*520/rect.width,y=(event.clientY-rect.top)*520/rect.height;let hit=null,d=28;for(const p of points){const n=Math.hypot(p.x-x,p.y-y);if(n<d){hit=p;d=n;}}if(!hit){tip.hidden=true;return;}if(hit.landmark){tip.textContent=hit.landmark.label+' · '+hit.landmark.address;tip.hidden=false;return;}const a=hit.a;tip.textContent=[a.faa?'FAA':null,a.flight||a.r||a.hex,a.t,Number.isFinite(a.altitude_ft)?Math.round(a.altitude_ft).toLocaleString()+' ft':null,Number.isFinite(a.speed_knots)?Math.round(a.speed_knots)+' kt':null,Number.isFinite(a.track_deg)?Math.round(a.track_deg)+'° track':null].filter(Boolean).join(' · ');tip.hidden=false;}
  side.addEventListener('pointermove',event=>{const rect=side.getBoundingClientRect(),x=(event.clientX-rect.left)*520/rect.width,y=(event.clientY-rect.top)*300/rect.height,hit=sidePoints.find(p=>Math.hypot(p.x-x,p.y-y)<18);tip.hidden=!hit;if(hit)tip.textContent=[hit.a.faa?'FAA · '+hit.a.hex:(hit.a.flight||hit.a.hex),Math.round(hit.a.altitude_ft).toLocaleString()+' ft reported',hit.view.elevation.toFixed(1)+'° elevation',hit.view.inFov?'Inside estimated FoV':'Outside vertical FoV'].join(' · ');});side.addEventListener('pointerleave',()=>tip.hidden=true);
  canvas.addEventListener('pointermove',showAt);canvas.addEventListener('click',showAt);canvas.addEventListener('pointerleave',()=>tip.hidden=true);
  function centerLabel(location, landmarks = []) {
   if (!location) return '';
   const normalize = address => (address || '').trim().toLowerCase().replace(/[,\s]+/g, ' ');
   const addresses = new Set([location.address, location.resolved_address].map(normalize).filter(Boolean));
   const match = landmarks.find(mark => mark.label && (
    [mark.address, mark.resolved_address].some(address => addresses.has(normalize(address))) ||
    (Number.isFinite(mark.latitude) && Number.isFinite(mark.longitude) &&
     mark.latitude === location.latitude && mark.longitude === location.longitude)
   ));
   return match?.label || location.resolved_address || location.address || '';
  }
  async function refresh(){clearTimeout(timer);if(busy)return;busy=true;try{latest=await api('/api/air-traffic');requestFailed=false;state.textContent=latest.status==='available'?(latest.aircraft.length+' aircraft'):latest.status==='stale'?'Feed delayed':latest.status==='waiting'?'Updating center…':'Unavailable';center.textContent=centerLabel(latest.center,latest.landmarks);center.title=center.textContent;canvas.setAttribute('aria-label',`${Number.isFinite(latest.camera_azimuth_deg)?'Camera-up':'North-up'} aircraft radar. ${state.textContent}. Arrows show reported ground track.`);canvas.title=latest.camera_fov?`Estimated view: ${latest.camera_fov.horizontal_deg.toFixed(1)}° horizontal × ${latest.camera_fov.vertical_deg.toFixed(1)}° vertical. Shaded wedge shows projected bearings across the radar range; Side view accounts for estimated aircraft elevation; boxes indicate estimated matches in both dimensions.`:'';}catch(e){requestFailed=true;state.textContent='Reconnecting…';}finally{busy=false;draw();timer=setTimeout(refresh,requestFailed?2500:latest?.faa_live?2000:5000);}}
  window.addEventListener('camera-fov-preview',draw);
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
