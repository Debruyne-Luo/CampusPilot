"use strict";
// Ranking stays in the page. No personal origin is sent to chat, storage or analytics.
const Nearby = (() => {
  let sequence = 0, pending = null, timer;
  const valid = (p) => p?.coordinate_system === 'GCJ02' && Number.isFinite(p.longitude) && Number.isFinite(p.latitude) && Math.abs(p.longitude) <= 180 && Math.abs(p.latitude) <= 90;
  function distance(a, b) {
    const rad = Math.PI / 180, lat = (b.latitude-a.latitude)*rad, lng = (b.longitude-a.longitude)*rad;
    const h = Math.sin(lat/2)**2 + Math.cos(a.latitude*rad)*Math.cos(b.latitude*rad)*Math.sin(lng/2)**2;
    return 6371000 * 2 * Math.asin(Math.sqrt(Math.min(1, h)));
  }
  function rank(origin, candidates) {
    if (!valid(origin)) return [];
    return candidates.filter(p => valid(p.position)).map(place => ({place, distance: distance(origin, place.position)}))
      .sort((a,b) => a.distance-b.distance || a.place.place_id.localeCompare(b.place.place_id));
  }
  function normalize(text) {return text.normalize('NFKC').toLowerCase().replace(/[\s·（）()_-]+/g,'');}
  function match(pool, query) {
    const q=normalize(query), block=q.match(/e[12][abc](?=\d|\b)/);
    const text=block ? block[0] : q;
    if (!text) return pool;
    const direct=pool.filter(p => [p.name,...p.aliases].some(x => normalize(x).includes(text)));
    if (direct.length) return direct;
    const scored=pool.map(p => ({p,score:Math.max(0,...[p.name,...p.aliases].map(x => {const label=normalize(x);return label.length>1 && text.includes(label) ? label.length : 0;}))}));
    const max=Math.max(0,...scored.map(x=>x.score));return scored.filter(x=>max>0 && x.score===max).map(x=>x.p);
  }
  function cancel() {
    sequence++; clearTimeout(timer);
    if (pending?.status?.isConnected) pending.status.textContent='定位已取消，可重新选择位置。';
    if (pending?.button) pending.button.disabled=false;
    pending=null;
  }
  function recommend(origin, state, accuracy=0) {
    const ranked=rank(origin,state.candidates);
    state.output.replaceChildren();
    if (!ranked.length) {state.status.textContent='这些地点尚无可用地图点位。';return;}
    state.status.textContent=`${state.originName || '按当前定位'}推荐；距离为直线到建筑/店铺参考点，实际步行看路线。`;
    if (accuracy > 100) state.status.textContent+=` 定位精度约${Math.round(accuracy)}米。`;
    for (const [i,item] of ranked.slice(0,1).entries()) {
      const meters=Math.round(item.distance/10)*10, label=meters<1000 ? `${meters}米` : `${(meters/1000).toFixed(1)}公里`;
      const b=element('button',`${i===0?'建议先去：':''}${item.place.name} · 直线约${label} ↗`,'linked-card');b.type='button';
      b.addEventListener('click',()=>Journey.present({places:[item.place],result_status:'success'},state.source));state.output.append(b);
    }
    state.box.prepend(state.output);
  }
  function receive(data) {
    const state=pending;
    if (!state || data.request_id!==state.id) return;
    clearTimeout(timer);pending=null;state.button.disabled=false;
    if (!state.output.isConnected) return;
    if (data.status==='success' && valid(data.position)) recommend(data.position,state,state.accuracy);
    else state.status.textContent='定位坐标转换失败，请选择你所在的校园地点。';
  }
  function attach(parent,candidates,kind='地点',source='places') {
    if (!candidates.some(p=>valid(p.position))) return;
    const box=element('section',undefined,'nearby-box');box.setAttribute('aria-label','最近'+kind+'推荐');
    const controls=element('div',undefined,'nearby-controls'), button=element('button','按我的位置推荐最近'+kind,'journey-button');button.type='button';
    const select=element('select');select.setAttribute('aria-label','选择你所在的地点');
    const placeholder=element('option','或选择你所在的地点');placeholder.value='';select.append(placeholder);
    for(const p of places.filter(p=>valid(p.position) && !(p.tags||[]).includes('food') && !(p.tags||[]).includes('parcel'))) {
      const option=element('option',p.name);option.value=p.place_id;select.append(option);
    }
    const status=element('p','点击定位或选择所在地点，可推荐最近'+kind+'。','nearby-status');status.setAttribute('role','status');
    const output=element('div',undefined,'assistant-actions nearby-results');
    const state={candidates,status,output,button,box,source,originName:''};
    select.addEventListener('change',()=>{cancel();const p=places.find(p=>p.place_id===select.value);if(p){state.originName=`从${p.name}`;recommend(p.position,state);}});
    button.addEventListener('click',()=>{
      cancel();const id=state.id=sequence;state.originName='';select.value='';
      if (mapState!=='ready') {status.textContent='请等待地图加载，或先选择你所在的地点。';return;}
      if (!globalThis.isSecureContext || !navigator.geolocation) {status.textContent='当前环境无法定位，请选择你所在的地点。';return;}
      pending=state;button.disabled=true;status.textContent='正在获取位置…';
      timer=setTimeout(()=>{if(pending===state){cancel();status.textContent='定位超时，请选择你所在的地点。';}},25000);
      navigator.geolocation.getCurrentPosition(fix=>{
        if(pending!==state || state.id!==id || !output.isConnected) return;
        const c=fix.coords;
        if(!Number.isFinite(c.accuracy) || c.accuracy>500){cancel();status.textContent='定位精度不足，请选择你所在的地点。';return;}
        state.accuracy=c.accuracy;status.textContent='正在比较距离…';
        sendToMap({action:'nearby-origin',request_id:state.id,position:{longitude:c.longitude,latitude:c.latitude,coordinate_system:'WGS84'}});
      },()=>{if(pending===state && state.id===id){cancel();status.textContent='未能获取位置，可选择你所在的地点继续推荐。';}},{enableHighAccuracy:true,timeout:15000,maximumAge:0});
    });
    controls.append(button,select);box.append(controls,status,output);parent.append(box);
  }
  return {rank,match,attach,receive,cancel};
})();
if (typeof module !== 'undefined') module.exports=Nearby;
