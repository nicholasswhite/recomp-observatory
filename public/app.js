'use strict';
const $ = id => document.getElementById(id);
let current = null;
let unit = 'bytes';
let busy = false;
let lastSuccess = null;
const number = v => v == null ? '—' : Number(v).toLocaleString('en-US');
const escapeHtml = v => String(v ?? '—').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const size = v => {
  if (v == null) return '—';
  if (v < 1000) return `${number(v)} B`;
  const units = ['kB', 'MB', 'GB', 'TB']; let n = v / 1000, i = 0;
  while (n >= 1000 && i < 3) { n /= 1000; i++; }
  return `${n.toLocaleString('en-US', {maximumFractionDigits: n < 100 ? 2 : 1})} ${units[i]}`;
};
const percent = v => v == null ? '—' : Number(v).toFixed(1);
const time = v => v ? new Date(v).toLocaleString('en-US', {timeZone: 'America/New_York', month:'short', day:'numeric',hour:'numeric',minute:'2-digit',second:'2-digit'}) + ' ET' : 'Unknown';
const relative = v => {
  if (!v) return 'Unknown';
  const seconds = Math.max(0, (Date.now() - new Date(v)) / 1000);
  if (seconds < 60) return 'just now';
  if (seconds < 3600) return `${Math.floor(seconds/60)}m ago`;
  if (seconds < 86400) return `${Math.floor(seconds/3600)}h ago`;
  return `${Math.floor(seconds/86400)}d ago`;
};
const text = (id,v) => { $(id).textContent = v; };
const width = v => `${Math.max(0,Math.min(100,v || 0))}%`;
const sum = (...values) => values.some(v => v == null) ? null : values.reduce((a,b) => a+b,0);
const componentLabel = name => String(name || '').replaceAll('_',' ').replace(/\b(ppu|spu|rsx|gcm|dma|rpc|pcm|prx|hid|aac)\b/gi,word=>word.toUpperCase()).replace(/^./,letter=>letter.toUpperCase());

function renderMetrics(d) {
  const {ppu,spu,build,imports,recovery} = d;
  renderTarget(d);
  renderPs3Details(d);
  renderOverall(d);
  renderWorkPulse(d);
  text('ppu-percent',percent(ppu.emissionPercent));
  text('ppu-chunks',number(ppu.nativeChunks));
  text('ppu-covered',size(ppu.emittedSourceBytes));
  $('ppu-covered').title = `${number(ppu.emittedSourceBytes)} source bytes with supported emission`;
  text('ppu-remaining',size(ppu.unsupportedSourceBytes));
  $('ppu-remaining').title = `${number(ppu.unsupportedSourceBytes)} source bytes with explicit-failure emission`;
  $('ppu-bar').firstElementChild.style.width = width(ppu.emissionPercent);
  if (ppu.emissionPercent == null) $('ppu-bar').removeAttribute('aria-valuenow');
  else $('ppu-bar').setAttribute('aria-valuenow',ppu.emissionPercent);
  text('spu-percent', `${percent(spu.emissionPercent)}${spu.emissionPercent == null ? '' : '%'}`);
  $('spu-bar').style.width = width(spu.emissionPercent);
  text('spu-images', number(spu.imageCount)); text('spu-total',size(spu.sourceBytes));
  text('build-units',number(build.translationUnits)); text('exe-size',size(build.executableBytes));
  text('build-freshness',build.stale === true ? 'SOURCE CHANGED SINCE LINK' : build.stale === false ? 'CHECKED SOURCES MATCH' : 'FRESHNESS UNKNOWN');
  text('unresolved-count',number(imports.unresolvedCount));
  text('bound-imports',number(sum(imports.boundFunctions, imports.boundVariables)));
  text('input-size',size(recovery.recoveredBytes));
  text('load-segments',`${number(recovery.authenticatedLoadSegments)}/${number(recovery.totalNonemptyLoadSegments)}`);
  text('elf-status',recovery.completeElfRecovered === true ? 'Complete ELF recovery reported' : recovery.completeElfRecovered === false ? 'Whole-file identity not established' : 'Whole-file identity unknown');
  text('readiness-heading', build.gameComplete === true ? 'Completion reported' : build.gameComplete === false ? 'Port incomplete' : 'Readiness unverified');
  text('readiness-copy', !d.capabilities.translation ? 'This attempt has its own build and runtime evidence. Translation coverage is unavailable in this report format.' : build.available ? 'Code generation and a Windows link are recorded. Game boot, rendering, and playability require their own evidence.' : 'Waiting for a valid build report. Missing evidence is not interpreted as progress.');
  text('game-testing',build.testsRun === true ? 'Reported as run' : build.testsRun === false ? 'Deferred' : 'Unknown');
  text('updated',`Reports observed ${relative(d.collectedAt)}`);
  text('footer-time',`Observed ${time(d.collectedAt)} · ${Math.round(d.collectionMs)} ms collection`);
}

