import test from 'node:test';
import assert from 'node:assert/strict';
import vm from 'node:vm';
import {readFileSync} from 'node:fs';

const source=readFileSync(new URL('../backend/src/campuspilot/web_assets/map-frame.js',import.meta.url),'utf8');
const point=(longitude=104.15)=>({longitude,latitude:30.67,coordinate_system:'GCJ02'});
function harness(){
  let receive;const moves=[],fits=[],parent={postMessage(){}};
  const fakeMap={getSize:()=>({getHeight:()=>836,getWidth:()=>1048}),getZoom:()=>17,getCenter:()=>[104.14,30.67],
    setZoomAndCenter:(...args)=>moves.push(args),getFitZoomAndCenterByBounds:(bounds,edges,zoom)=>{fits.push({bounds,edges});return [zoom,bounds.a];},
    getFitZoomAndCenterByOverlays:(_,edges)=>{fits.push({edges});return [16,[104.15,30.67]];},resize(){},remove(){}};
  const context=vm.createContext({window:{addEventListener:(name,fn)=>{if(name==='message')receive=fn;}},parent,location:{origin:'https://test.invalid'},
    matchMedia:()=>({matches:false}),performance:{now:()=>100},cancelAnimationFrame(){},setTimeout,clearTimeout,
    document:{body:{dataset:{}}},AMap:{Bounds:class{constructor(a,b){this.a=a;this.b=b;}}},fakeMap});
  vm.runInContext(source+'\nmap=fakeMap;started=true;frameGeneration=7;desktopMode=true;reduceMotion=true;globalThis.manual=manualCamera;globalThis.getMode=()=>cameraMode;globalThis.route=()=>{routeLayers=[{}];};',context);
  const send=(data,override={})=>receive({origin:'https://test.invalid',source:parent,data:{type:'campuspilot-map',frame_generation:7,...data},...override});
  return {send,moves,fits,context};
}
test('desktop explicit place uses one final fit, four insets and reduced-motion instant camera',()=>{
  const h=harness();h.send({action:'viewport-insets',top:136,bottom:240,left:32,right:48});
  h.send({action:'center',position:point(),operation_id:1});
  assert.equal(h.moves.length,1);assert.deepEqual(Array.from(h.fits[0].edges),[136,240,32,48]);assert.equal(h.moves[0][2],true);assert.equal(h.moves[0][3],0);
});
test('layout changes defer only the latest explicit camera, then perform exactly once',()=>{
  const h=harness();h.send({action:'layout',changing:true});
  h.send({action:'center',position:point(104.14),operation_id:1});h.send({action:'center',position:point(104.16),operation_id:2});
  assert.equal(h.moves.length,0);h.send({action:'layout',changing:false});assert.equal(h.moves.length,1);
  assert.ok(Math.abs(h.moves[0][1][0]-104.16)<.0001);
  h.send({action:'layout',changing:true});h.send({action:'layout',changing:false});h.send({action:'resize'});assert.equal(h.moves.length,1);
});
test('drag cancels deferred camera and resize/inset messages never reclaim ownership',()=>{
  const h=harness();h.send({action:'layout',changing:true});h.send({action:'center',position:point(),operation_id:3});h.context.manual();
  h.send({action:'layout',changing:false});h.send({action:'viewport-insets',bottom:320});h.send({action:'resize'});
  assert.equal(h.moves.length,0);assert.equal(h.context.getMode(),'manual');
  h.context.route();h.send({action:'overview',operation_id:4});assert.equal(h.moves.length,1);assert.equal(h.context.getMode(),'route');
});
test('stale operations and untrusted frame messages cannot move the camera',()=>{
  const h=harness();h.send({action:'center',position:point(),operation_id:5});
  h.send({action:'center',position:point(104.17),operation_id:4});
  h.send({action:'center',position:point(),operation_id:6,frame_generation:99});
  h.send({action:'center',position:point(),operation_id:6},{origin:'https://evil.invalid'});
  h.send({action:'center',position:point(),operation_id:6},{source:{}});
  assert.equal(h.moves.length,1);
});
