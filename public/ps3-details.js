'use strict';
function renderPs3Details(d){
  const panel=document.getElementById('ps3-details'),m=d.ps3Metrics;
  panel.hidden=!m;
  document.querySelector('[href="#ps3-details"]').hidden=!m;
  if(!m)return;
  const p=m.ppu,s=m.spu,f=m.freshness,imports=m.imports;
  const n=v=>v==null?'Unknown':Number(v).toLocaleString('en-US');
  const e=v=>String(v??'Unknown').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
  document.getElementById('ps3-audit-time').textContent=`Observed ${time(m.observedAt)} · scan ${Math.round(m.scanMs)} ms`;
  document.getElementById('ps3-ppu-mapping').textContent=p.mappingPercent==null?'Unknown':p.mappingPercent.toFixed(2)+'%';
  document.getElementById('ps3-ppu-counts').textContent=`${n(p.matchedEntries)} / ${n(p.originalEntries)} original entries have a generated definition`;
  document.getElementById('ps3-ppu-notes').textContent=`${n(p.generatedFunctions)} total definitions · ${n(p.extraDefinitions)} additional definitions · ${n(p.generatedFiles)} generated C++ files. Instruction semantics are unverified.`;
  document.getElementById('ps3-todos').textContent=n(p.todoCount);
  document.getElementById('ps3-todo-notes').textContent=`TODO comments by kind: ${Object.entries(p.todoByKind).map(([k,v])=>`${k}: ${n(v)}`).join(', ')||'None counted'}. Data and padding may be included. Comment-only trap sites: ${n(p.commentOnlyByKind.trap)}; mtfsf sites: ${n(p.commentOnlyByKind.mtfsf)}. These are not proven supported implementations.`;
  document.getElementById('ps3-spu-counts').textContent=`${n(s.generatedFunctions)} definitions across ${n(s.generatedPrograms)} generated SPU sources`;
  document.getElementById('ps3-spu-notes').textContent=`${n(s.programsWithInventories)} sources have matching original inventories. In that subset, ${n(s.mappedSubsetMatches)} / ${n(s.mappedSubsetEntries)} entries match. Missing inventories prevent a full SPU mapping percentage.`;
  document.getElementById('ps3-build-identity').textContent=`${n(f.checkedFiles)} recorded project source hashes checked · ${n(f.changedFiles.length)} changed · ${n(f.unavailableFiles.length)} unavailable · ${n(f.excludedFiles)} excluded`;
  document.getElementById('ps3-build-scope').textContent=f.basis;
  document.getElementById('ps3-imports-summary').innerHTML=imports?`<strong>${n(imports.total)} original imports · ${n(imports.unresolvedCount)} unresolved in the recorded audit</strong><p>${n(imports.providers.hle)} HLE providers · ${n(imports.providers.native_prx)} native PRX providers. Audit: ${e(time(imports.recordedAt))}. ${imports.matchesSelectedBuild?'Executable identity matches the selected build.':'Different executable identity from the selected build: this is historical evidence, not current service coverage.'}</p>`:'No compatible service audit is available.';
  const old=m.historicalAudit;
  document.getElementById('ps3-old-audit').textContent=old.recordedAt?`Prior PPU audit: ${time(old.recordedAt)}; ${n(old.functions)} functions and ${n(old.todos)} TODOs. ${n(old.newerGeneratedFiles)} generated files are newer. The figures above come from a fresh read-only scan.`:'No prior PPU audit is available.';
  document.getElementById('ps3-spu-table').innerHTML=s.programs.map(row=>`<tr><td>${e(row.name)}</td><td>${n(row.generatedFunctions)}</td><td>${n(row.originalEntries)}</td><td>${n(row.matchedEntries)}</td><td>${row.inventoryAvailable?'Inventory found':'Inventory unavailable'}</td></tr>`).join('');
}