function successfulReceipts(d) {
  const receipts=[];
  for(const point of ProgressData.points(d)){
    if(!point.buildAt||typeof point.buildUnits!=='number'||!Number.isFinite(point.buildUnits))continue;
    if(!receipts.length||receipts.at(-1).buildAt!==point.buildAt)receipts.push(point);
    else receipts[receipts.length-1]=point;
  }
  return receipts;
}

function renderWorkPulse(d) {
  const panel=$('work-pulse'),supported=d.target?.adapter==='independent-reports-v1';
  panel.hidden=!supported;
  if(!supported)return;
  const b=d.build||{},state=b.workState||{},summary=b.componentSummary||{},receipts=successfulReceipts(d);
  const latest=receipts.at(-1),previous=receipts.at(-2);
  const stateCopy={
    'successful-receipt-current':['RECEIPT CURRENT','Latest successful receipt matches the observed source and report identities.'],
    'source-changed-receipt-pending':['RECEIPT PENDING','Native source or report inputs changed after the latest successful receipt.'],
    'freshness-unknown':['FRESHNESS UNKNOWN','A successful receipt exists, but its relationship to the current source could not be fully checked.'],
    unavailable:['NO RECEIPT','No compatible successful-build receipt is available.'],
  }[state.state]||['CHECKING','Build state is unavailable for this report reader.'];
  text('work-state',stateCopy[0]);
  text('work-pulse-summary',ProgressData.preferredMetric(d)==='build'?'Native work is advancing while recent translation-emission coverage is unchanged.':stateCopy[1]);
  text('work-link-state',state.state==='source-changed-receipt-pending'?'Matching receipt pending':state.state==='successful-receipt-current'?'Latest receipt is current':b.available?'Receipt freshness unverified':'No successful receipt');
  text('work-link-detail',state.state==='source-changed-receipt-pending'?`${number(state.changedSourceCount)} source/tool files changed after the ${time(b.linkedAt)} receipt.`:b.available?`${number(b.translationUnits)} units linked ${time(b.linkedAt)}.`:'Waiting for compatible build evidence.');
  if(latest&&previous){
    const delta=latest.buildUnits-previous.buildUnits,signed=`${delta>0?'+':''}${number(delta)}`;
    text('work-build-growth',delta===0?'Unit count unchanged':`${signed} translation unit${Math.abs(delta)===1?'':'s'}`);
    text('work-build-detail',`${number(previous.buildUnits)} → ${number(latest.buildUnits)} across the latest two successful receipts.`);
  } else if(latest){
    text('work-build-growth',`${number(latest.buildUnits)} linked units`);
    text('work-build-detail','A second distinct successful receipt is needed for a delta.');
  } else {
    text('work-build-growth','Unknown');text('work-build-detail','No successful build-unit history is available.');
  }
  if(summary.available){
    text('work-milestone-count',`${number(summary.trueCount)} met / ${number(summary.total)} declared`);
    text('work-milestone-detail',`${number(summary.falseCount)} flags remain unmet in this receipt. The declared scope can grow.`);
  } else {
    text('work-milestone-count','Unknown');text('work-milestone-detail','No compatible implementation-flag receipt is available.');
  }
  text('work-pulse-note',state.basis||'Build receipts and implementation flags are scoped evidence. They are not a whole-game completion percentage.');
}

