// Service worker: waiting for targets, markers and quiet DOM and network after an action.

import { sleep } from "./config";
import { rethrowBlocked, frameCall, allFramesCall } from "./scripts";
import { Loc, splitRef } from "./frames";

/** Waits until the DOM has had no mutations for quietMs (AJAX updates never change the tab status). */
export async function domIdle(tabId: number, quietMs: number, capMs: number, frameId = 0) {
  const end = Date.now() + capMs;
  while (Date.now() < end) {
    try { if ((await frameCall(tabId, frameId, "idle")).sinceMs >= quietMs) return; } catch (e) { rethrowBlocked(e); /* navigating */ }
    await sleep(100);
  }
}

type Net = { pending: () => number; quietMs: () => number; stop: () => void };

/**
 * Counts the tab's in-flight page loads and XHR/fetch requests while an action settles. Listeners
 * exist only during the action, so other browsing never wakes the service worker.
 */
export function watchNetwork(tabId: number): Net {
  const inflight = new Set<string>();
  let last = Date.now();
  const filter: chrome.webRequest.RequestFilter = {
    urls: ["<all_urls>"], tabId, types: ["main_frame", "sub_frame", "xmlhttprequest"],
  };
  const start = (d: { requestId: string }) => { inflight.add(d.requestId); last = Date.now(); return undefined; };
  const end = (d: { requestId: string }) => { inflight.delete(d.requestId); last = Date.now(); };
  try {
    chrome.webRequest.onBeforeRequest.addListener(start, filter);
    chrome.webRequest.onCompleted.addListener(end, filter);
    chrome.webRequest.onErrorOccurred.addListener(end, filter);
  } catch { /* no webRequest permission (extension not reloaded yet) */ }
  return {
    pending: () => inflight.size,
    quietMs: () => Date.now() - last,
    stop: () => {
      chrome.webRequest?.onBeforeRequest.removeListener(start);
      chrome.webRequest?.onCompleted.removeListener(end);
      chrome.webRequest?.onErrorOccurred.removeListener(end);
    },
  };
}

/**
 * After an interaction: give navigations a moment to start and wait for them to finish, then wait
 * until no requests are in flight and the DOM and network have been quiet for 500 ms (AJAX updates
 * never change the tab status). Gives up after domCapMs of DOM churn (timers, animations), or 10 s
 * of pending requests (long polling). Returns whether a page load happened and, when it gave up,
 * what kept the page busy.
 */
export async function settle(
  tabId: number, net: Net, frameId = 0, domCapMs = 5000,
): Promise<{ navigated: boolean; busy?: "dom" | "network" }> {
  await sleep(300);
  let navigated = false;
  const end = Date.now() + 15000;
  while (Date.now() < end) {
    try {
      if ((await chrome.tabs.get(tabId)).status === "complete") break;
      navigated = true;
    } catch { return { navigated }; }
    await sleep(200);
  }
  const start = Date.now();
  for (;;) {
    const elapsed = Date.now() - start;
    const busy = net.pending() > 0;
    if (elapsed > 10000) return { navigated, busy: "network" };
    if (!busy && elapsed > domCapMs) return { navigated, busy: "dom" };
    if (!busy && net.quietMs() >= 500) {
      try {
        const s = await frameCall(tabId, frameId, "idle");
        if (s.sinceMs >= 500 && !s.busy) return { navigated };
      } catch (e) { rethrowBlocked(e); /* navigating */ }
    }
    await sleep(100);
  }
}

/**
 * Polls until the target exists, is visible and enabled (it may still be rendering), or passes another page
 * check (`readyUpload`). Selectors and text= targets not found in the main frame are looked for in iframes.
 * Returns the frame and whether a stale ref was re-resolved.
 */
export async function waitTarget(tabId: number, raw: string, timeoutMs: number, check = "ready"): Promise<Loc & { reresolved: boolean }> {
  const loc = splitRef(raw);
  const anyFrame = loc.frameId === 0 && !/^e\d+$/.test(loc.target);
  const end = Date.now() + timeoutMs;
  for (;;) {
    let r: { ok: boolean; reason?: string; fatal?: boolean; reresolved?: boolean };
    try {
      r = await frameCall(tabId, loc.frameId, check, loc.target);
    } catch (e: any) {
      rethrowBlocked(e);
      r = { ok: false, reason: String(e?.message ?? e) }; // page navigating or restricted
    }
    if (r.ok) return { ...loc, reresolved: !!r.reresolved };
    if (r.fatal) throw new Error(r.reason);
    if (anyFrame) {
      try {
        const hit = (await allFramesCall(tabId, check, loc.target)).find((f) => f.frameId !== 0 && f.value?.ok);
        if (hit) return { frameId: hit.frameId, target: loc.target, reresolved: false };
      } catch (e) { rethrowBlocked(e); /* navigating */ }
    }
    const reason = r.reason;
    if (Date.now() >= end) throw new Error(`${reason} (waited ${timeoutMs / 1000}s)`);
    await sleep(150);
  }
}

/** Polls until the selector is visible and/or the text is in some frame of the page (or, with gone, in none). */
export async function waitFor(tabId: number, selector: string | null, text: string | null, timeoutMs: number, gone = false) {
  const start = Date.now();
  while (Date.now() - start < timeoutMs) {
    try {
      const present = (await allFramesCall(tabId, "check", selector, text)).some((f) => f.value === true);
      if (present !== gone) return { found: true, ms: Date.now() - start };
    } catch (e) { rethrowBlocked(e); /* page navigating */ }
    await sleep(250);
  }
  return { found: false, ms: Date.now() - start };
}

/** Waits until no frame has a visible aria-busy="true" element (up to timeoutMs). */
export async function waitNotBusy(tabId: number, timeoutMs: number) {
  const end = Date.now() + timeoutMs;
  while (Date.now() < end) {
    try {
      if (!(await allFramesCall(tabId, "idle")).some((f) => f.value?.busy)) return;
    } catch (e) { rethrowBlocked(e); /* navigating */ }
    await sleep(100);
  }
}
