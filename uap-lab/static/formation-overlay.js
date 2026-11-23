'use strict';
(() => {
 if (window.FIELD_PUBLIC_READ_ONLY || recordingAsset) return;
 const controls=document.querySelector('#formation-controls'), toggle=document.querySelector('#formation-toggle');
 const tools=document.querySelector('#formation-tools'),edit=document.querySelector('#formation-edit');
 const undo=document.querySelector('#formation-undo'),save=document.querySelector('#formation-save'),message=document.querySelector('#formation-status');
 const predict=document.querySelector('#formation-predict'),exportPrediction=document.querySelector('#formation-export-prediction');
 let estimates=[],savedJob=null;
 const route='/api/email-review/formation',query='?'+new URLSearchParams({id});
 let picking=false,points=[],anchor=null,tracks=[],revision='',timer,state='',sending=false;
 controls.hidden=false;controls.style.display='';
 function buttons(){
   tools.hidden=!toggle.checked&&!state&&!picking;
   exportPrediction.hidden=!predict.checked||picking||state!=='ready'||savedJob?.prediction===true;
   exportPrediction.disabled=sending;
   edit.hidden=picking||!toggle.checked;undo.hidden=!picking||!toggle.checked;save.hidden=!picking;
   undo.disabled=!points.length||sending;save.disabled=points.length<2||sending;
 }
 function stopPicking(){picking=false;points=[];anchor=null;buttons();}
 function instructions(){
   message.textContent=points.length?points.length+' lights selected. Connect them in outline order.':'Pause on a clear frame and click each light in outline order.';
   buttons();draw();
 }
 function pick(){video.pause();box=null;drag=null;hoverPoint=null;picking=true;points=[];anchor=null;instructions();}
 async function refresh(){
   clearTimeout(timer);
   try{
     const response=await fetch(route+query,{cache:'no-store'});if(!response.ok)throw Error('Could not load the overlay.');
     const job=await response.json();state=job.state||'';if(!savedJob&&job.prediction)predict.checked=true;savedJob=job;buttons();
     if(toggle.checked&&state==='ready'&&revision!==job.revision){
       const r=await fetch(route+'/tracks'+query+'&predict=1&v='+job.revision);if(!r.ok)throw Error('Could not load the tracks.');
       const payload=await r.json();tracks=payload.tracks;estimates=payload.predictions||[];revision=job.revision;draw();
     }
     if(!toggle.checked)message.textContent=picking?'Selected points retained.':state==='ready'?'Formation saved · overlay hidden':state==='error'?job.error:state?'Tracking lights…':'';
     else if(!picking)message.textContent=state==='error'?job.error:state==='ready'?(predict.checked?'Dashed lines and diamonds indicate predicted positions.':'Tracked lights · image-plane positions'):state?'Tracking lights…':'';
     if(state==='queued'||state==='tracking')timer=setTimeout(refresh,3000);
   }catch(e){if(toggle.checked)message.textContent=e.message;timer=setTimeout(refresh,5000);}
 }
 toggle.onchange=async()=>{
   buttons();draw();
   await refresh();
   if(toggle.checked&&picking)instructions();
   else if(toggle.checked&&(!state||state==='error'))pick();
 };
 predict.onchange=()=>{buttons();draw();if(!picking)refresh();};
 exportPrediction.onclick=async()=>{
   if(sending||!savedJob)return;
   sending=true;buttons();
   try{
     const {points,anchor,start,end,revision:from_revision}=savedJob;
     await request(route,{id,points,anchor,start,end,from_revision,prediction:true});await refresh();
   }catch(e){message.textContent=e.message;}finally{sending=false;buttons();}
 };
 edit.onclick=pick;
 undo.onclick=()=>{points.pop();if(!points.length)anchor=null;instructions();};
 canvas.addEventListener('pointerdown',e=>{
   if(!toggle.checked||!picking)return;
   e.preventDefault();e.stopImmediatePropagation();
   if(!ready||video.seeking||sending)return;
   video.pause();
   const t=frameAt(video.currentTime);
   if(anchor!==null&&Math.abs(t-anchor)>.002){message.textContent='Return to the selected frame or undo the points to start again.';return;}
   if(points.length<16){anchor=t;points.push(point(e).map(Math.round));instructions();}
 },true);
 save.onclick=async()=>{
   if(sending||anchor===null)return;
   sending=true;buttons();
   try{
     const [start,end]=playerRange();
     await request(route,{id,anchor,start,end,points,prediction:predict.checked});
     tracks=[];stopPicking();await refresh();
   }catch(e){message.textContent=e.message;}finally{sending=false;buttons();}
 };
 window.formationDraw=t=>{
   if(!toggle.checked)return false;
   let visible=[];const inferred=new Set();
   if(picking){if(anchor===null||Math.abs(anchor-t)<.003)visible=points;}
   else if(tracks.length&&t>=tracks[0][0]&&t<=tracks.at(-1)[0]){
     let l=0,h=tracks.length-1;while(l<h){const m=(l+h)>>1;if(tracks[m][0]<t)l=m+1;else h=m;}
     const a=tracks[Math.max(0,l-1)],b=tracks[l],factor=a[0]===b[0]?0:(t-a[0])/(b[0]-a[0]);
     visible=a[1].map((p,i)=>{
       let q=b[1][i];
       if((!p||!q)&&predict.checked){
         p=p||estimates[Math.max(0,l-1)]?.[i];q=q||estimates[l]?.[i];
         if(p&&q)inferred.add(i);
       }
       return p&&q?p.map((x,j)=>x+factor*(q[j]-x)):null;
     });
   }
   ctx.save();ctx.lineWidth=1.5*canvas.width/Math.max(1,canvas.clientWidth);ctx.strokeStyle='#ebc314';
   visible.forEach((p,i)=>{const q=visible[(i+1)%visible.length];if(p&&q){ctx.setLineDash(inferred.has(i)||inferred.has((i+1)%visible.length)?[8,8]:[]);ctx.beginPath();ctx.moveTo(...p);ctx.lineTo(...q);ctx.stroke();}});
   ctx.setLineDash([]);
   visible.forEach((p,i)=>{
     if(!p)return;
     ctx.beginPath();
     if(inferred.has(i)){
       const [x,y]=p;ctx.moveTo(x,y-8);ctx.lineTo(x+8,y);ctx.lineTo(x,y+8);ctx.lineTo(x-8,y);ctx.closePath();
     }else ctx.arc(...p,7,0,Math.PI*2);
     ctx.stroke();
   });
   ctx.restore();return picking;
 };
 buttons();refresh();
})();