function renderOverall(d) {
  const o = d.overall || {};
  text('overall-percent', percent(o.translationPercent));
  $('overall-bar').firstElementChild.style.width = width(o.translationPercent);
  if(o.translationPercent == null) $('overall-bar').removeAttribute('aria-valuenow');
  else $('overall-bar').setAttribute('aria-valuenow', o.translationPercent);
  text('overall-supported', size(o.supportedSourceBytes));
  text('overall-failures', size(o.failureSourceBytes));
  text('overall-counts', !d.capabilities.translation ? 'This report reader does not provide a supported translation denominator. Coverage remains unknown for this attempt.' : `${number(o.supportedWords)} / ${number(o.scannedWords)} scanned words have supported C++ emission · ${number(o.supportedSourceBytes)} / ${number(o.scannedSourceBytes)} source bytes`);
  const changed = [d.ppu,d.spu].some(m => m.generatorChangedSinceReport === true);
  const stages = [
    ['01','Source recovery', d.recovery.completeElfRecovered === true ? 'Complete ELF reported' : d.recovery.completeElfRecovered === false ? 'Partial identity verified' : 'Unknown', 'Load-segment authentication is recorded separately from whole-file identity.'],
    ['02','Source analysis', o.scannedWords == null ? 'Unknown' : `${size(o.scannedSourceBytes)} scanned`, 'Selected executable extents processed; readable-source decompilation has no separate coverage report.'],
    ['03','C++ translation', `${percent(o.translationPercent)}${o.translationPercent == null ? '' : '% supported'}${changed ? ' · generator changed' : ''}`, 'Supported emission across the PPU and SPU reports. Remaining words emit explicit failures.'],
    ['04','Windows build', d.build.available ? (d.build.stale === true ? 'Linked · newer edits' : d.build.stale === false ? 'Linked · subset checked' : 'Linked · freshness unknown') : 'Unverified', `${number(d.build.translationUnits)} translation units in the last successful receipt. A whole-port compile percentage is unavailable.`],
    ['05','Runtime / gameplay', d.build.gameRun === true ? 'Historical run recorded' : d.build.gameRun === false ? 'Execution deferred' : 'Unverified', 'Boot, graphics, sound, input and gameplay require execution evidence; no completion percentage is inferred.'],
  ];
  $('pipeline-stages').innerHTML = stages.map(([n,label,state,detail]) => `<div class="pipeline-stage"><span class="pipeline-number">${n}</span><h3>${label}</h3><strong>${escapeHtml(state)}</strong><p>${escapeHtml(detail)}</p></div>`).join('');
}

function renderTranslation(d) {
  $('translation-summary').innerHTML = [['PPU',d.ppu,'Main CPU + firmware'],['SPU',d.spu,'Identified SPU images']].map(([name,m,caption]) => {
    const covered = unit === 'bytes' ? m.emittedSourceBytes : m.implementedWords;
    const total = unit === 'bytes' ? m.sourceBytes : m.words;
    const label = unit === 'bytes' ? 'source bytes' : 'words';
    return `<div class="coverage-row"><div class="processor-name">${name}<small>${caption}</small></div><div><div class="processor-bar" role="progressbar" aria-label="${name} supported emission coverage" aria-valuemin="0" aria-valuemax="100" ${m.emissionPercent == null ? '' : `aria-valuenow="${m.emissionPercent}"`}><div style="width:${width(m.emissionPercent)}"></div></div><div class="processor-count">${number(covered)} / ${number(total)} ${label} with supported emission</div>${m.generatorChangedSinceReport ? '<div class="processor-count amber-text">Generator changed since this report</div>' : ''}</div><div class="processor-percent">${percent(m.emissionPercent)}${m.emissionPercent == null ? '' : '%'}</div></div>`;
  }).join('');
  text('module-count',`${number(d.modules.length)} IMAGES`);
  const total = d.modules.reduce((s,m) => s+(m.words||0),0);
  $('module-map').innerHTML = d.modules.map(m => `<span style="flex:${m.words || 0}" title="${escapeHtml(m.name)}: ${number(m.words)} words · ${total ? (m.words/total*100).toFixed(2) : '—'}% of PPU source volume"></span>`).join('');
  renderRawSpu(d);
  renderModules(); renderUnsupported();
}

