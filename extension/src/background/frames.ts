// Service worker: iframes: refs like f3e12, snapshots with their frames inlined, and positions across frames.

import { sleep } from "./config";
import { frameCall, pageCall, allFramesCall } from "./scripts";

/** Where an action runs: refs from inside an iframe look like f<frameId>e12. */
export type Loc = { frameId: number; target: string };
export type FrameRead = { url: string; chars: number };

export function splitRef(target: string): Loc {
  const m = /^f(\d+)(e\d+)$/.exec(target);
  return m ? { frameId: Number(m[1]), target: m[2] } : { frameId: 0, target };
}

/**
 * Replaces the iframe placeholders (\u0001token lines) of a snapshot with the snapshots of those
 * frames, refs prefixed with the frame id. Frames that cannot be reached are left as [iframe ...].
 * Each inlined frame's URL and own text size go to `frames` (the session log credits them to their domain).
 */
export async function inlineFrames(
  tabId: number, text: string, maxChars: number, interactive: boolean, frames: FrameRead[] = [], depth = 0,
): Promise<string> {
  const tokens = Array.from(text.matchAll(/^\u0001(\w+)$/gm), (m) => m[1]);
  if (!tokens.length) return text;
  const byToken = new Map<string, number>();
  // Children learn their token by postMessage once page.js is in them, so they may need a round or two.
  for (let i = 0; depth < 4 && i < 8; i++) {
    try {
      for (const f of await allFramesCall(tabId, "frameInfo")) if (f.value?.token) byToken.set(f.value.token, f.frameId);
    } catch { /* restricted */ }
    if (tokens.every((t) => byToken.has(t))) break;
    await sleep(60);
  }
  const parts = new Map<string, string>();
  for (const t of tokens) {
    const frameId = byToken.get(t);
    if (frameId === undefined) continue;
    try {
      const s = await frameCall(tabId, frameId, "snapshot", null, maxChars, interactive);
      const own = String(s.text).replace(/\[e(\d+)/g, `[f${frameId}e$1`);
      frames.push({ url: s.url, chars: own.length });
      const inner = (await inlineFrames(tabId, own, maxChars, interactive, frames, depth + 1)).trim();
      if (inner) parts.set(t, `${inner}\n[/iframe]`);
    } catch { /* frame navigated away or restricted */ }
  }
  return text.replace(/^\u0001(\w+)$\n?/gm, (_, t) => (parts.has(t) ? parts.get(t) + "\n" : ""));
}

/** Runs a selector-based page function in the main frame, or in the first iframe where the selector matches. */
export async function selectorCall(tabId: number, selector: string | null, name: string, ...args: any[]) {
  try {
    return await pageCall(tabId, name, ...args);
  } catch (e: any) {
    if (!selector || !String(e?.message).startsWith("selector not found")) throw e;
    const hit = (await allFramesCall(tabId, name, ...args)).find((f) => f.frameId !== 0 && f.value && !f.value.error);
    if (!hit) throw e;
    return { ...hit.value, frame: `f${hit.frameId}` };
  }
}

/**
 * Viewport coordinates of a target for trusted input, adding the offsets of the iframes it is in, and what
 * covers it there (in its own frame, or over one of those iframes in a frame around it), if anything.
 */
export async function locateAbs(tabId: number, loc: Loc) {
  const p = await frameCall(tabId, loc.frameId, "locate", loc.target);
  let frameId = loc.frameId;
  for (let depth = 0; frameId !== 0; depth++) {
    const { token } = await frameCall(tabId, frameId, "frameInfo");
    const hit = token && depth < 5 ? (await allFramesCall(tabId, "frameOffset", token, p.x, p.y)).find((f) => f.value) : undefined;
    if (!hit) throw new Error("could not locate the iframe on the page; take a new snapshot");
    p.x += hit.value.x;
    p.y += hit.value.y;
    p.covered ||= hit.value.covered;
    frameId = hit.frameId;
  }
  return p;
}

/**
 * locateAbs, polled while another element covers the target, so overlays that go away (spinners, toasts) are
 * waited for. A real click there would land on the overlay, so one that stays is an error.
 */
export async function locateUncovered(tabId: number, loc: Loc, target: string, timeoutMs: number, verb = "click") {
  const end = Date.now() + timeoutMs;
  for (;;) {
    const p = await locateAbs(tabId, loc);
    if (!p.covered) return p;
    if (Date.now() >= end) {
      throw new Error(`${target} (${p.desc}) is covered by ${p.covered}: close that first (click its button), ` +
        `or ${verb} without --trusted`);
    }
    await sleep(150);
  }
}

/** CSS pixels around an element in its screenshot. */
export const SHOT_MARGIN = 8;
