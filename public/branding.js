'use strict';
let brandingTarget=null,brandingRevision=0;

function localArtworkUrl(value){
  return typeof value==='string'&&/^\/artwork\/(?:custom\/[a-f0-9]{64}\.(?:jpg|png|webp)|auto\/[a-f0-9]{64}\.png)$/.test(value)?value:'';
}

function loadArtwork(element,candidates,revision,onready,onfail){
  const urls=[...new Set(candidates.filter(Boolean))];
  element.onload=null;element.onerror=null;element.hidden=true;element.removeAttribute('src');
  const attempt=index=>{
    if(revision!==brandingRevision)return;
    if(index>=urls.length){if(onfail)onfail();return;}
    const url=urls[index],probe=new Image();
    probe.onload=()=>{
      if(revision!==brandingRevision)return;
      element.src=url;element.hidden=false;
      if(onready)onready(url);
    };
    probe.onerror=()=>attempt(index+1);
    probe.src=url;
  };
  attempt(0);
}

function renderGameBranding(target){
  brandingTarget=target||null;
  const revision=++brandingRevision,b=target?.branding||{};
  const image=document.getElementById('game-cover'),backdrop=document.getElementById('game-backdrop'),overlay=document.getElementById('game-overlay');
  const workspaceBackdrop=document.getElementById('workspace-backdrop');
  const cover=image.closest('.game-cover'),fallback=document.getElementById('cover-placeholder'),credit=document.getElementById('cover-credit');
  document.getElementById('game-brand-line').textContent=[b.studio,b.subtitle].filter(Boolean).join(' · ');
  fallback.textContent=(target?.gameTitle||'GAME').split(/\s+/).slice(0,3).map(word=>word[0]).join('').toUpperCase();
  const coverUrl=localArtworkUrl(b.coverUrl),iconUrl=localArtworkUrl(b.iconUrl);
  const backgroundUrl=localArtworkUrl(b.backgroundUrl),overlayUrl=localArtworkUrl(b.overlayUrl);
  const backgroundReady=Boolean(backgroundUrl)&&backdrop.getAttribute('src')===backgroundUrl&&!backdrop.hidden&&!workspaceBackdrop.hidden;
  if(!backgroundReady)workspaceBackdrop.hidden=true;
  const iconMode=!coverUrl&&Boolean(iconUrl);
  cover.classList.toggle('game-icon',iconMode);
  fallback.hidden=false;
  image.alt='';
  loadArtwork(image,[coverUrl,iconUrl],revision,loaded=>{
    const loadedIcon=Boolean(iconUrl)&&loaded===iconUrl;
    cover.classList.toggle('game-icon',loadedIcon);
    image.alt=target?(loadedIcon?`${target.gameTitle} game icon`:`${target.gameTitle} cover art`):'';
    fallback.hidden=true;
  },()=>{cover.classList.remove('game-icon');image.alt='';fallback.hidden=false;});
  if(!backgroundReady)loadArtwork(backdrop,[backgroundUrl],revision,()=>{workspaceBackdrop.hidden=false;},()=>{workspaceBackdrop.hidden=true;});
  loadArtwork(overlay,[overlayUrl],revision);
  const source=typeof b.source==='string'&&/^https?:\/\//.test(b.source)?b.source:'';
  credit.hidden=!source;
  if(source)credit.href=source;else credit.removeAttribute('href');
  document.getElementById('artwork-game-name').textContent=target?.gameTitle||'Select a game';
}

document.addEventListener('DOMContentLoaded',()=>{
  const el=id=>document.getElementById(id),panel=el('artwork-editor');
  el('artwork-toggle').addEventListener('click',()=>{
    panel.hidden=!panel.hidden;
    if(!panel.hidden){
      el('repo-manager').hidden=true;
      const b=brandingTarget?.branding||{},hasAutomatic=Boolean(b.iconUrl||b.overlayUrl||b.backgroundUrl);
      el('brand-studio').value=b.studio||'';el('brand-subtitle').value=b.subtitle||'';el('brand-source').value=b.source||'';
      el('brand-cover-file').value='';
      el('artwork-message').textContent=hasAutomatic?(b.coverUrl?'Manual cover is active; restoring automatic artwork will reveal the detected game icon.':'Automatically detected PS3 artwork is active. A manual cover overrides the game icon.'):'Settings apply to every attempt for this game.';
    }
  });
  el('artwork-close').addEventListener('click',()=>{panel.hidden=true;});
  el('artwork-form').addEventListener('submit',async event=>{
    event.preventDefault();if(!brandingTarget)return;
    const target=brandingTarget,button=el('artwork-save');button.disabled=true;
    try{
      const file=el('brand-cover-file').files[0];let image='';
      if(file){
        if(file.size>4*1024*1024)throw new Error('Choose a cover smaller than 4 MiB.');
        if(!['image/png','image/jpeg','image/webp'].includes(file.type))throw new Error('Choose a JPEG, PNG or WebP image.');
        image=await new Promise((resolve,reject)=>{const reader=new FileReader();reader.onload=()=>resolve(reader.result);reader.onerror=()=>reject(new Error('Cannot read this image'));reader.readAsDataURL(file);});
      }
      await wsPost('/api/branding',{gameId:target.gameId,studio:el('brand-studio').value,subtitle:el('brand-subtitle').value,source:el('brand-source').value,image});
      await initializeWorkspace(wsTarget);el('artwork-message').textContent='Game artwork and branding saved.';panel.hidden=true;
    }catch(error){el('artwork-message').textContent=error.message;}finally{button.disabled=false;}
  });
  el('artwork-reset').addEventListener('click',async()=>{
    if(!brandingTarget)return;el('artwork-reset').disabled=true;
    try{await wsPost('/api/branding',{gameId:brandingTarget.gameId,reset:true});await initializeWorkspace(wsTarget);panel.hidden=true;}
    catch(error){el('artwork-message').textContent=error.message;}finally{el('artwork-reset').disabled=false;}
  });
});