function renderRawSpu(d) {
  const r=d.rawSpu||{},panel=$('raw-spu-report');
  panel.hidden=!r.available;
  if(!r.available)return;
  text('raw-spu-percent',percent(r.emissionPercent));
  text('raw-spu-supported',`${number(r.implementedWords)} / ${number(r.words)}`);
  text('raw-spu-failures',number(r.unsupportedWords));
  text('raw-spu-overlays',number(r.overlayCount));
  text('raw-spu-units',number(r.translationUnits));
  text('raw-spu-time',`Report observed ${time(r.generatedAt)}`);
  $('raw-spu-bar').firstElementChild.style.width=width(r.emissionPercent);
  if(r.emissionPercent==null)$('raw-spu-bar').removeAttribute('aria-valuenow');
  else $('raw-spu-bar').setAttribute('aria-valuenow',r.emissionPercent);
  text('raw-spu-basis',`${r.basis||'Raw SPU overlay report scope.'} It does not establish runtime correctness or game completion.`);
}

function renderModules() {
  if (!current) return;
  const query = $('module-search').value.toLowerCase().trim();
  const rows = current.modules.filter(m => m.name.toLowerCase().includes(query));
  const largest = Math.max(1,...current.modules.map(m => m.words || 0));
  $('module-table').innerHTML = rows.map(m => `<div class="list-row"><div><code>${escapeHtml(m.name)}</code><small>${m.kind === 'game' ? 'GAME' : 'FIRMWARE'}</small><div class="row-volume" style="width:${m.words/largest*190}px"></div></div><strong title="${number(m.sourceBytes)} bytes / ${number(m.words)} words">${unit === 'bytes' ? size(m.sourceBytes) : number(m.words)}</strong></div>`).join('') || '<div class="empty">No matching source images.</div>';
}

function renderUnsupported() {
  if (!current) return;
  const filter = $('processor-filter').value;
  const rows = current.unsupported.filter(row => filter === 'all' || row.processor === filter).slice(0,40);
  $('unsupported-list').innerHTML = rows.map(row => `<div class="unsupported-row"><div><small>${escapeHtml(row.processor)}</small> <code>${escapeHtml(row.name)}</code></div><strong title="${number(row.words)} source words">${unit === 'bytes' ? size(row.sourceBytes) : number(row.words)}</strong></div>`).join('') || '<div class="empty">No unsupported-class entries available.</div>';
}

