'use strict';
(()=>{
 const names={human:'Stable',experimental:'Experimental',hybrid:'Hybrid',machine:'Machine-only'};
 const ns='http://www.w3.org/2000/svg';let lastPoints=[],signature='';
 const svg=(tag,attrs,text)=>{const el=document.createElementNS(ns,tag);for(const [k,v]of Object.entries(attrs))el.setAttribute(k,v);if(text!==undefined)el.textContent=text;return el};
 function render(points){
  const leaderboard=document.getElementById('model-leaderboard');if(!leaderboard)return;
  let card=document.getElementById('modelScoreHistory');
  if(!card){card=document.createElement('section');card.id='modelScoreHistory';card.className='metrics-card model-comparison-card';card.innerHTML='<h2>Model score history</h2><div class="metrics-legend score-history-legend"></div><svg class="score-history-chart" role="img" aria-label="Model composite scores out of 100 over time"></svg><p class="score-history-empty" hidden>No scored comparisons in this period.</p>';const tableCard=leaderboard.closest('.metrics-card'),row=document.createElement('div');row.className='metrics-score-overview';tableCard.before(row);row.append(tableCard,card);
   const style=document.createElement('style');style.textContent='.metrics-score-overview{display:grid;grid-template-columns:minmax(0,1fr) minmax(0,1fr);gap:16px;align-items:stretch;margin-bottom:16px}.metrics-score-overview>.metrics-card{min-width:0;margin:0}@media(max-width:1100px){.metrics-score-overview{grid-template-columns:minmax(0,1fr)}}#modelScoreHistory{min-width:0;display:flex;flex-direction:column}.metrics-score-overview>.metrics-card>h2{margin:0 0 12px}.metrics-score-overview #model-leaderboard-summary,.metrics-score-overview .score-history-legend{margin:0 0 16px;font-size:11px;line-height:1.6;min-height:17.6px}.score-history-chart{display:block;width:100%;height:0;min-height:250px;flex:1 1 250px;overflow:visible}.score-history-chart text{font:10px var(--app-font);fill:var(--muted)}.score-history-chart .grid{stroke:var(--line);stroke-width:1}#modelScoreHistory .score-line{fill:none;stroke:var(--ink);stroke-width:2;stroke-linejoin:round;stroke-linecap:round}#modelScoreHistory .score-line.experimental{stroke-dasharray:7 4}#modelScoreHistory .score-line.hybrid{stroke-dasharray:2 4}#modelScoreHistory .score-line.machine{stroke-dasharray:10 3 2 3}.score-history-chart .score-hit{fill:transparent;stroke:none;cursor:crosshair}.score-history-chart .score-hit:focus{outline:none;stroke:var(--ink)}.score-history-legend{display:flex;flex-wrap:wrap;gap:16px}.score-history-legend span{display:inline-flex;gap:6px;align-items:center}.score-history-legend .score-swatch{display:block;flex:none;width:40px;height:10px;overflow:visible}';document.head.append(style);
   for(const [lane,name]of Object.entries(names)){const label=document.createElement('span');label.className=lane;const marker=svg('svg',{viewBox:'0 0 40 10',width:40,height:10,class:'score-swatch','aria-hidden':'true'});marker.append(svg('path',{d:'M2 5H38',class:'score-line '+lane}));label.append(marker,document.createTextNode(name));card.querySelector('.score-history-legend').append(label)}
   new ResizeObserver(()=>{requestAnimationFrame(()=>render(lastPoints))}).observe(card.querySelector('.score-history-chart'));
  }
  const chart=card.querySelector('.score-history-chart'),width=Math.max(280,chart.clientWidth||960),height=Math.max(250,chart.clientHeight||250),left=40,right=width-12,top=12,bottom=height-40;
  const rows=points.map(p=>({...p,time:p.epoch?p.epoch*1000:Date.parse(p.day+'T12:00:00Z')})).filter(p=>Number.isFinite(p.time)).sort((a,b)=>a.time-b.time);
  const next=JSON.stringify([width,height,rows]);if(next===signature)return;signature=next;chart.replaceChildren();chart.setAttribute('viewBox',`0 0 ${width} ${height}`);
  for(let n=0;n<=100;n+=25){const y=bottom-n/100*(bottom-top);chart.append(svg('line',{x1:left,x2:right,y1:y,y2:y,class:'grid'}),svg('text',{x:left-8,y:y+4,'text-anchor':'end'},n))}
  const first=rows[0]?.time,last=rows.at(-1)?.time,x=t=>first===last?(left+right)/2:left+(t-first)/(last-first)*(right-left),y=v=>bottom-v/100*(bottom-top);
  let tip=document.getElementById('scoreHistoryTooltip');if(!tip){tip=document.createElement('div');tip.id='scoreHistoryTooltip';tip.className='model-chart-tooltip';tip.setAttribute('role','status');document.body.append(tip)}tip.hidden=true;
  const hide=()=>{tip.hidden=true;chart.querySelectorAll('.score-line').forEach(line=>line.style.opacity='')};chart.onpointerleave=hide;
  function show(row,lane,clientX,clientY){
   tip.replaceChildren();const title=document.createElement('strong');title.textContent=names[lane];tip.append(title);
   for(const value of [scoreFor(row,lane).toFixed(1)+' / 100',new Date(row.time).toLocaleString(),'Model '+(row[lane+'_version']||'').slice(0,12)+' · v'+(row.settings_revisions?.[lane]??0)]){const line=document.createElement('div');line.textContent=value;tip.append(line)}
   chart.querySelectorAll('.score-line').forEach(line=>line.style.opacity=line.classList.contains(lane)?'1':'.25');
   tip.hidden=false;tip.style.left=Math.max(12,Math.min(innerWidth-tip.offsetWidth-12,clientX+12))+'px';tip.style.top=Math.max(12,Math.min(innerHeight-tip.offsetHeight-12,clientY-tip.offsetHeight-12))+'px'
  }
  let count=0;const segments=[];
  for(const lane of Object.keys(names)){let d='',previous=null;const hits=[];
   for(const row of rows){const score=scoreFor(row,lane);if(score===null){previous=null;continue}count++;d+=(previous?' L':' M')+x(row.time)+','+y(score);segments.push({lane,a:previous||row,b:row});previous=row;
    const dot=svg('circle',{cx:x(row.time),cy:y(score),r:8,class:'score-hit',tabindex:0,'aria-label':`${names[lane]}: ${score.toFixed(1)} out of 100, ${new Date(row.time).toLocaleString()}`});dot.onfocus=()=>{const r=dot.getBoundingClientRect();show(row,lane,r.x,r.y)};dot.onblur=hide;hits.push(dot)
   }
   chart.append(svg('path',{d,class:'score-line '+lane}));for(const hit of hits)chart.append(hit);
  }
  chart.onpointermove=e=>{
   const r=chart.getBoundingClientRect(),px=(e.clientX-r.left)/r.width*width,py=(e.clientY-r.top)/r.height*height;let nearest=null,distance=10;
   for(const segment of segments){const {lane,a,b}=segment,ax=x(a.time),ay=y(scoreFor(a,lane)),bx=x(b.time),by=y(scoreFor(b,lane)),dx=bx-ax,dy=by-ay,length=dx*dx+dy*dy,t=length?Math.max(0,Math.min(1,((px-ax)*dx+(py-ay)*dy)/length)):0,dist=Math.hypot(px-ax-t*dx,py-ay-t*dy);
    if(dist<distance){distance=dist;nearest={lane,row:t<.5?a:b}}
   }
   if(nearest)show(nearest.row,nearest.lane,e.clientX,e.clientY);else hide();
  };
  card.querySelector('.score-history-empty').hidden=count>0;
  if(rows.length){const ticks=first===last?1:(width<500?3:6);for(let i=0;i<ticks;i++){const time=ticks===1?first:first+i*(last-first)/(ticks-1);chart.append(svg('text',{x:x(time),y:height-12,'text-anchor':i===0?'start':i===ticks-1?'end':'middle'},new Date(time).toLocaleDateString(undefined,{month:'short',day:'numeric'})))}}

 }
 function scoreFor(row,lane){const score=modelComposite(row.lanes?.[lane]);if(!score)return null;const support=Object.keys(names).map(k=>modelComposite(row.lanes?.[k])).find(Boolean);return score.positive===support.positive&&score.negative===support.negative?score.score:null}
 window.addEventListener('station-score-history',e=>{lastPoints=e.detail.points;render(lastPoints)});
})();
