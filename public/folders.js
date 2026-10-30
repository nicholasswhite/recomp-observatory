'use strict';

document.addEventListener('DOMContentLoaded',()=>{
  const el=id=>document.getElementById(id),dialog=el('folder-dialog');
  let current=null,generation=0,loading=false;
  const folderIcon='<svg viewBox="0 0 24 24" aria-hidden="true" fill="none" stroke="currentColor" stroke-width="1.4"><path d="M3 7V5h6l2 2h10v13H3Z"/><path d="M3 10h18"/></svg>';
  function folderButton(folder,shortcut=false){
    const button=document.createElement('button');button.type='button';button.className=shortcut?'folder-shortcut':'folder-entry';
    button.innerHTML=folderIcon;
    const name=document.createElement('span');name.textContent=folder.name;button.append(name);
    button.title=folder.path;button.setAttribute('aria-label',`Open folder ${folder.name}`);
    if(shortcut&&folder.path===current?.path)button.setAttribute('aria-current','location');
    button.addEventListener('click',()=>load(folder.path));return button;
  }
  function render(){
    const query=el('folder-filter').value.trim().toLocaleLowerCase();
    const folders=(current?.folders||[]).filter(f=>f.name.toLocaleLowerCase().includes(query));
    el('folder-list').replaceChildren(...folders.map(f=>folderButton(f)));
    if(!folders.length){const empty=document.createElement('p');empty.className='folder-empty';empty.textContent=query?'No folders match this filter.':'No subfolders here. You can use this folder.';el('folder-list').append(empty);}
    el('folder-status').textContent=`${folders.length.toLocaleString()} folder${folders.length===1?'':'s'}${query?' matching your filter':''}.${current?.truncated?' This location is large; open a subfolder or enter a more specific path.':''}`;
  }
  async function load(path){
    const request=++generation;loading=true;el('folder-select').disabled=true;el('folder-up').disabled=true;
    el('folder-status').textContent='Loading folders…';el('folder-list').setAttribute('aria-busy','true');
    try{
      const result=await wsPost('/api/folders',{path:path||null});
      if(request!==generation||!dialog.open)return;
      current=result;el('folder-location').value=result.path;el('folder-selected-path').textContent=result.path;
      el('folder-filter').value='';el('folder-shortcuts').replaceChildren(...result.shortcuts.map(f=>folderButton(f,true)));
      render();el('folder-up').disabled=!result.parent;el('folder-select').disabled=false;
    }catch(error){if(request===generation&&dialog.open)el('folder-status').textContent=error.message;}
    finally{if(request===generation){loading=false;el('folder-list').removeAttribute('aria-busy');}}
  }
  el('browse-folders').addEventListener('click',()=>{
    dialog.showModal();load(el('repo-path').value.trim()||current?.path||null);
  });
  el('folder-location-form').addEventListener('submit',event=>{event.preventDefault();load(el('folder-location').value.trim());});
  el('folder-up').addEventListener('click',()=>{if(current?.parent)load(current.parent);});
  el('folder-filter').addEventListener('input',()=>{if(!loading&&current)render();});
  ['folder-close','folder-cancel'].forEach(id=>el(id).addEventListener('click',()=>dialog.close()));
  dialog.addEventListener('close',()=>{generation++;loading=false;});
  el('folder-select').addEventListener('click',()=>{
    if(loading||!current||el('folder-select').disabled)return;
    el('repo-path').value=current.path;dialog.close();el('repo-path').focus();
  });
});