function renderBuild(d) {
  const b = d.build;
  text('runtime-badge', b.testsRun === false ? 'UNTESTED' : 'REPORTED STATE');
  text('link-time',`Receipt modified ${time(b.linkedAt)}`);
  text('build-status', b.available ? (b.testsRun === false ? 'LINKED · UNTESTED' : 'LINK RECORDED') : 'NO BUILD REPORT');
  const elapsed = b.elapsedSeconds == null ? '—' : `${Math.floor(b.elapsedSeconds / 60)}m ${Math.round(b.elapsedSeconds % 60)}s`;
  $('build-details').innerHTML = [['Native executable',size(b.executableBytes)],['Build duration',elapsed],['Objects compiled',number(b.objectsCompiled)],['Objects reused',number(b.objectsReused)]].map(([label,value]) => `<div class="detail-item"><small>${label.toUpperCase()}</small><strong>${value}</strong></div>`).join('');
  const changes = b.changedRecordedSources || [];
  const mismatches = b.reportHashMismatches || [];
  let freshness = b.stale === true ? `${changes.length} recorded source files differ from the linked build. ${number(b.newerSourceCount)} source/tool files are newer than its receipt.` : b.stale === false ? `${number(b.recordedSourcesChecked)} recorded source files checked. No changes detected in the checked subset.` : 'Build freshness could not be established from the available evidence.';
  if(mismatches.length) freshness += ` ${mismatches.length} generation report identities changed.`;
  $('stale-detail').innerHTML = `<span class="info-icon">i</span><div>${escapeHtml(freshness)}<br><span class="muted">Generated game code and executable bytes are excluded from this bounded check.</span>${changes.length ? `<details><summary>Changed source files</summary><div class="chips">${changes.map(p => `<span>${escapeHtml(p)}</span>`).join('')}</div></details>` : ''}</div>`;
  $('remaining-work').innerHTML = b.remaining.map(item => `<span>${escapeHtml(item)}</span>`).join('') || '<span>No remaining-work list available</span>';
  const components = Object.fromEntries(b.components.map(c => [c.name,c.value]));
  const status = (v, yes, no) => v === true ? [yes,'reported'] : v === false ? [no,'missing'] : ['Unknown','state'];
  const runtime = [
    ['Firmware initialization', ...status(components.firmware_modules_initialized,'Reported initialized','Not initialized')],
    ['SPU group execution', ...status(components.spu_group_execution_integrated,'Reported integrated','Not integrated')],
    ['RSX renderer integration', ...status(components.rsx_renderer_integrated,'Reported integrated','Not integrated')],
    ['Graphics device', ...status(components.native_graphics_device_initialized,'Reported initialized','Not initialized')],
    ['Audio endpoint', ...status(components.native_audio_endpoint_initialized,'Reported initialized','Not initialized')],
    ['Native window', ...status(components.native_window_created,'Reported created','Not created')],
    ['Game execution', ...status(b.gameRun,'Reported run; outcome separate','Not run')],
    ['Gameplay / FPS', d.recordedRuntime ? `${d.recordedRuntime.fps.toFixed(2)} FPS · historical sample` : 'Not measured','state'],
  ];
  const runtimeRows=d.ps3Metrics?d.ps3Metrics.milestones.map(row=>[row.name,row.state,'state']):runtime;
  $('runtime-list').innerHTML = runtimeRows.map(([label,value,cls]) => `<div class="runtime-row"><span>${label}</span><strong class="${cls}">${value}</strong></div>`).join('');
  renderImplementationReceipt(d);
  text('unresolved-summary',`${number(d.imports.unresolvedCount)} symbols`);
  $('unresolved-table').innerHTML = d.imports.unresolved.map(r => `<tr><td>${escapeHtml(r.library)}</td><td><code>${escapeHtml(r.importer)}</code></td><td>${escapeHtml(r.kind)}<br><code>${escapeHtml(r.nid)}</code></td><td>${escapeHtml(r.reason)}</td></tr>`).join('') || '<tr><td colspan="4">No unresolved import details available.</td></tr>';
}

function renderImplementationReceipt(d) {
  const b=d.build||{},summary=b.componentSummary||{},panel=$('implementation-receipt');
  panel.hidden=!summary.available;
  if(!summary.available)return;
  text('implementation-count',`${number(summary.trueCount)} MET / ${number(summary.total)} DECLARED`);
  const events=(b.milestoneHistory||[]).filter(row=>!row.baseline&&((row.newlyTrue||[]).length||(row.newlyFalse||[]).length)).slice(-4).reverse();
  $('implementation-milestones').innerHTML=events.map(row=>{
    const becameTrue=(row.newlyTrue||[]),becameFalse=(row.newlyFalse||[]),visibleTrue=becameTrue.slice(0,10),visibleFalse=becameFalse.slice(0,6);
    const chips=[...visibleTrue.map(name=>`<span class="milestone-chip" title="${escapeHtml(name)}">＋ ${escapeHtml(componentLabel(name))}</span>`),...visibleFalse.map(name=>`<span class="milestone-chip regressed" title="${escapeHtml(name)}">− ${escapeHtml(componentLabel(name))}</span>`)];
    const hiddenCount=becameTrue.length-visibleTrue.length+becameFalse.length-visibleFalse.length;
    if(hiddenCount>0)chips.push(`<span class="milestone-chip more">＋ ${number(hiddenCount)} more changes</span>`);
    return `<div class="milestone-event" role="listitem"><div><strong>${number(row.translationUnits)}-unit receipt</strong><small>${escapeHtml(time(row.at))}</small></div><div class="milestone-chips">${chips.join('')}</div></div>`;
  }).join('')||'<div class="empty">No comparable earlier receipt is available for a milestone transition. The latest declared counts are still shown above.</div>';
  text('implementation-note',`${summary.basis||'Boolean evidence declared by the latest build receipt.'} “Met” means the receipt flag is true; it does not prove runtime behavior, playability, or completion.`);
}

