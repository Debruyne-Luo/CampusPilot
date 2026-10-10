"use strict";
// One-shot GPS and cancellation tests. Coordinates and DOM are synthetic fixtures.
const assert=require('node:assert/strict'), vm=require('node:vm'), fs=require('node:fs');
class Node {
  constructor(tag,text=''){this.tag=tag;this.textContent=text;this.children=[];this.handlers={};this.isConnected=true;this.disabled=false;}
  append(...nodes){this.children.push(...nodes);}
  prepend(node){this.children=this.children.filter(x=>x!==node);this.children.unshift(node);}
  replaceChildren(...nodes){this.children=nodes;}
  setAttribute(){}
  addEventListener(event,callback){this.handlers[event]=callback;}
  click(){this.handlers.click?.();}
}
const callbacks=[],sent=[],timers=new Map();let timer=0;
const p={place_id:'synthetic:destination',name:'SYNTHETIC destination',aliases:[],position:{longitude:0,latitude:0,coordinate_system:'GCJ02'}};
const context={module:{exports:{}},console,places:[p],mapState:'ready',isSecureContext:true,
  element:(tag,text)=>new Node(tag,text),Journey:{present(){}},sendToMap:data=>sent.push(data),
  navigator:{geolocation:{getCurrentPosition:(success,error)=>callbacks.push({success,error})}},
  setTimeout:fn=>{timers.set(++timer,fn);return timer;},clearTimeout:id=>timers.delete(id)};
vm.createContext(context);vm.runInContext(fs.readFileSync('backend/src/campuspilot/web_assets/nearby.js','utf8'),context);
const near=context.module.exports, parent=new Node('section');near.attach(parent,[p],'fixture');
const box=parent.children[0],controls=box.children[0],button=controls.children[0],select=controls.children[1],status=box.children[1],output=box.children[2];
const fix={coords:{longitude:0,latitude:0,accuracy:10}};
button.click();assert.equal(callbacks.length,1);assert.equal(button.disabled,true);
near.cancel();button.click();callbacks[0].success(fix);assert.equal(sent.length,0,'cancelled GPS callback cannot supersede a new request');
callbacks[1].success(fix);assert.equal(sent.length,1);assert.equal(sent[0].action,'nearby-origin');
near.receive({request_id:sent[0].request_id-1,status:'success',position:p.position});assert.equal(output.children.length,0);
near.receive({request_id:sent[0].request_id,status:'success',position:p.position});assert.equal(output.children.length,1);assert.equal(button.disabled,false);
select.value=p.place_id;select.handlers.change();assert.equal(callbacks.length,2,'catalogue origin never requests GPS');assert.match(status.textContent,/SYNTHETIC destination/);
button.click();callbacks[2].error();assert.equal(button.disabled,false);assert.match(status.textContent,/未能获取/);
button.click();callbacks[3].success({coords:{longitude:0,latitude:0,accuracy:900}});assert.equal(sent.length,1);assert.match(status.textContent,/精度不足/);
button.click();output.isConnected=false;callbacks[4].success(fix);assert.equal(sent.length,1,'removed chat does not send stale GPS');near.cancel();
assert.equal(timers.size,0);console.log('Nearby cancellation/denial/privacy tests passed with synthetic fixes.');
