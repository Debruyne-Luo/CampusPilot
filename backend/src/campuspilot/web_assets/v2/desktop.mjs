import {getGsap, reducedMotion, installDisclosures} from './desktop-motion.mjs';
export function initDesktop({showChat, focusQuestion, map}) {
  const $ = id => document.getElementById(id);
  const media = matchMedia('(min-width:1280px)'), systemMotion = matchMedia('(prefers-reduced-motion: reduce)');
  const app = document.querySelector('.app'), thread = $('thread'), chat = document.querySelector('.chat');
  let mapMode = false, savedScroll = 0, savedFocus = null, transition = 0, gsap = null;
  function apply() {
    map.preferences({desktop:media.matches, reducedMotion:systemMotion.matches});
    if (reducedMotion()) gsap?.globalTimeline.getChildren().forEach(t => t.progress(1));
  }
  systemMotion.addEventListener('change', apply);
  apply();
  if (media.matches) getGsap().then(value => gsap = value);
  installDisclosures(thread);
  function active(id) {
    $('desktop-map').setAttribute('aria-pressed',String(id==='desktop-map'));
    $('desktop-map').textContent=id==='desktop-map'?'返回问答':'展开地图';
  }
  const readingWidth = () => 540;
  function insets() {
    if (!media.matches) return;
    const wrap = document.querySelector('.mapwrap').getBoundingClientRect();
    const dock = document.querySelector('.map-dock').getBoundingClientRect();
    const bottom = dock.height > 0 ? wrap.bottom-dock.top+16 : 72;
    map.viewportInsets({top:76,bottom:Math.min(bottom,wrap.height*.5),left:32,right:32});
  }
  function mode(on) {
    if (!media.matches) return;
    if (mapMode === on) {insets();return;}
    const token = ++transition;
    gsap?.killTweensOf(app);
    if (on) {savedScroll=thread.scrollTop;savedFocus=document.activeElement;}
    const from = chat.getBoundingClientRect().width;
    map.layout(true);
    mapMode=on;document.body.dataset.workspace = on ? 'map' : 'read';active(on?'desktop-map':'desktop-chat');
    // Bounded layout animation reflows text, never stretches glyphs.
    const end = on?392:readingWidth();app.style.setProperty('--read-width',from+'px');
    const done = () => {
      if(token!==transition)return;
      app.style.setProperty('--read-width',end+'px');document.body.style.setProperty('--read-width',end+'px');
      if(!on){thread.scrollTop=savedScroll;if(savedFocus?.isConnected&&!savedFocus.closest('#desktop-context'))savedFocus.focus({preventScroll:true});}
      insets();map.resize();map.layout(false);
    };
    if(gsap&&!reducedMotion()) gsap.to(app,{'--read-width':end+'px',duration:on?.3:.26,ease:on?'power3.inOut':'power3.out',overwrite:true,onComplete:done});
    else done();
  }
  function summarize() {
    const questions = thread.querySelectorAll('.msg-user'), answers = thread.querySelectorAll('.answer .conclusion');
    $('context-question').textContent = questions.length ? questions[questions.length-1].textContent : '在校园里，找到下一站。';
    const text = answers.length ? answers[answers.length-1].textContent : '先找地点，再选择起点。问答和已保存的清单会留在这里。';
    $('context-answer').textContent = text.length>180?text.slice(0,180)+'…':text;
  }
  function enterMap(place) {if(!media.matches)return;summarize();if(place)$('context-place').textContent=place.name||'已选地点';mode(true);}
  $('return-reading').addEventListener('click',()=>mode(false));
  $('new-chat').addEventListener('click',()=>{mode(false);focusQuestion();});
  $('handling-entry').addEventListener('click',()=>mode(false));
  $('desktop-map').addEventListener('click',()=>{if(mapMode)mode(false);else enterMap();});
  $('route-overview').addEventListener('click',()=>map.overview());
  function resize() {
    ++transition;gsap?.killTweensOf(app);
    if(!media.matches){gsap?.globalTimeline.getChildren().forEach(t=>t.progress(1));delete document.body.dataset.workspace;app.style.removeProperty('--read-width');mapMode=false;}
    else {app.style.setProperty('--read-width',(mapMode?392:readingWidth())+'px');getGsap().then(value=>gsap=value);insets();}
    map.layout(false);apply();
  }
  media.addEventListener('change',resize);window.addEventListener('resize',resize);
  const observer=new ResizeObserver(insets);observer.observe(document.querySelector('.map-dock'));observer.observe(document.querySelector('.mapwrap'));
  new MutationObserver(summarize).observe(thread,{childList:true,subtree:true,characterData:true});
  active('desktop-chat');
  document.addEventListener('click',event=>{
    const button=event.target.closest('button');if(!button||!media.matches||reducedMotion()||!gsap)return;
    gsap.fromTo(button,{scale:.97},{scale:1,duration:.14,ease:'power2.out',overwrite:'auto',clearProps:'transform'});
  });
  return {enterMap,read:()=>mode(false),clearPlace:()=>{$('context-place').textContent='还未选择地点';},get mapMode(){return mapMode;}};
}
