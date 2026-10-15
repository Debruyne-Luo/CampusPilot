// GSAP owns desktop DOM motion. AMap owns its camera; narrow screens keep Motion Mini.
export const isDesktop = () => matchMedia('(min-width:1280px)').matches;
export const reducedMotion = () => matchMedia('(prefers-reduced-motion: reduce)').matches || document.body.dataset.reduceMotion === 'true';
let engine;
export function getGsap() {
  return engine ||= new Promise(resolve => {
    const script=document.createElement('script');
    script.src=new URL('./vendor/gsap-3.15.0.min.js',import.meta.url).href;
    script.onload=()=>resolve(window.gsap);
    script.onerror=()=>resolve(null); // content and controls remain usable if motion cannot load
    document.head.append(script);
  });
}
export function enterDesktop(elements, duration = .2, y = 6) {
  if (reducedMotion()) return;
  getGsap().then(gsap => {
    const targets = Array.from(elements).filter(el => el?.isConnected);
    if (!gsap || !isDesktop() || reducedMotion() || !targets.length) return;
    gsap.fromTo(targets, {opacity:.4, y}, {opacity:1, y:0, duration, stagger:.025, ease:'power3.out', overwrite:true, clearProps:'transform,opacity'});
  });
}

// Native <details> semantics remain available without JS and on narrow screens.
export function installDisclosures(root) {
  const targets = new WeakMap();
  root.addEventListener('click', async event => {
    const summary = event.target.closest('summary');
    if (!isDesktop() || !summary || !root.contains(summary)) return;
    const details = summary.parentElement;
    if (!details.matches('details.citations, .citations details, details.handling-preview')) return;
    event.preventDefault();
    const wanted = !(targets.get(details) ?? details.open);
    targets.set(details, wanted);
    const gsap = await getGsap();
    if (targets.get(details) !== wanted || !details.isConnected) return;
    if(!gsap){details.open=wanted;targets.delete(details);return;}
    gsap.killTweensOf(details);
    const start = details.getBoundingClientRect().height;
    details.style.height = ''; details.open = true;
    const end = wanted ? details.getBoundingClientRect().height : summary.getBoundingClientRect().height + parseFloat(getComputedStyle(details).paddingTop) + parseFloat(getComputedStyle(details).paddingBottom);
    const anchor = summary.getBoundingClientRect().top;
    const finish = () => {details.open = wanted; details.style.height = ''; details.style.overflow = ''; targets.delete(details);};
    if (reducedMotion()) {finish(); return;}
    gsap.fromTo(details, {height:start, overflow:'hidden'}, {height:end, duration:.22, ease:'power3.out', onUpdate:() => {
      root.scrollTop += summary.getBoundingClientRect().top - anchor;
    }, onComplete:finish});
  });
}
