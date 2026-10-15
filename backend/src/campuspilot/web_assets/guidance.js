"use strict";
// Geometry and noisy-fix handling are independent of GPS, UI and the map provider.
const WalkingProgress = (() => {
  const valid = (p) => Array.isArray(p) && p.length === 2 && p.every(Number.isFinite) && Math.abs(p[0]) <= 180 && Math.abs(p[1]) <= 90;
  function metres(a,b) {
    const x = (b[0]-a[0]) * 111320 * Math.cos((a[1]+b[1]) * Math.PI / 360);
    const y = (b[1]-a[1]) * 111320; return Math.hypot(x,y);
  }
  function create(geometry,stepEnds,totalDistance) {
    if (!Array.isArray(geometry) || geometry.length < 2 || geometry.length > 20000 || !geometry.every(valid) ||
        !Array.isArray(stepEnds) || !stepEnds.length || !stepEnds.every((i,n) => Number.isSafeInteger(i) && i >= 0 && i < geometry.length && (!n || i >= stepEnds[n-1])) ||
        !Number.isFinite(totalDistance) || totalDistance <= 0) throw new Error("Invalid walking geometry");
    const cumulative = [0];
    for (let i=1;i<geometry.length;i++) cumulative.push(cumulative[i-1]+metres(geometry[i-1],geometry[i]));
    const length = cumulative[cumulative.length-1]; if (length < 1) throw new Error("Empty walking geometry");
    let along = null, lastTime = null, offSince = null, arrivalSince = null;
    function project(point) {
      let best = null;
      const scale = 111320 * Math.cos(point[1] * Math.PI / 180);
      for (let i=1;i<geometry.length;i++) {
        if (along !== null && (cumulative[i] < along-40 || cumulative[i-1] > along+200)) continue;
        const a=geometry[i-1],b=geometry[i];
        const ax=(a[0]-point[0])*scale, ay=(a[1]-point[1])*111320;
        const dx=(b[0]-a[0])*scale,dy=(b[1]-a[1])*111320;
        const denominator=dx*dx+dy*dy;
        const t=denominator ? Math.max(0,Math.min(1,-(ax*dx+ay*dy)/denominator)) : 0;
        const distance=Math.hypot(ax+t*dx,ay+t*dy), candidate=cumulative[i-1]+t*(cumulative[i]-cumulative[i-1]);
        if (!best || distance < best.distance-.5 || (Math.abs(distance-best.distance) <= .5 && along !== null && Math.abs(candidate-along) < Math.abs(best.along-along))) best={distance,along:candidate};
      }
      return best;
    }
    function update(point,accuracy,now) {
      if (!valid(point) || !Number.isFinite(accuracy) || accuracy < 0 || !Number.isFinite(now)) return {status:"invalid"};
      if (accuracy > 60) {offSince=null; arrivalSince=null; return {status:"inaccurate",accuracy};}
      const nearest=project(point); if (!nearest) return {status:"invalid"};
      const threshold=Math.max(35,accuracy*1.5);
      if (nearest.distance > threshold) {
        arrivalSince=null; if (offSince === null) offSince=now;
        return {status:now-offSince >= 6000 ? "off_route" : "checking",deviation:Math.round(nearest.distance)};
      }
      offSince=null;
      if (along !== null && lastTime !== null && nearest.along-along > Math.max(60,(now-lastTime)/1000*2.5+accuracy*2)) {
        arrivalSince=null; return {status:"unstable"};
      }
      along=Math.max(along || 0,nearest.along); lastTime=now;
      const remaining=Math.max(0,totalDistance*(1-along/length));
      let step=0; while (step < stepEnds.length-1 && along > cumulative[stepEnds[step]]-8) step++;
      const atEnd=accuracy <= 25 && along/length >= .85 && metres(point,geometry[geometry.length-1]) <= 20;
      if (atEnd) {if (arrivalSince === null) arrivalSince=now;} else arrivalSince=null;
      return {status:arrivalSince !== null && now-arrivalSince >= 6000 ? "arrived" : "walking",remaining,step,accuracy};
    }
    // Pausing breaks consecutive-fix evidence, but retains the last route progress.
    function resetContinuity() {offSince=null; arrivalSince=null;}
    return {update,resetContinuity};
  }
  return {create,metres};
})();
if (typeof module !== "undefined" && module.exports) module.exports = WalkingProgress;