function renderActivity(d) {
  $('activity-list').innerHTML = d.activity.slice(0,16).map(row => `<div class="activity-row"><span class="activity-marker"></span><div class="activity-name"><code>${escapeHtml(row.path)}</code><small>${escapeHtml(({src:'Native source',tools:'Build / translation tooling',docs:'Implementation notes',reports:'Evidence report'})[row.category] || row.category)} · ${size(row.size)}</small></div><span class="activity-time" title="${escapeHtml(time(row.modifiedAt))}">${relative(row.modifiedAt)}</span></div>`).join('') || '<div class="empty">No source-file activity available.</div>';
  const history = ProgressData.changeEvents(ProgressData.points(d));
  if (history.length <= 1) {
    $('history').innerHTML = `<div class="empty-chart"><strong>First observation captured</strong><p>New points appear when coverage, unresolved imports, or the successful build receipt changes. No history is invented.</p><small class="muted">Since ${time(d.monitor.historyStartedAt)}</small></div>`;
  } else {
    const start=Math.max(0,history.length-9),visible=history.slice(start).map((point,index)=>({point,previous:history[start+index-1]})).reverse();
    $('history').innerHTML = visible.map(({point:h,previous}) => {
      const buildChanged=previous&&(h.buildAt!==previous.buildAt||h.buildUnits!==previous.buildUnits);
      const emissionChanged=previous&&(h.ppu!==previous.ppu||h.spu!==previous.spu);
      const rawSpuChanged=previous&&h.rawSpu!==previous.rawSpu;
      const importsChanged=previous&&h.unresolved!==previous.unresolved;
      let headline='First recorded observation';
      if(buildChanged){const delta=typeof h.buildUnits==='number'&&typeof previous.buildUnits==='number'?h.buildUnits-previous.buildUnits:null;headline=`Successful link · ${number(h.buildUnits)} units${delta==null?'':delta===0?' · unit count unchanged':` (${delta>0?'+':''}${number(delta)})`}`;}
      else if(emissionChanged)headline='Emission report changed';
      else if(rawSpuChanged)headline=previous.rawSpu==null?'Raw SPU scope observed':'Raw SPU report changed';
      else if(importsChanged)headline='Import inventory changed';
      const component=typeof h.componentTrue==='number'?` · ${number(h.componentTrue)}/${number(h.componentTotal)} flags met`:'';
      return `<div class="history-row progress-event"><span>${time(h.at)}</span><span><strong>${escapeHtml(headline)}</strong><br><small>PPU ${size(h.ppu)} · SPU ${size(h.spu)} · ${number(h.unresolved)} imports${component}</small></span></div>`;
    }).join('');
  }
  const a=d.assets;
  $('asset-details').innerHTML = [[number(a.archiveCount),'archives indexed'],[number(a.archiveNames),'archive names'],[size(a.sourceBytes),'inventoried source tree']].map(([value,label]) => `<div><strong>${value}</strong><small>${label}</small></div>`).join('');
}

function renderEvidence(d) {
  $('evidence-table').innerHTML = d.evidence.map(row => `<tr><td title="${escapeHtml(d.sourceRoot+'\\'+row.path)}"><code>${escapeHtml(row.path)}</code></td><td>${time(row.modifiedAt)}</td><td>${size(row.size)}</td><td class="${row.status === 'ok' ? '' : 'amber-text'}" title="${escapeHtml(row.error || 'Read successfully')}">${row.status === 'ok' ? 'Read successfully' : escapeHtml(row.status)}</td></tr>`).join('');
  const errors = d.errors || [];
  $('error-banner').hidden = !errors.length;
  if (errors.length) text('error-banner',`${errors.length} evidence source(s) are unavailable or incomplete. Affected metrics remain unknown. ${errors[0].path}: ${errors[0].message}`);
}

