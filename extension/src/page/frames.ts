// Page script: tokens that let the service worker match frame ids to <iframe> elements, and iframe offsets.

import { w } from "./dom";
import { coverAt } from "./find";

// A parent frame tells each child iframe its token (see frameToken), so the service worker can match
// frame ids to <iframe> elements and inline child snapshots in the right place.
if (!w.__wpFrameListener) {
  w.__wpFrameListener = true;
  addEventListener("message", (e) => {
    if (e.source === parent && parent !== window && typeof e.data?.__wpFrame === "string") w.__wpFrameToken = e.data.__wpFrame;
  });
}

export function frameToken(f: HTMLIFrameElement): string {
  let t = f.getAttribute("data-wp-frame");
  if (!t) {
    t = "w" + Math.random().toString(36).slice(2, 10);
    f.setAttribute("data-wp-frame", t);
  }
  f.contentWindow?.postMessage({ __wpFrame: t }, "*");
  return t;
}

/**
 * This frame's token, set by its parent's snapshot (null in the top frame or before a snapshot).
 * Also re-sends the tokens of this frame's child iframes, for children injected after the snapshot.
 */
export function frameInfo() {
  for (const f of Array.from(document.querySelectorAll("iframe[data-wp-frame]"))) frameToken(f as HTMLIFrameElement);
  return { token: (w.__wpFrameToken as string | undefined) ?? null };
}

/**
 * Viewport position of the content box of the child iframe with this token, or null if it is not in this frame,
 * and what in this frame covers the iframe at the child's point (x, y), if anything.
 */
export function frameOffset(token: string, x = 0, y = 0) {
  const f = document.querySelector(`iframe[data-wp-frame="${CSS.escape(token)}"]`) as HTMLIFrameElement | null;
  if (!f) return null;
  const r = f.getBoundingClientRect();
  const cs = getComputedStyle(f);
  const ox = r.left + f.clientLeft + parseFloat(cs.paddingLeft), oy = r.top + f.clientTop + parseFloat(cs.paddingTop);
  return { x: ox, y: oy, covered: coverAt(f, ox + x, oy + y) };
}
