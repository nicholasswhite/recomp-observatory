'use strict';
// Pure data helpers also run in Node for observer-only verification.
const ProgressData = {
  value(point,metric,series){
    const valid=n=>typeof n==='number'&&Number.isFinite(n)&&n>=0;
    if(metric==='functions')return series==='combined'?(valid(point.ppuFunctions)&&valid(point.spuFunctions)?point.ppuFunctions+point.spuFunctions:null):(valid(point[series+'Functions'])?point[series+'Functions']:null);
    if(metric==='imports')return valid(point.unresolved)?point.unresolved:null;
    if(metric==='build')return valid(point.buildUnits)?point.buildUnits:null;
    const bytes=series==='combined'?(valid(point.ppu)&&valid(point.spu)?point.ppu+point.spu:null):point[series];
    if(!valid(bytes))return null;
    if(metric==='bytes')return bytes;
    const total=series==='combined'?(valid(point.ppuTotal)&&valid(point.spuTotal)?point.ppuTotal+point.spuTotal:null):point[series+'Total'];
    return valid(total)&&total>0&&bytes<=total?bytes/total*100:null;
  },
  points(snapshot){
    const rows=(snapshot.history||[]).filter(p=>p&&Number.isFinite(Date.parse(p.at))).map(p=>({...p}));
    const last={at:snapshot.collectedAt,ppu:snapshot.ppu.emittedSourceBytes,spu:snapshot.spu.emittedSourceBytes,
      ppuTotal:snapshot.ppu.sourceBytes,spuTotal:snapshot.spu.sourceBytes,rawSpu:snapshot.rawSpu?.emittedSourceBytes??null,rawSpuTotal:snapshot.rawSpu?.sourceBytes??null,
      unresolved:snapshot.imports.unresolvedCount,componentTrue:snapshot.build.componentSummary?.trueCount??null,componentTotal:snapshot.build.componentSummary?.total??null,
      ppuFunctions:snapshot.ps3Metrics?.ppu.generatedFunctions??null,spuFunctions:snapshot.ps3Metrics?.spu.generatedFunctions??null,buildAt:snapshot.build.linkedAt,buildUnits:snapshot.build.translationUnits};
    if(Number.isFinite(Date.parse(last.at))&&(!rows.length||Date.parse(last.at)>Date.parse(rows[rows.length-1].at)))rows.push(last);
    return rows.sort((a,b)=>Date.parse(a.at)-Date.parse(b.at));
  },
  changeEvents(rows,limit=null){
    const keys=['ppu','spu','rawSpu','unresolved','buildAt','buildUnits'];
    const clean=(rows||[]).filter(p=>p&&Number.isFinite(Date.parse(p.at))).sort((a,b)=>Date.parse(a.at)-Date.parse(b.at));
    const events=[];
    for(const point of clean){
      const previous=events.at(-1);
      if(!previous||keys.some(key=>point[key]!==previous[key]))events.push(point);
    }
    return Number.isInteger(limit)&&limit>=0?events.slice(-limit):events;
  },
  preferredMetric(snapshot,hours=24){
    let rows=ProgressData.points(snapshot);
    const observed=Date.parse(snapshot.collectedAt),cutoff=observed-hours*3600000;
    const recent=rows.filter(point=>Date.parse(point.at)>=cutoff);
    if(recent.length>=2)rows=recent;
    const buildValues=new Set(rows.map(point=>point.buildUnits).filter(value=>typeof value==='number'&&Number.isFinite(value)&&value>=0));
    const emissionValues=new Set(rows.filter(point=>typeof point.ppu==='number'&&typeof point.spu==='number').map(point=>`${point.ppu}:${point.spu}`));
    return buildValues.size>1&&emissionValues.size<=1?'build':'bytes';
  },
  thin(rows,limit=500){
    if(rows.length<=limit)return rows;
    // Time bins retain first/last and each numeric series' extrema, preserving dips.
    const readers=['bytes','percent','functions'].flatMap(m=>['combined','ppu','spu'].map(s=>p=>ProgressData.value(p,m,s)));
    readers.push(p=>p.unresolved,p=>p.buildUnits,p=>p.ppuTotal,p=>p.spuTotal);
    const out=new Set([0,rows.length-1]), bins=Math.max(1,Math.floor((limit-2)/(2*readers.length+2)));
    const start=Date.parse(rows[0].at),span=Math.max(1,Date.parse(rows.at(-1).at)-start),groups=new Map();
    rows.forEach((p,i)=>{const bin=Math.min(bins-1,Math.floor((Date.parse(p.at)-start)/span*bins));if(!groups.has(bin))groups.set(bin,[]);groups.get(bin).push(i);});
    for(const group of groups.values()){
      out.add(group[0]);out.add(group.at(-1));
      for(const read of readers){let lo=null,hi=null;for(const i of group){const n=read(rows[i]);if(typeof n!=='number'||!Number.isFinite(n))continue;if(lo===null||n<read(rows[lo]))lo=i;if(hi===null||n>read(rows[hi]))hi=i;}if(lo!==null)out.add(lo);if(hi!==null)out.add(hi);}
    }
    return [...out].sort((a,b)=>a-b).map(i=>rows[i]);
  }
};
if(typeof module!=='undefined')module.exports=ProgressData;

