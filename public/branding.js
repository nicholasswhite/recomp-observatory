'use strict';
let brandingTarget=null,brandingRevision=0;
const titleBoundsCache=new Map();
const TITLE_PROBE_LIMIT=512,TITLE_OUTPUT_WIDTH=1200,TITLE_OUTPUT_HEIGHT=280;

function localArtworkUrl(value){
  return typeof value==='string'&&/^\/artwork\/(?:custom\/[a-f0-9]{64}\.(?:jpg|png|webp)|auto\/[a-f0-9]{64}\.png)$/.test(value)?value:'';
}

function visibleAlphaBounds(pixels,width,height,threshold=2){
  if(!pixels||!Number.isInteger(width)||!Number.isInteger(height)||width<1||height<1||pixels.length<width*height*4)return null;
  let left=width,top=height,right=-1,bottom=-1;
  for(let y=0,index=3;y<height;y++)for(let x=0;x<width;x++,index+=4){
    if(pixels[index]<=threshold)continue;
    if(x<left)left=x;if(x>right)right=x;if(y<top)top=y;if(y>bottom)bottom=y;
  }
  return right<left?null:{x:left,y:top,width:right-left+1,height:bottom-top+1};
}

function titleArtworkBounds(image,url){
  if(titleBoundsCache.has(url))return titleBoundsCache.get(url);
  const naturalWidth=image.naturalWidth||image.width,naturalHeight=image.naturalHeight||image.height;
  if(!naturalWidth||!naturalHeight)return null;
  const scale=Math.min(1,TITLE_PROBE_LIMIT/Math.max(naturalWidth,naturalHeight));
  const width=Math.max(1,Math.round(naturalWidth*scale)),height=Math.max(1,Math.round(naturalHeight*scale));
  const probe=document.createElement('canvas');probe.width=width;probe.height=height;
  const context=probe.getContext('2d',{willReadFrequently:true});if(!context)return null;
  context.drawImage(image,0,0,width,height);
  const sampled=visibleAlphaBounds(context.getImageData(0,0,width,height).data,width,height);
  if(!sampled)return null;
  const pad=2;
  const left=Math.max(0,Math.floor(sampled.x/scale)-pad),top=Math.max(0,Math.floor(sampled.y/scale)-pad);
  const right=Math.min(naturalWidth,Math.ceil((sampled.x+sampled.width)/scale)+pad);
  const bottom=Math.min(naturalHeight,Math.ceil((sampled.y+sampled.height)/scale)+pad);
  const bounds={x:left,y:top,width:right-left,height:bottom-top};titleBoundsCache.set(url,bounds);return bounds;
}

function drawTitleArtwork(canvas,image,url){
  const bounds=titleArtworkBounds(image,url);if(!bounds||bounds.width<1||bounds.height<1)return false;
  const scale=Math.min(1,TITLE_OUTPUT_WIDTH/bounds.width,TITLE_OUTPUT_HEIGHT/bounds.height);
  canvas.width=Math.max(1,Math.round(bounds.width*scale));canvas.height=Math.max(1,Math.round(bounds.height*scale));
  const context=canvas.getContext('2d');if(!context)return false;
  context.clearRect(0,0,canvas.width,canvas.height);
  context.drawImage(image,bounds.x,bounds.y,bounds.width,bounds.height,0,0,canvas.width,canvas.height);
  canvas.dataset.source=url;return true;
}

function setTitleArtworkMode(slot,heading,canvas,enabled){
  slot.classList.toggle('has-title-art',enabled);heading.classList.toggle('visually-hidden',enabled);canvas.hidden=!enabled;
  if(!enabled)canvas.removeAttribute('data-source');
}

function loadTitleArtwork(canvas,url,revision,onready,onfail){
  const probe=new Image();
  probe.onload=()=>{
    if(revision!==brandingRevision)return;
    try{if(!drawTitleArtwork(canvas,probe,url))throw new Error('Title artwork has no visible pixels');onready();}
    catch{onfail();}
  };
  probe.onerror=()=>{if(revision===brandingRevision)onfail();};probe.src=url;
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
  const cover=image.closest('.side-game-art'),fallback=document.getElementById('cover-placeholder'),credit=document.getElementById('cover-credit');
  const sidebarGame=document.getElementById('sidebar-game');
  const titleSlot=document.getElementById('game-title-slot'),titleHeading=document.getElementById('game-title-heading');
  document.getElementById('game-brand-line').textContent=[b.studio,b.subtitle].filter(Boolean).join(' · ');
  fallback.textContent=(target?.gameTitle||'GAME').split(/\s+/).slice(0,3).map(word=>word[0]).join('').toUpperCase();
  const coverUrl=localArtworkUrl(b.coverUrl),iconUrl=localArtworkUrl(b.iconUrl);
  const backgroundUrl=localArtworkUrl(b.backgroundUrl),overlayUrl=localArtworkUrl(b.overlayUrl);
  const backgroundReady=Boolean(backgroundUrl)&&backdrop.getAttribute('src')===backgroundUrl&&!backdrop.hidden&&!workspaceBackdrop.hidden;
  if(!backgroundReady)workspaceBackdrop.hidden=true;
  const preferredUrl=coverUrl||iconUrl,iconMode=!coverUrl&&Boolean(iconUrl);
  cover.classList.toggle('game-icon',iconMode);
  const showSidebarArtwork=loaded=>{
    const loadedIcon=Boolean(iconUrl)&&loaded===iconUrl;
    cover.classList.toggle('game-icon',loadedIcon);
    image.alt=target?(loadedIcon?`${target.gameTitle} game icon`:`${target.gameTitle} cover art`):'';
    image.dataset.preferred=preferredUrl;fallback.hidden=true;sidebarGame.classList.add('visually-hidden');
  };
  const showSidebarFallback=()=>{cover.classList.remove('game-icon');image.alt='';delete image.dataset.preferred;fallback.hidden=false;sidebarGame.classList.remove('visually-hidden');};
  const loadedUrl=image.getAttribute('src');
  if(preferredUrl&&image.dataset.preferred===preferredUrl&&[coverUrl,iconUrl].includes(loadedUrl)&&!image.hidden)showSidebarArtwork(loadedUrl);
  else{showSidebarFallback();loadArtwork(image,[coverUrl,iconUrl],revision,showSidebarArtwork,showSidebarFallback);}
  if(!backgroundReady)loadArtwork(backdrop,[backgroundUrl],revision,()=>{workspaceBackdrop.hidden=false;},()=>{workspaceBackdrop.hidden=true;});
  if(overlayUrl&&overlay.dataset.source===overlayUrl&&!overlay.hidden)setTitleArtworkMode(titleSlot,titleHeading,overlay,true);
  else{
    setTitleArtworkMode(titleSlot,titleHeading,overlay,false);
    if(overlayUrl)loadTitleArtwork(overlay,overlayUrl,revision,
      ()=>setTitleArtworkMode(titleSlot,titleHeading,overlay,true),
      ()=>setTitleArtworkMode(titleSlot,titleHeading,overlay,false));
  }
  const source=typeof b.source==='string'&&/^https?:\/\//.test(b.source)?b.source:'';
  credit.hidden=!source;
  if(source)credit.href=source;else credit.removeAttribute('href');
  document.getElementById('artwork-game-name').textContent=target?.gameTitle||'Select a game';
}

if(typeof document!=='undefined')document.addEventListener('DOMContentLoaded',()=>{
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

if(typeof module!=='undefined'&&module.exports)module.exports={localArtworkUrl,visibleAlphaBounds,setTitleArtworkMode};
