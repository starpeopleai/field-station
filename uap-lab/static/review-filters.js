"use strict";
(()=>{
 const params=new URLSearchParams(location.search),legacy=params.get('view');
 const state={classification:'all',review_status:'needs_review',starred:false,manual:legacy==='manual_recordings'};
 if(legacy){Object.assign(state,{classification:'all',review_status:'all'});if(['anomalous','not_anomalous'].includes(legacy))state.classification=legacy;if(['needs_review','human_reviewed'].includes(legacy))state.review_status=legacy;if(legacy==='human_reviewed_anomalous')Object.assign(state,{classification:'anomalous',review_status:'human_reviewed'});if(legacy==='starred')state.starred=true;}
 for(const [key,values]of [['classification',['all','anomalous','not_anomalous']],['review_status',['all','needs_review','human_reviewed']]])if(values.includes(params.get(key)))state[key]=params.get(key);
 const sidebar=document.getElementById('objectViews'),main=sidebar.closest('main'),layout=document.createElement('div'),content=document.createElement('div'),controls=new Map();layout.className='review-layout';content.className='review-content';sidebar.className='review-sidebar';sidebar.setAttribute('aria-label','Detection filters');sidebar.replaceChildren();for(const node of [...main.childNodes])if(node!==sidebar)content.append(node);layout.append(sidebar,content);main.append(layout);
 const timeRange={};
 const timeField=document.createElement('details'),timeLegend=document.createElement('summary'),timeFields=document.createElement('div');
 timeField.className='review-time';timeFields.className='time-fields';
 timeLegend.textContent='Capture time';timeField.append(timeLegend,timeFields);
 const zone=new Intl.DateTimeFormat(undefined,{timeZoneName:'short'}).formatToParts(new Date(Number(params.get('captured_from')||params.get('captured_to')||Date.now()/1000)*1000)).find(p=>p.type==='timeZoneName')?.value;
 const inputs={};
 for(const [key,title] of [['captured_from','From'],['captured_to','Through']]){
  const label=document.createElement('label'),input=document.createElement('input');
  input.type='datetime-local';input.step='1';label.textContent=title+(zone?' ('+zone+')':'');
  const value=params.get(key);
  if(value && Number.isFinite(Number(value))){
   const d=new Date(Number(value)*1000);
   if(Number.isFinite(d.getTime())){input.value=new Date(d.getTime()-d.getTimezoneOffset()*60000).toISOString().slice(0,19);timeRange[key]=value;}
  }
  inputs[key]=input;label.append(input);timeFields.append(label);
 }
 const apply=document.createElement('button'),clearTime=document.createElement('button');
 apply.type=clearTime.type='button';apply.textContent='Apply';clearTime.textContent='Clear';
 apply.onclick=()=>{
  const from=inputs.captured_from,to=inputs.captured_to;
  to.setCustomValidity(from.value && to.value && new Date(from.value)>new Date(to.value)?'End must follow start':'');
  if(!from.reportValidity()||!to.reportValidity())return;
  for(const [key,input] of Object.entries(inputs)){if(input.value)timeRange[key]=String(new Date(input.value).getTime()/1000);else delete timeRange[key];}
  return change();
 };
 clearTime.onclick=()=>{for(const [key,input] of Object.entries(inputs)){delete timeRange[key];input.value='';input.setCustomValidity('');}return change();};
 const actions=document.createElement('div');actions.className='time-actions';clearTime.className='clear-time';actions.append(apply,clearTime);timeField.append(actions);timeField.open=Object.keys(timeRange).length>0;sidebar.append(timeField);

 function change(){const query=new URLSearchParams({...timeRange,classification:state.classification,review_status:state.review_status});if(state.starred)query.set('view','starred');if(state.manual)query.set('view','manual_recordings');syncSource();history.replaceState(null,'','/label-videos?'+query);const detail={};window.dispatchEvent(new CustomEvent('review-filter-change',{detail}));return detail.completion;}
 for(const [key,title,options]of [['review_status','Review status',[['needs_review','Machine-only review'],['human_reviewed','Human-reviewed'],['all','All']]],['classification','Classification',[['all','Both'],['anomalous','Anomalous'],['not_anomalous','Not anomalous']]]]){const field=document.createElement('fieldset'),legend=document.createElement('legend');legend.textContent=title;field.append(legend);for(const [value,text]of options){const label=document.createElement('label'),input=document.createElement('input'),name=document.createElement('span'),count=document.createElement('span');input.type='radio';input.name=key;input.value=value;input.checked=state[key]===value;name.textContent=text;count.className='tab-count';count.textContent='…';input.addEventListener('change',()=>{if(input.checked){state[key]=value;change();}});label.append(input,name,count);field.append(label);controls.set(key+':'+value,count);}sidebar.append(field);}
 const starLabel=document.createElement('label'),star=document.createElement('input'),starText=document.createElement('span');starLabel.className='star-filter';starLabel.hidden=true;star.type='checkbox';star.checked=state.starred;starText.textContent='Starred';star.addEventListener('change',()=>{state.starred=star.checked;change();});const starCount=document.createElement('span');starCount.className='tab-count';starCount.textContent='…';starLabel.append(star,starText,starCount);sidebar.append(starLabel);
 const source=document.createElement('fieldset'),legend=document.createElement('legend');legend.textContent='Show';source.append(legend);
 for(const [value,text]of [['detections','Detections'],['manual','Manual recordings']]){const label=document.createElement('label'),input=document.createElement('input'),name=document.createElement('span');input.type='radio';input.name='recording_source';input.value=value;input.checked=(value==='manual')===state.manual;name.textContent=text;const count=document.createElement('span');count.className='tab-count';count.textContent='…';controls.set('source:'+value,count);input.addEventListener('change',()=>{if(input.checked){state.manual=value==='manual';change();}});label.append(input,name,count);source.append(label);}sidebar.prepend(source);
 function syncSource(){for(const field of sidebar.querySelectorAll('fieldset'))if(field!==source&&field!==timeField)field.hidden=state.manual;starLabel.hidden=state.manual||!starEnabled;document.getElementById('detectionQueue').classList.toggle('manual-recordings',state.manual);const empty=document.querySelector('#queueEmpty span');if(empty)empty.textContent=state.manual?'No manual recordings.':'No objects in this view.';}
 let starEnabled=false;syncSource();
 const clipLinks=document.createElement('div');clipLinks.className='review-time-clips';timeField.append(clipLinks);
 function showClips(clips){
  clipLinks.replaceChildren(...clips.map(clip=>{const a=document.createElement('a');a.href=clip.url;a.textContent=clip.title;return a;}));
 }
 window.REVIEW_FILTERS={showClips,enableStarred:enabled=>{starEnabled=enabled;starLabel.hidden=state.manual||!enabled;if(!enabled){state.starred=false;star.checked=false;}},view:()=>state.manual?'manual_recordings':state.starred?'starred':'all',query:before=>new URLSearchParams({...timeRange,view:state.manual?'manual_recordings':state.starred?'starred':'all',classification:state.classification,review_status:state.review_status,before,limit:100}),matches:row=>(!Object.keys(timeRange).length||((row.captured_epoch??row.detected_epoch??(state.manual?row.created:null))!=null && (row.captured_epoch??row.detected_epoch??row.created)>=(timeRange.captured_from??-Infinity) && (row.captured_epoch??row.detected_epoch??row.created)<Number(timeRange.captured_to??Infinity)+1))&&(state.manual?row.kind==='manual_recording':(!state.starred||row.starred)&&(state.classification==='all'||row.label===state.classification)&&(state.review_status==='all'||Boolean(row.human_reviewed)===(state.review_status==='human_reviewed'))),render:(counts,indexing,sources,totals)=>{if(!indexing&&Number.isFinite(totals?.starred)){starCount.textContent=totals.starred.toLocaleString('en-US',{notation:'compact',maximumFractionDigits:1});starCount.title=totals.starred.toLocaleString();}for(const [key,value]of Object.entries(sources||{})){const node=controls.get('source:'+(key==='manual_recordings'?'manual':key));if(node&&Number.isFinite(value)){node.textContent=value.toLocaleString('en-US',{notation:'compact',maximumFractionDigits:1});node.title=value.toLocaleString();}}sidebar.setAttribute('aria-busy',String(indexing));if(!counts||indexing)return;for(const [key,node]of controls){const [group,value]=key.split(':');if(Number.isFinite(counts[group]?.[value])){node.textContent=counts[group][value].toLocaleString('en-US',{notation:'compact',maximumFractionDigits:1});node.title=counts[group][value].toLocaleString();}}}};
})();