const Guidance = typeof document === "undefined" ? null : (() => {
  let context=null, tracker=null, watchId=null, sequence=0, phase="idle", note="", progress=null;
  let rawPosition=null, lastSent=0;
  function button(text,action) {const b=element("button",text,"journey-button"); b.type="button"; b.addEventListener("click",action); return b;}
  function clearWatch() {
    if (watchId !== null) navigator.geolocation?.clearWatch(watchId);
    watchId=null; rawPosition=null;
    if (context) sendToMap({action:"guidance-stop",request_id:context.requestId,navigation_id:sequence});
  }
  function stop() {
    const ended=context;
    clearWatch(); sequence++; context=null; tracker=null; progress=null; phase="idle"; note=""; render();
    ended?.onStop?.();
  }
  function pause(message="页面已离开前台，步行引导已暂停。") {
    if (!context || ["paused","error","arrived"].includes(phase)) return;
    clearWatch(); sequence++; tracker?.resetContinuity(); phase="paused"; note=message; render();
    if(context.demo) sendToMap({action:'dino-pause',paused:true});
  }
  function start(options) {
    stop(); context=options;
    try {tracker=WalkingProgress.create(options.route.geometry,options.route.stepEnds,options.route.distance);}
    catch {phase="error"; note="当前路线未提供完整引导信息，请重新规划。"; render(); return;}
    watch();
  }
  function resume() {
    if (!context || !tracker || !["paused","error"].includes(phase)) return;
    tracker.resetContinuity(); watch();
  }
  function watch() {
    const id=++sequence; lastSent=-Infinity;
    if(context.demo) {
      phase='walking'; note='路线演示 · 不使用设备定位，不代表你的实时位置。'; render();
      sendToMap({action:'dino-pause',paused:false}); return;
    }
    if (!navigator.geolocation || !window.isSecureContext) {phase="error"; note="当前浏览器无法持续定位，可展开分步指引。"; render(); return;}
    phase="locating"; note="正在获取当前位置…"; render();
    sendToMap({action:"guidance-start",request_id:context.requestId,navigation_id:id});
    const fail=(error) => {
      if (!context || id !== sequence || !["locating","walking"].includes(phase)) return;
      clearWatch(); sequence++; tracker.resetContinuity(); phase="error";
      note=error.code === 1 ? "定位权限未允许，可继续查看分步指引。" : "暂未取得有效定位，请重试或查看分步指引。"; render();
    };
    try {watchId=navigator.geolocation.watchPosition((fix) => {
      if (!context || id !== sequence || !["locating","walking"].includes(phase)) return;
      const {longitude,latitude,accuracy}=fix.coords;
      if (![longitude,latitude,accuracy].every(Number.isFinite) || Math.abs(longitude)>180 || Math.abs(latitude)>90 ||
          accuracy < 0 || !Number.isFinite(fix.timestamp) || Date.now()-fix.timestamp > 15000 || fix.timestamp-Date.now() > 2000) return;
      rawPosition=accuracy <= 60 ? {longitude,latitude,coordinate_system:"WGS84"} : null;
      const now=Date.now(); if (now-lastSent < 6000) return; lastSent=now;
      sendToMap({action:"guidance-update",request_id:context.requestId,navigation_id:id,
        position:{longitude,latitude,coordinate_system:"WGS84"},accuracy});
    }, fail, {enableHighAccuracy:true,timeout:15000,maximumAge:0});}
    catch {fail({code:2});}
  }
  function receive(data) {
    if (!context || data.navigation_id !== sequence || data.request_id !== context.requestId || !["locating","walking"].includes(phase)) return;
    if (data.status !== "success") {
      clearWatch(); sequence++; tracker.resetContinuity(); phase="error";
      note="当前位置暂时无法更新，请重试定位或查看分步指引。"; render(); return;
    }
    const p=data.position;
    if (p?.coordinate_system !== "GCJ02") return;
    const next=tracker.update([p.longitude,p.latitude],data.accuracy,Date.now());
    if (next.status === "invalid") return;
    phase="walking";
    if (next.status === "walking") {progress=next; note="按参考路线步行，留意现场道路与入口。";}
    else if (next.status === "arrived") {progress=next; phase="arrived"; note="已到达目的地附近，请核对建筑入口。"; clearWatch();}
    else if (next.status === "inaccurate") {note=`定位精度约 ${Math.round(next.accuracy)} 米，暂不更新步行进度。`;}
    else if (next.status === "off_route") {progress=next; note=`距参考路线约 ${next.deviation} 米，可从当前位置重新规划。`;}
    else {note="正在确认定位，请留意地图上的当前位置。";}
    render();
  }
  function replan() {
    if (!context || !rawPosition) return;
    const origin={...rawPosition}, callback=context.replan; stop(); callback(origin);
  }
  function receiveDemo(data) {
    if(!context?.demo || data.request_id!==context.requestId || phase!=='walking') return;
    const distance=context.route.distance;
    const travelled=Math.max(0,Math.min(distance,data.fraction*distance));
    const geometry=context.route.geometry, cumulative=[0];
    for(let i=1;i<geometry.length;i++) cumulative.push(cumulative[i-1]+WalkingProgress.metres(geometry[i-1],geometry[i]));
    const ends=context.route.stepEnds || [], along=data.fraction*cumulative.at(-1);
    let step=ends.findIndex(i=>cumulative[i]>=along);
    if(step<0)step=context.route.steps.length-1;
    step=Math.max(0,step);
    progress={status:'walking',step,remaining:distance-travelled};
    // Keep controls mounted during progress updates so pointer-down/up and focus survive.
    const slot=document.querySelector('.guidance-slot');
    if(!slot?.querySelector('.guidance-progress')) {render();return;}
    slot.querySelector('.guidance-step-label').textContent=`下一步 · 第 ${step+1} / ${context.route.steps.length} 步`;
    slot.querySelector('h3').textContent=context.route.steps[step] || '继续沿路线步行';
    slot.querySelector('.guidance-progress').textContent=`剩余约 ${Math.round(progress.remaining)} 米`;
    const bar=slot.querySelector('.g-progress i');
    if (bar && distance > 0) bar.style.width=`${Math.max(0,Math.min(100,(travelled/distance)*100))}%`;
  }
  function render() {
    const slot=document.querySelector('.guidance-slot'); if (!slot) return;
    slot.replaceChildren();
    const active=!!context;
    // Classic UI has #journey-card/#journey-title; the v2 UI only provides .guidance-slot.
    document.getElementById('journey-card')?.classList.toggle('guiding',active);
    const title=document.getElementById('journey-title'); if (title) title.textContent=active ? '步行引导' : '步行参考路线';
    document.querySelector('.start-guidance')?.toggleAttribute('hidden',active);
    document.querySelector('.route-guidance-note')?.toggleAttribute('hidden',active);
    if (!active) return;
    const box=element('section',undefined,'guidance-box'); box.setAttribute('aria-label','前台步行引导');
    box.append(element('p','前往 ' + context.target.name,'guidance-target'));
    if (context.detail) box.append(element('p',context.detail,'guidance-detail'));
    const status=element('p',note,note === '按参考路线步行，留意现场道路与入口。' ? 'guidance-normal-note' : ''); status.setAttribute('role','status'); box.append(status);
    // Honest progress: fraction of the real route already covered (GPS or demo position).
    const total=Number(context.route.distance) || 0;
    function progressBar(remaining) {
      const wrap=element('div',undefined,'g-progress'); wrap.setAttribute('aria-hidden','true');
      const fill=element('i'); wrap.append(fill);
      if (total > 0) fill.style.width=`${Math.max(0,Math.min(100,(1-remaining/total)*100))}%`;
      return wrap;
    }
    if (phase === 'arrived') {
      const done=element('div',undefined,'g-arrived');
      done.append(element('span','✓','tick'),element('h3','已到达目的地附近'));
      box.append(done);
      box.append(element('p','请核对建筑入口与楼层指引。','guidance-arrived-note'));
    }
    else if (progress?.status === 'walking') {
      box.append(element('p',`下一步 · 第 ${progress.step+1} / ${context.route.steps.length} 步`,'guidance-step-label'));
      box.append(element('h3',context.route.steps[progress.step] || '继续沿路线步行'));
      const remaining=Math.round(progress.remaining), time=Math.max(1,Math.ceil(context.route.time*progress.remaining/context.route.distance/60));
      box.append(progressBar(progress.remaining));
      const meta=element('div',undefined,'g-progress-meta');
      meta.append(element('span',`剩余约 ${remaining} 米`,'guidance-progress'),element('span',`约 ${time} 分钟`));
      box.append(meta);
    }
    if (['paused','error'].includes(phase)) box.append(button(context.demo ? '继续演示' : phase === 'paused' ? '继续引导' : '重试定位',resume));
    else if (phase !== 'arrived') {
      const follow=button('跟随位置',() => sendToMap({action:'guidance-follow',navigation_id:sequence})); follow.classList.add('guidance-follow-button');
      box.append(button(context.demo ? '暂停演示' : '暂停引导',() => pause(context.demo ? '路线演示已暂停。' : '步行引导已暂停。')));
      if(!context.demo) box.append(follow);
      if (rawPosition && progress?.status === 'off_route') box.append(button('从当前位置重新规划',replan));
    }
    const end=button(context.demo ? '结束演示' : '结束引导',stop), exit=button('退出路线',() => {
      if(context?.onExit) {const exit=context.onExit;stop();exit();}
      else if(typeof Journey !== 'undefined') Journey.exitRoute(); else stop();
    });
    end.classList.add('guidance-end-button'); exit.classList.add('guidance-exit-button');
    box.append(end,exit); slot.append(box);
  }
  document.addEventListener('visibilitychange',() => {if (document.hidden) pause();});
  window.addEventListener('pagehide',stop);
  return {start,stop,pause,receive,receiveDemo,render,active:() => !!context};
})();
// Top-level const is not a window property; ES modules (v2 UI) reach it through window.
if (Guidance) window.Guidance = Guidance;
