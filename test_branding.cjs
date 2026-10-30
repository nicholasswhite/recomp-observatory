'use strict';
const assert=require('node:assert/strict');
const {localArtworkUrl,visibleAlphaBounds,setTitleArtworkMode}=require('./public/branding.js');

const digest='a'.repeat(64);
assert.equal(localArtworkUrl(`/artwork/auto/${digest}.png`),`/artwork/auto/${digest}.png`);
assert.equal(localArtworkUrl(`/artwork/custom/${digest}.webp`),`/artwork/custom/${digest}.webp`);
assert.equal(localArtworkUrl('https://example.com/title.png'),'');
assert.equal(localArtworkUrl('/artwork/auto/../../title.png'),'');

const pixels=new Uint8ClampedArray(4*3*4);
assert.equal(visibleAlphaBounds(pixels,4,3),null);
pixels[(1+1*4)*4+3]=3;
pixels[(3+2*4)*4+3]=255;
assert.deepEqual(visibleAlphaBounds(pixels,4,3),{x:1,y:1,width:3,height:2});
assert.equal(visibleAlphaBounds(pixels,0,3),null);

function classTarget(){
  const values=new Set();
  return {values,toggle(name,enabled){if(enabled)values.add(name);else values.delete(name);}};
}
const slotClasses=classTarget(),headingClasses=classTarget();
const slot={classList:slotClasses},heading={classList:headingClasses};
const canvas={hidden:true,dataset:{source:'/artwork/auto/title.png'},removeAttribute(name){if(name==='data-source')delete this.dataset.source;}};
setTitleArtworkMode(slot,heading,canvas,true);
assert.equal(canvas.hidden,false);
assert.equal(slotClasses.values.has('has-title-art'),true);
assert.equal(headingClasses.values.has('visually-hidden'),true);
setTitleArtworkMode(slot,heading,canvas,false);
assert.equal(canvas.hidden,true);
assert.equal(slotClasses.values.has('has-title-art'),false);
assert.equal(headingClasses.values.has('visually-hidden'),false);
assert.equal(canvas.dataset.source,undefined);

console.log('branding title-art checks passed');
