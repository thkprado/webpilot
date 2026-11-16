// Page script: DOM mutation counting, quiet time, and presence checks that the service worker polls.

import { w, deepFirst, isVisible } from "./dom";

/** Starts counting DOM mutations (once per document) and restarts the quiet timer. Returns the count so far. */
export function arm() {
  if (!w.__wpObserver) {
    w.__wpMutCount = 0;
    w.__wpObserver = new MutationObserver((records) => {
      const real = records.filter((r) => r.attributeName !== "data-wp-ref" && r.attributeName !== "data-wp-frame" &&
        r.attributeName !== "data-wp-upload").length;
      if (!real) return;
      w.__wpMutCount += real;
      w.__wpLastMut = performance.now();
    });
    w.__wpObserver.observe(document, { subtree: true, childList: true, attributes: true, characterData: true });
  }
  w.__wpLastMut = performance.now();
  return { count: w.__wpMutCount as number };
}

/** How long the DOM has been quiet, and how many mutations happened in this document so far. */
export function idle() {
  if (!w.__wpObserver) arm();
  const busy = Array.from(document.querySelectorAll('[aria-busy="true"]')).some(isVisible);
  return { sinceMs: Math.round(performance.now() - w.__wpLastMut), count: w.__wpMutCount as number, busy, url: location.href };
}

export function check(selector: string | null, text: string | null): boolean {
  if (selector) {
    const el = deepFirst(selector);
    if (!el || !isVisible(el)) return false;
  }
  if (text && !(document.body?.innerText || "").includes(text)) return false;
  return true;
}

export const visibility = () => document.visibilityState;
