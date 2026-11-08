const test = require('node:test');
const assert = require('node:assert/strict');
const MapAssets = require('./map-assets.js');
const tick = () => new Promise(setImmediate);
function fixture(load) {
 const ready=[], writes=[], removed=[];
 const manager=new MapAssets({mobile:false, manifest:async map=>({map,paks:[{name:'core',size:1},{name:map,size:1}]}),
   load:load || (async () => new Uint8Array(1)), mount:(n)=>writes.push(n), unmount:n=>removed.push(n),
   progress:()=>{}, ready:(...args)=>ready.push(args), error:()=>{}});
 return {manager,ready,writes,removed};
}
test('downloads only missing packages and removes old map files after success',async()=>{
 const f=fixture(); f.manager.seed('old',[{name:'core'},{name:'old'}]);
 assert.equal(f.manager.request('new',1),false); await tick();
 assert.deepEqual(f.writes,['new']); assert.deepEqual(f.removed,['old']);
 assert.deepEqual(f.ready,[[1,true]]); assert.equal(f.manager.request('new',2),2);
 f.manager.indexed('new'); assert.equal(f.manager.request('new',3),true);
});
test('same-map gamestate updates keep one download and use the latest ticket',async()=>{
 let resolve;let calls=0; const f=fixture(()=>{calls++;return new Promise(r=>resolve=r)});
 f.manager.seed('old',[{name:'core'},{name:'old'}]);
 f.manager.request('new',1);await tick();f.manager.request('new',2);resolve(new Uint8Array(1));await tick();
 assert.equal(calls,1);assert.deepEqual(f.ready,[[2,true]]);
});
test('superseded downloads cannot mount or resume the wrong map',async()=>{
 let resolve;const f=fixture(()=>new Promise(r=>resolve=r));f.manager.seed('old',[{name:'core'},{name:'old'}]);
 f.manager.request('new',1);await tick();assert.equal(f.manager.request('old',2),true);
 resolve(new Uint8Array(1));await tick();assert.deepEqual(f.ready,[]);assert.deepEqual(f.writes,[]);
});
test('failure keeps old packages intact and permits retry',async()=>{
 let fail=true;const f=fixture(async()=>{if(fail)throw Error('network');return new Uint8Array(1)});
 f.manager.seed('old',[{name:'core'},{name:'old'}]);f.manager.request('new',1);await tick();
 assert.deepEqual(f.removed,[]);assert.deepEqual(f.ready,[[1,false]]);
 fail=false;f.manager.request('new',2);await tick();assert.deepEqual(f.ready,[[1,false],[2,true]]);
});

test('disconnect cancels a pending mount and invalidates stale completion',async()=>{
 let resolve;const f=fixture(()=>new Promise(r=>resolve=r));f.manager.seed('old',[{name:'core'}]);
 f.manager.request('new',4);await tick();f.manager.cancel(4);resolve(new Uint8Array(1));await tick();
 assert.deepEqual(f.ready,[]);assert.deepEqual(f.writes,[]);
});
