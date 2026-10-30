'use strict';
let wsCatalog={targets:[]}, wsTarget='', wsGeneration=0, wsCandidates=[];
const wsEl=id=>document.getElementById(id);
const wsEscape=v=>String(v??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));

function wsChoose(id){
  wsTarget=id;wsGeneration++;
  current=null;lastSuccess=null;
  wsEl('target-content').hidden=true;
  wsEl('selection-status').textContent=id?'Loading selected recomp attempt…':'Add a repository to begin.';
  wsEl('module-search').value='';wsEl('processor-filter').value='all';
  const target=wsCatalog.targets.find(t=>t.id===id);
  wsEl('toolchain-badge').textContent=target?.toolchain||'No target';
  wsEl('game-title').textContent=target?.gameTitle||'Select a game';
  wsEl('target-subtitle').textContent=target?.toolchain||'RECOMP TARGET';
  wsEl('attempt-description').textContent=target?.title||'Local recomp statistics and evidence.';
  wsEl('sidebar-game').textContent=target?.gameTitle||'RECOMP WORKSPACE';
  wsEl('footer-target').textContent=target?`${target.gameTitle} / ${target.title}`:'LOCAL WORKSPACE';
  document.title=target?`${target.gameTitle} · ${target.title} · Recomp Observatory`:'Recomp Observatory';
  try{localStorage.setItem('observatory-target',id);}catch{}
  renderGameBranding(target);
  document.getElementById('artwork-editor').hidden=true;
  if(id)refresh(true);
}

function wsAttempts(gameId,preferred){
  const targets=wsCatalog.targets.filter(t=>t.gameId===gameId);
  wsEl('attempt-select').replaceChildren(...targets.map(t=>new Option(t.title+(t.available?'':' · folder unavailable'),t.id)));
  const id=targets.some(t=>t.id===preferred)?preferred:(targets[0]?.id||'');
  wsEl('attempt-select').value=id;wsChoose(id);
}

async function initializeWorkspace(preferred){
  const response=await fetch('/api/workspace',{cache:'no-store'});
  if(!response.ok)throw new Error('Workspace unavailable');
  wsCatalog=await response.json();wsEl('workspace-name').textContent=wsCatalog.name;
  const games=[...new Map(wsCatalog.targets.map(t=>[t.gameId,t.gameTitle])).entries()];
  wsEl('game-select').replaceChildren(...games.map(([id,title])=>new Option(title,id)));
  const target=wsCatalog.targets.find(t=>t.id===preferred)||wsCatalog.targets[0];
  wsEl('game-select').value=target?.gameId||'';wsAttempts(target?.gameId,target?.id);
}

function renderTarget(d){
  const t=d.target;
  const labels={'game-title':t.gameTitle,'sidebar-game':t.gameTitle,
    'attempt-description':t.title,'target-subtitle':t.toolchain,
    'footer-target':`${t.gameTitle} / ${t.title}`,'reader-description':d.capabilities.description,
    'target-status':'Observing this attempt'};
  Object.entries(labels).forEach(([id,label])=>wsEl(id).textContent=label);
  renderGameBranding(t);
  document.title=`${t.gameTitle} · ${t.title} · Recomp Observatory`;
  document.body.classList.toggle('without-translation',!d.capabilities.translation);
  wsEl('recorded-runtime').innerHTML=d.recordedRuntime?`<strong>${d.recordedRuntime.fps.toFixed(2)} FPS · historical sample</strong><p class="metric-note">${wsEscape(d.recordedRuntime.scope)} ${d.recordedRuntime.frames??'—'} frames · ${wsEscape(time(d.recordedRuntime.recordedAt))}</p>`:'';
}

async function wsPost(url,value){
  const response=await fetch(url,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(value)});
  const data=await response.json();if(!response.ok)throw new Error(data.error||`HTTP ${response.status}`);return data;
}

document.addEventListener('DOMContentLoaded',()=>{
  wsEl('game-select').addEventListener('change',()=>wsAttempts(wsEl('game-select').value));
  wsEl('attempt-select').addEventListener('change',()=>wsChoose(wsEl('attempt-select').value));
  wsEl('manage-toggle').addEventListener('click',()=>{
    wsEl('repo-manager').hidden=!wsEl('repo-manager').hidden;
    if(!wsEl('repo-manager').hidden)wsEl('artwork-editor').hidden=true;
  });
  wsEl('repo-close').addEventListener('click',()=>{wsEl('repo-manager').hidden=true;wsEl('manage-toggle').focus();});
  wsEl('scan-form').addEventListener('submit',async event=>{
    event.preventDefault();wsEl('scan-button').disabled=true;wsEl('add-targets').hidden=true;wsEl('scan-results').replaceChildren();
    wsEl('scan-message').textContent='Scanning supported report locations…';
    try{
      const result=await wsPost('/api/discover',{root:wsEl('repo-path').value});wsCandidates=result.targets;
      wsEl('scan-message').textContent=`${result.targets.length} candidate(s) · ${result.foldersVisited} folders inspected. ${result.warnings.join(' ')}`;
      wsEl('scan-results').innerHTML=result.targets.map((t,i)=>`<div class="candidate" data-index="${i}"><label><input type="checkbox" checked data-field="include"> Include this attempt</label><code>${wsEscape(t.root)}</code><div class="candidate-fields"><label>Game name<input data-field="gameTitle" value="${wsEscape(t.gameTitle)}"></label><label>Attempt name<input data-field="title" value="${wsEscape(t.title)}"></label><label>Toolchain badge<input data-field="toolchain" value="${wsEscape(t.toolchain)}"></label></div><small>${wsEscape(t.adapter)}</small></div>`).join('');
      wsEl('add-targets').hidden=false;
    }catch(error){wsEl('scan-message').textContent=error.message;}finally{wsEl('scan-button').disabled=false;}
  });
  wsEl('add-targets').addEventListener('click',async()=>{
    wsEl('add-targets').disabled=true;
    try{
      const targets=[...wsEl('scan-results').querySelectorAll('.candidate')].filter(row=>row.querySelector('[data-field="include"]').checked).map(row=>{
        const t={...wsCandidates[Number(row.dataset.index)]};
        ['gameTitle','title','toolchain'].forEach(k=>t[k]=row.querySelector(`[data-field="${k}"]`).value.trim());return t;
      });
      await wsPost('/api/targets',{targets});await initializeWorkspace(wsTarget);
      wsEl('scan-message').textContent='Targets saved. Select a game and recomp attempt above.';wsEl('add-targets').hidden=true;
    }catch(error){wsEl('scan-message').textContent=error.message;}finally{wsEl('add-targets').disabled=false;}
  });
});
