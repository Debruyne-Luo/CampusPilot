// Motion is used only for plan steps and answer cards; disabled under prefers-reduced-motion.
import { animate, stagger } from "./vendor/motion-mini.mjs";
import {enterDesktop} from './desktop-motion.mjs';

const desktop = () => typeof matchMedia === "function" && matchMedia("(min-width:1280px)").matches;
const reduced = () => typeof matchMedia === "function" && (matchMedia("(prefers-reduced-motion: reduce)").matches || (desktop() && document.body.dataset.reduceMotion === "true"));
const SPRING = "cubic-bezier(.2,.7,.2,1)";

export function stepIn(el) {
  if (reduced() || !el) return;
  if (desktop()) { enterDesktop([el], .16, 0); return; }
  animate(el, { opacity: [0, 1], transform: ["translateY(8px)", "none"] }, { duration: 0.22, ease: SPRING });
}
export function tick(el) {
  if (reduced() || !el) return;
  if (desktop()) { enterDesktop([el], .12, 0); return; }
  animate(el, { transform: ["scale(.4)", "scale(1)"] }, { duration: 0.22, ease: SPRING });
}
export function cardsIn(els) {
  if (reduced() || !els.length) return;
  if (desktop()) {
    enterDesktop(els.slice(0, 6), .22, 8);
    return;
  }
  animate(els.slice(0, 6), { opacity: [.4, 1], transform: ["translateY(8px)", "none"] },
    { duration: 0.22, delay: stagger(0.03), ease: SPRING });
}
