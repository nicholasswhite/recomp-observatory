const assert=require('node:assert/strict');
const {performance}=require('node:perf_hooks');
const P=require('./public/progress.js');
assert.equal(P.value({ppu:80,spu:20},'bytes','combined'),100);
assert.equal(P.value({ppu:80,spu:20},'percent','combined'),null);
assert.equal(P.value({ppu:80,spu:null},'bytes','combined'),null);
assert.equal(P.value({ppu:80,spu:20,ppuTotal:100,spuTotal:100},'percent','combined'),50);
assert.equal(P.value({ppu:120,ppuTotal:100},'percent','ppu'),null);
assert.equal(P.value({ppu:NaN},'bytes','ppu'),null);
assert.equal(P.value({unresolved:0},'imports','imports'),0);
assert.equal(P.value({ppuFunctions:4,spuFunctions:6},'functions','combined'),10);
assert.equal(P.value({ppuFunctions:4},'functions','combined'),null);
assert.equal(P.value({ppuFunctions:4},'functions','ppu'),4);
const old={at:'2026-01-01T00:00:00Z',ppu:10,spu:10};
const snapshot={collectedAt:'2026-01-01T01:00:00Z',history:[old],ppu:{emittedSourceBytes:11,sourceBytes:20},spu:{emittedSourceBytes:10,sourceBytes:20},imports:{unresolvedCount:0},build:{translationUnits:5,linkedAt:'2026-01-01T01:00:00Z'}};
const points=P.points(snapshot);
assert.equal(points.length,2);assert.equal(P.value(points[0],'percent','combined'),null);
assert.equal(P.value(points[1],'percent','combined'),52.5);
assert.equal(old.ppuTotal,undefined); // No backfilled historical denominators.
const enriched=P.points({...snapshot,rawSpu:{emittedSourceBytes:30,sourceBytes:40},build:{...snapshot.build,componentSummary:{trueCount:7,total:9}}}).at(-1);
assert.equal(enriched.rawSpu,30);assert.equal(enriched.rawSpuTotal,40);assert.equal(enriched.componentTrue,7);assert.equal(enriched.componentTotal,9);
const heartbeatRows=[
  {at:'2026-01-01T00:00:00Z',ppu:10,spu:20,unresolved:3,buildAt:'2026-01-01T00:00:00Z',buildUnits:100},
  {at:'2026-01-01T00:01:00Z',ppu:10,spu:20,unresolved:3,buildAt:'2026-01-01T00:00:00Z',buildUnits:100},
  {at:'2026-01-01T00:02:00Z',ppu:10,spu:20,unresolved:3,buildAt:'2026-01-01T00:02:00Z',buildUnits:102},
  {at:'2026-01-01T00:03:00Z',ppu:11,spu:20,unresolved:3,buildAt:'2026-01-01T00:02:00Z',buildUnits:102},
  {at:'2026-01-01T00:04:00Z',ppu:11,spu:20,unresolved:2,buildAt:'2026-01-01T00:02:00Z',buildUnits:102},
];
const events=P.changeEvents(heartbeatRows);
assert.equal(events.length,4);assert.equal(events[1].buildUnits,102);assert.equal(events[2].ppu,11);assert.equal(events[3].unresolved,2);
assert.deepEqual(P.changeEvents(heartbeatRows,2),events.slice(-2));
const flatEmission={collectedAt:'2026-01-01T03:00:00Z',history:heartbeatRows,ppu:{emittedSourceBytes:11,sourceBytes:20},spu:{emittedSourceBytes:20,sourceBytes:40},imports:{unresolvedCount:2},build:{translationUnits:102,linkedAt:'2026-01-01T00:02:00Z'}};
assert.equal(P.preferredMetric(flatEmission),'bytes'); // PPU changed in the same recent window.
const buildOnly={...flatEmission,history:heartbeatRows.slice(0,3).map(row=>({...row,ppu:10,spu:20})),ppu:{emittedSourceBytes:10,sourceBytes:20}};
assert.equal(P.preferredMetric(buildOnly),'build');
const rows=Array.from({length:10080},(_,i)=>({at:new Date(i*60000).toISOString(),ppu:500,spu:400,ppuTotal:1000,spuTotal:1000,unresolved:20,buildUnits:30}));
rows[5021].ppu=5;rows[5099].spu=999;
const start=performance.now(),reduced=P.thin(rows),elapsed=performance.now()-start;
assert.ok(reduced.length<=500);assert.ok(reduced.includes(rows[5021]));assert.ok(reduced.includes(rows[5099]));
assert.equal(reduced[0],rows[0]);assert.equal(reduced.at(-1),rows.at(-1));
console.log(`Progress graph checks passed; ${rows.length} observations -> ${reduced.length} points in ${elapsed.toFixed(1)} ms.`);