let requestSerial=0;
async function refresh(force=false) {
  if (!wsTarget || (busy && !force)) return;
  const generation=wsGeneration, serial=++requestSerial, target=wsTarget;
  busy = true;
  $('refresh').disabled = true;
  try {
    const response = await fetch(`/api/snapshot?target=${encodeURIComponent(target)}`, {cache:'no-store',signal:AbortSignal.timeout(15000)});
    if (!response.ok) throw new Error(`HTTP ${response.status}`);
    const data = await response.json();
    if (data.schemaVersion !== 1) throw new Error('Unsupported telemetry format');
    if(generation!==wsGeneration || serial!==requestSerial) return;
    if(data.target.id!==target) throw new Error('Target mismatch');
    current = data;
    renderMetrics(data); renderTranslation(data); renderBuild(data); renderActivity(data); renderEvidence(data); renderProgressGraph(data);
    $('target-content').hidden=false;
    text('selection-status', `${data.target.gameTitle} / ${data.target.title} · ${data.sourceRoot}`);
    lastSuccess = Date.now();
    text('connection','Live · 5s');
    $('connection-dot').classList.remove('offline');
  } catch (error) {
    if(generation!==wsGeneration || serial!==requestSerial) return;
    text('selection-status', `Selected target unavailable: ${error.message}`);
    text('connection','Disconnected');
    $('connection-dot').classList.add('offline');
    $('error-banner').hidden=false;
    text('error-banner',`Local observer unavailable (${error.message}). ${lastSuccess ? 'Displayed values are the last successful observation. ' : ''}Open Start Dashboard.cmd to start the server.`);
  } finally {
    if(serial===requestSerial) {busy = false; $('refresh').disabled = false;}
  }
}

$('refresh').addEventListener('click',()=>refresh(true));
$('module-search').addEventListener('input',renderModules);
$('processor-filter').addEventListener('change',renderUnsupported);
document.querySelectorAll('[data-unit]').forEach(button => button.addEventListener('click',() => {
  unit = button.dataset.unit;
  document.querySelectorAll('[data-unit]').forEach(b => { b.classList.toggle('selected',b===button); b.setAttribute('aria-pressed',String(b===button)); });
  if (current) renderTranslation(current);
}));
$('export').addEventListener('click',() => {
  if (!current) return;
  const shared={schemaVersion:1,collectedAt:current.collectedAt,
    target:{id:current.target.id,gameTitle:current.target.gameTitle,title:current.target.title,toolchain:current.target.toolchain,adapter:current.target.adapter},
    ppu:{words:current.ppu.words,supportedWords:current.ppu.implementedWords,emissionPercent:current.ppu.emissionPercent},
    spu:{words:current.spu.words,supportedWords:current.spu.implementedWords,emissionPercent:current.spu.emissionPercent},
    rawSpu:current.rawSpu?.available?{words:current.rawSpu.words,supportedWords:current.rawSpu.implementedWords,emissionPercent:current.rawSpu.emissionPercent,overlayCount:current.rawSpu.overlayCount,includedInOverall:false}:null,
    overall:current.overall,
    build:{available:current.build.available,status:current.build.status,linkedAt:current.build.linkedAt,translationUnits:current.build.translationUnits,stale:current.build.stale,testsRun:current.build.testsRun,gameRun:current.build.gameRun,workState:current.build.workState,componentSummary:current.build.componentSummary,milestoneHistory:current.build.milestoneHistory},
    unresolvedImports:current.imports.unresolvedCount,recordedRuntime:current.recordedRuntime||null,
    ps3Metrics:current.ps3Metrics?Object.fromEntries(Object.entries(current.ps3Metrics).filter(([k])=>!['evidence','errors'].includes(k))):null,
    evidence:current.evidence.map(row=>({name:row.name,modifiedAt:row.modifiedAt,status:row.status})),history:current.history};
  const blob = new Blob([JSON.stringify(shared,null,2)],{type:'application/json'});
  const url=URL.createObjectURL(blob), link=document.createElement('a');
  link.href=url; link.download=`${wsTarget}-progress-${new Date().toISOString().replace(/[:.]/g,'-')}.json`;link.click();
  setTimeout(() => URL.revokeObjectURL(url),1000);
});
const observer = new IntersectionObserver(entries => {
  const visible=entries.filter(e=>e.isIntersecting).sort((a,b)=>a.boundingClientRect.top-b.boundingClientRect.top)[0];
  if(visible) document.querySelectorAll('nav a').forEach(a=>a.classList.toggle('active',a.hash === `#${visible.target.id}`));
},{rootMargin:'-5% 0px -70% 0px'});
document.querySelectorAll('#target-content>.section').forEach(s=>observer.observe(s));
let savedTarget;try {savedTarget=localStorage.getItem('observatory-target');}catch{}
initializeWorkspace(savedTarget).catch(error=>text('selection-status',error.message));
setInterval(()=>refresh(),5000);
