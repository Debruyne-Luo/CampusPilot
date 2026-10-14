import test from 'node:test';
import assert from 'node:assert/strict';
import {createMap} from '../backend/src/campuspilot/web_assets/v2/map.mjs';
const a={place_id:'synthetic:a',name:'合成地点 A',category:'service',hotspot:true,position:{longitude:104.14,latitude:30.67,coordinate_system:'GCJ02'}};
const b={...a,place_id:'synthetic:b',name:'合成地点 B',hotspot:false,category:'teaching'};
async function setup(t){
  const sent=[],timers=[];let receive;
  const frame={contentWindow:{postMessage:data=>sent.push(data)}};
  for(const [key,value] of Object.entries({window:{addEventListener:(_,fn)=>receive=fn},location:{origin:'https://test.invalid'},matchMedia:q=>({matches:q.includes('min-width')}),
    fetch:async()=>({json:async()=>({configured:true,key:'synthetic-only'})}),setTimeout:fn=>{timers.push(fn);return timers.length;}})){
    const before=globalThis[key];globalThis[key]=value;t.after(()=>{if(before===undefined)delete globalThis[key];else globalThis[key]=before;});
  }
  const api=createMap({frame,fallback:{},status(){},onSelect(){}});await api.init([a,b]);
  const generation=sent[0].frame_generation;
  const message=data=>receive({source:frame.contentWindow,origin:location.origin,data:{type:'campuspilot-map',frame_generation:generation,...data}});
  message({action:'ready'});sent.length=0;
  return {api,sent,timers,message};
}
test('answer/filter data never requests a desktop camera; an explicit filtered selection remains visible',async t=>{
  const {api,sent}=await setup(t);api.reveal([b.place_id]);api.setFilter('service');
  assert.ok(sent.every(m=>m.action==='places'&&m.fit===false));
  api.focus(b);assert.equal(sent.filter(m=>m.action==='center').length,1);
  assert.ok(sent.filter(m=>m.action==='places').at(-1).places.some(p=>p.place_id===b.place_id));
});
test('new selection settles the cancelled route; late results cannot resolve the replacement',async t=>{
  const {api,sent,message}=await setup(t);const first=api.route({place_id:a.place_id},a.position);
  const oldId=sent.at(-1).request_id;api.focus(b);assert.equal((await first).status,'cancelled');
  let settled=false;const second=api.route({place_id:b.place_id},a.position).then(x=>{settled=true;return x;});const newId=sent.at(-1).request_id;
  message({action:'route-result',request_id:oldId,status:'success'});await Promise.resolve();assert.equal(settled,false);
  message({action:'route-result',request_id:newId,status:'success'});assert.equal((await second).status,'success');
});
test('picking an origin cancels waiting route; timeout also settles and clears the frame',async t=>{
  const {api,sent,timers}=await setup(t);const first=api.route({place_id:a.place_id},a.position);api.pickOrigin();assert.equal((await first).status,'cancelled');
  const second=api.route({place_id:a.place_id},a.position);timers.at(-1)();assert.equal((await second).status,'error');assert.equal(sent.at(-1).action,'route-clear');
});