if(typeof document!=='undefined'){
  let chartSnapshot=null, chartRows=[],chartWindow=null,chartTarget='';
  const colors={combined:'#82b5ff',ppu:'#df8ac9',spu:'#8acfe8',imports:'#d8ac73',build:'#a9bde6'};
  const labels={combined:'Combined',ppu:'PPU',spu:'SPU',imports:'Unresolved imports',build:'Compiled units'};
  const el=id=>document.getElementById(id), safe=s=>String(s).replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
  const date=s=>new Date(s).toLocaleString('en-US',{timeZone:'America/New_York',month:'short',day:'numeric',hour:'numeric',minute:'2-digit'});
  const metric=()=>el('graph-metric').value;
  const chosen=()=>['imports','build'].includes(metric())?[metric()]:[...document.querySelectorAll('[data-graph-series]:checked')].map(i=>i.dataset.graphSeries);
  const format=(n,m=metric())=>n==null?'Unknown':m==='percent'?n.toFixed(3)+'%':m==='bytes'?(n/1e6).toFixed(4)+' MB':['build','imports','functions'].includes(m)?Math.round(n).toLocaleString('en-US'):n.toLocaleString('en-US');
  function inspect(point){
    el('graph-inspector').innerHTML=`<strong>${safe(date(point.at))} ET</strong> · ${chosen().map(s=>`<span style="color:${colors[s]}">${labels[s]}: ${format(ProgressData.value(point,metric(),s))}</span>`).join(' · ')}`;
  }
  function renderProgressGraph(snapshot){
    if(snapshot)chartSnapshot=snapshot;if(!chartSnapshot)return;
    const d=chartSnapshot;
    if(chartTarget!==d.target.id){
      if(!d.capabilities.translation&&d.ps3Metrics)el('graph-metric').value='functions';
      else if(d.capabilities.translation)el('graph-metric').value=ProgressData.preferredMetric(d);
      else if(ProgressData.points(d).some(point=>typeof point.buildUnits==='number'))el('graph-metric').value='build';
      chartTarget=d.target.id;
    }
    const m=metric(),series=chosen(),range=el('graph-range').value;
    el('graph-target').textContent=`${d.target.gameTitle} / ${d.target.title}`;
    const context=el('graph-context');
    context.hidden=m!=='build';
    if(m==='build')context.textContent=ProgressData.preferredMetric(d)==='build'?'Emission reports are unchanged in the recent window, so this view highlights successful native-build growth.':'This view tracks successful build receipts. Translation-unit changes are not a completion percentage.';
    el('graph-series').hidden=['imports','build'].includes(m);
    let rows=ProgressData.points(d);
    if(range!=='all'){const cutoff=Date.parse(d.collectedAt)-Number(range)*3600000;rows=rows.filter(p=>Date.parse(p.at)>=cutoff);}
    const usable=rows.filter(p=>series.some(s=>ProgressData.value(p,m,s)!=null));
    const svg=el('progress-svg');svg.replaceChildren();chartRows=rows;
    el('graph-sample-count').textContent=`${usable.length.toLocaleString()} observations in view`;
    if(!usable.length){
      el('graph-empty').hidden=false;el('graph-empty').textContent=series.length?'No measurements for this metric in the selected time range. Earlier percentages require denominators recorded at the time.':'Select at least one line.';
      el('graph-inspector').textContent='No measurement available.';el('graph-change').textContent='—';el('graph-latest').textContent='—';el('graph-table').replaceChildren();chartWindow=null;return;
    }
    el('graph-empty').hidden=true;
    const first=usable[0],last=usable.at(-1),primary=series[0];
    const firstValue=ProgressData.value(first,m,primary),lastValue=ProgressData.value(last,m,primary);
    el('graph-latest').textContent=format(lastValue,m);
    el('graph-change').textContent=firstValue==null||lastValue==null?'Unknown':`${lastValue-firstValue>=0?'+':''}${m==='percent'?(lastValue-firstValue).toFixed(4)+' percentage points':m==='bytes'?(lastValue-firstValue).toLocaleString('en-US')+' bytes':(lastValue-firstValue).toLocaleString('en-US')}`;
    el('graph-primary').textContent=labels[primary];
    const vals=usable.flatMap(p=>series.map(s=>ProgressData.value(p,m,s)).filter(v=>v!=null));
    const focused=el('graph-scale').value==='focus';let low=focused?Math.min(...vals):0,high=Math.max(...vals);
    const padding=(high-low||Math.max(high*.0001,1))*.15;
    if(focused)low=Math.max(0,low-padding);high+=padding;
    if(m==='percent')high=Math.min(100,high);
    if(high<=low)high=low+1;
    let start=Date.parse(rows[0].at),end=Date.parse(rows.at(-1).at);
    if(start===end){start-=30000;end+=30000;}
    const W=1000,H=330,L=96,R=25,T=25,B=52;
    const x=t=>L+(t-start)/(end-start)*(W-L-R),y=v=>T+(high-v)/(high-low)*(H-T-B);
    const parts=[];
    for(let i=0;i<=4;i++){
      const v=low+(high-low)*i/4,yy=y(v),tt=start+(end-start)*i/4;
      parts.push(`<line x1="${L}" y1="${yy}" x2="${W-R}" y2="${yy}" class="graph-grid"/><text x="${L-12}" y="${yy+4}" text-anchor="end" class="graph-axis">${safe(format(v,m))}</text><text x="${x(tt)}" y="${H-15}" text-anchor="${i===0?'start':i===4?'end':'middle'}" class="graph-axis">${safe(date(tt))}</text>`);
    }
    // Draw individual measured points, with dashed connectors for monitoring gaps.
    const sampled=ProgressData.thin(rows);
    const indexes=new Map(rows.map((p,i)=>[p,i]));
    for(const s of series){
      const totalKeys=s==='combined'?['ppuTotal','spuTotal']:[s+'Total'];
      const discontinuities=[0];
      for(let i=1;i<rows.length;i++){
        const gap=Date.parse(rows[i].at)-Date.parse(rows[i-1].at)>180000;
        const scope=m==='percent'&&totalKeys.some(k=>rows[i][k]!==rows[i-1][k]);
        const unknown=ProgressData.value(rows[i],m,s)==null||ProgressData.value(rows[i-1],m,s)==null;
        discontinuities[i]=discontinuities[i-1]+(gap||scope||unknown?1:0);
      }
      let previous=null;
      for(const p of sampled){
        const value=ProgressData.value(p,m,s);if(value==null){previous=null;continue;}
        const xx=x(Date.parse(p.at)),yy=y(value);
        if(previous){const gap=discontinuities[indexes.get(p)]>discontinuities[indexes.get(previous.point)];
          parts.push(`<path d="M${previous.x},${previous.y} L${xx},${yy}" fill="none" stroke="${colors[s]}" stroke-width="2.3" ${gap?'stroke-dasharray="4 6" opacity=".5"':''}/>`);
        }
        parts.push(`<circle cx="${xx}" cy="${yy}" r="${sampled.length<80?3.5:1.6}" fill="${colors[s]}"><title>${safe(labels[s]+': '+format(value,m)+' · '+date(p.at)+' ET')}</title></circle>`);
        previous={point:p,x:xx,y:yy};
      }
    }
    svg.innerHTML=parts.join('');
    svg.setAttribute('aria-label',`${labels[primary]} over time for ${d.target.title}. ${usable.length} measured observations. ${focused?'Focused vertical scale.':'Zero baseline.'}`);
    el('graph-scale-note').textContent=focused?'Focused vertical scale · read the y-axis; it may not begin at zero.':'Vertical scale begins at zero.';
    chartWindow={start,end,left:L,right:W-R,width:W};inspect(last);
    el('graph-table').innerHTML=usable.slice(-100).reverse().map(p=>`<tr><td>${safe(date(p.at))} ET</td>${series.map(s=>`<td>${safe(labels[s]+': '+format(ProgressData.value(p,m,s),m))}</td>`).join('')}</tr>`).join('');
  }
  document.addEventListener('DOMContentLoaded',()=>{
    ['graph-metric','graph-range','graph-scale'].forEach(id=>el(id).addEventListener('change',()=>renderProgressGraph()));
    document.querySelectorAll('[data-graph-series]').forEach(i=>i.addEventListener('change',()=>renderProgressGraph()));
    el('progress-svg').addEventListener('pointermove',event=>{
      if(!chartWindow||!chartRows.length)return;
      const rect=event.currentTarget.getBoundingClientRect(),position=(event.clientX-rect.left)/rect.width*chartWindow.width;
      const t=chartWindow.start+(position-chartWindow.left)/(chartWindow.right-chartWindow.left)*(chartWindow.end-chartWindow.start);
      const closest=chartRows.reduce((best,p)=>Math.abs(Date.parse(p.at)-t)<Math.abs(Date.parse(best.at)-t)?p:best,chartRows[0]);inspect(closest);
    });
    el('progress-svg').addEventListener('keydown',event=>{
      if(!['ArrowLeft','ArrowRight','Home','End'].includes(event.key)||!chartRows.length)return;event.preventDefault();
      let i=Number(el('progress-svg').dataset.point||chartRows.length-1);i=event.key==='Home'?0:event.key==='End'?chartRows.length-1:Math.max(0,Math.min(chartRows.length-1,i+(event.key==='ArrowRight'?1:-1)));
      el('progress-svg').dataset.point=i;inspect(chartRows[i]);
    });
  });
  window.renderProgressGraph=renderProgressGraph;
}
