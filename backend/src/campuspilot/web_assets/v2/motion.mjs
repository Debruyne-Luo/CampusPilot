// Motion is used only for plan steps and answer cards; disabled under prefers-reduced-motion.
import { animate, stagger } from "./vendor/motion-mini.mjs";

const reduced = () => typeof matchMedia === "function" && matchMedia("(prefers-reduced-motion: reduce)").matches;
const SPRING = [0.2, 1.2, 0.4, 1];

export function stepIn(el) {
  if (reduced() || !el) return;
  animate(el, { opacity: [0, 1], transform: ["translateY(8px)", "none"] }, { duration: 0.38, ease: SPRING });
}
export function tick(el) {
  if (reduced() || !el) return;
  animate(el, { transform: ["scale(.4)", "scale(1)"] }, { duration: 0.32, ease: SPRING });
}
export function cardsIn(els) {
  if (reduced() || !els.length) return;
  animate(els, { opacity: [0, 1], transform: ["translateY(12px) scale(.985)", "none"] },
    { duration: 0.42, delay: stagger(0.07), ease: SPRING });
}
