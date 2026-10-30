'use strict';
let brandingTarget=null;
function renderGameBranding(target){
  brandingTarget=target||null;
  const b=target?.branding||{}, image=document.getElementById('game-cover'),backdrop=document.getElementById('game-backdrop');
  const cover=image.closest('.game-cover'),fallback=document.getElementById('cover-placeholder'),credit=document.getElementById('cover-credit');
  document.getElementById('game-brand-line').textContent=[b.studio,b.subtitle].filter(Boolean).join(' · ');
  fallback.textContent=(target?.gameTitle||'GAME').split(/\s+/).slice(0,3).map(w=>w[0]).join('').toUpperCase();
  const url=typeof b.coverUrl==='string'&&b.coverUrl.startsWith('/artwork/')?b.coverUrl:'';
  cover.classList.remove('cropped-case');
  image.hidden=true;backdrop.hidden=true;fallback.hidden=false;
  if(url){
    image.alt=`${target.gameTitle} cover art`;
    image.onload=()=>{if(image.getAttribute('src')===url){image.hidden=false;fallback.hidden=true;}};
    image.onerror=()=>{image.hidden=true;fallback.hidden=false;backdrop.hidden=true;};
    image.src=url;backdrop.src=url;backdrop.hidden=false;
    if(image.complete&&image.naturalWidth){image.hidden=false;fallback.hidden=true;}
  }else{image.removeAttribute('src');backdrop.removeAttribute('src');image.alt='';}
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
      const b=brandingTarget?.branding||{};
      el('brand-studio').value=b.studio||'';el('brand-subtitle').value=b.subtitle||'';el('brand-source').value=b.source||'';
      el('brand-cover-file').value='';el('artwork-message').textContent='Settings apply to every attempt for this game.';
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
