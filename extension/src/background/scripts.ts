// Service worker: running page.js functions in a tab's frames, and telling a page blocked by a dialog.

import { sleep } from "./config";

// Async so that page functions may return a Promise (executeScript awaits the one returned here).
const callWp = async (n: string, a: any[]) => {
  const wp = (globalThis as any).__wp;
  // Missing, or injected by an older build of the extension that lacks this function.
  if (!wp || typeof wp[n] !== "function") return { missing: true };
  try { return { value: await wp[n](...a) }; } catch (e: any) { return { error: String(e?.message ?? e) }; }
};

export const RESTRICTED = "could not run script in this tab: it shows a page no extension may script (chrome:// or edge:// " +
  "pages, the extension store, a PDF); goto a normal web page first";

/** Chrome's errors for pages an extension cannot script, with what to do instead. */
export function explain(e: any): Error {
  if (e instanceof PageBlocked) return e;
  const m = String(e?.message ?? e);
  if (/cannot access|cannot be scripted/i.test(m)) return new Error(`${RESTRICTED} (${m})`);
  if (/showing error page/i.test(m)) {
    return new Error(`the tab shows the browser's error page (site unreachable?); goto the URL again or another page (${m})`);
  }
  return e instanceof Error ? e : new Error(m);
}

/** A page whose main thread no longer runs scripts: almost always a dialog the shim did not answer. */
export class PageBlocked extends Error {}

const NOT_ANSWERING = "the page is not answering: a dialog it opened (alert, confirm) may be blocking it; " +
  "`webpilot reload` or `goto` closes it, or ask the user to answer it in the browser";

/** Lets PageBlocked through the catch blocks that retry while a page navigates. */
export function rethrowBlocked(e: unknown) {
  if (e instanceof PageBlocked) throw e;
}

/** How long a page call may go unanswered before the page is checked (a snapshot of 60k elements takes 0.7 s). */
const CHECK_AFTER_MS = 5000;

/**
 * Waits for p, a script run in the tab's frames. A JavaScript dialog blocks the page, and with it every script
 * an extension runs there, without an error: when p has not settled after CHECK_AFTER_MS, a trivial script is
 * run in the same frames, and if that does not return within 5 s either, fails with PageBlocked.
 */
export async function answering<T>(tabId: number, frames: number[] | "all", p: Promise<T>): Promise<T> {
  let done = false;
  let timer: ReturnType<typeof setTimeout> | undefined;
  const probe = new Promise<never>((_, reject) => {
    const check = async () => {
      const target = frames === "all" ? { tabId, allFrames: true } : { tabId, frameIds: frames };
      const alive = await Promise.race([
        chrome.scripting.executeScript({ target, func: () => 1, injectImmediately: true }).then(() => true, () => true),
        sleep(5000).then(() => false),
      ]);
      if (done) return;
      if (alive) timer = setTimeout(check, CHECK_AFTER_MS);
      else reject(new PageBlocked(NOT_ANSWERING));
    };
    timer = setTimeout(check, CHECK_AFTER_MS);
  });
  try {
    return await Promise.race([p, probe]);
  } finally {
    done = true;
    clearTimeout(timer);
  }
}

/** Calls globalThis.__wp[name](...args) in one frame of the tab, injecting page.js first if needed. */
export async function frameCall<T = any>(tabId: number, frameId: number, name: string, ...args: any[]): Promise<T> {
  const target = { tabId, frameIds: [frameId] };
  const run = async () => {
    const [res] = await answering(tabId, [frameId], chrome.scripting.executeScript({ target, func: callWp, args: [name, args] }))
      .catch((e) => { throw explain(e); });
    return res?.result as any;
  };
  let r = await run();
  if (r?.missing) {
    await answering(tabId, [frameId], chrome.scripting.executeScript({ target, files: ["page.js"] }))
      .catch((e) => { throw explain(e); });
    r = await run();
  }
  if (!r) throw new Error(RESTRICTED);
  if (r.error) throw new Error(r.error);
  if (r.value && typeof r.value === "object" && r.value.error) throw new Error(r.value.error);
  return r.value;
}

/** Calls globalThis.__wp[name](...args) in the tab's main frame. */
export const pageCall = <T = any>(tabId: number, name: string, ...args: any[]) => frameCall<T>(tabId, 0, name, ...args);

/** Calls globalThis.__wp[name](...args) in every frame that allows scripts; frames that fail are left out. */
export async function allFramesCall(tabId: number, name: string, ...args: any[]): Promise<{ frameId: number; value: any }[]> {
  const run = () => answering(tabId, "all",
    chrome.scripting.executeScript({ target: { tabId, allFrames: true }, func: callWp, args: [name, args] }));
  let res = await run();
  const missing = res.filter((r) => (r.result as any)?.missing).map((r) => r.frameId);
  if (missing.length) {
    await answering(tabId, missing, chrome.scripting.executeScript({ target: { tabId, frameIds: missing }, files: ["page.js"] }))
      .catch(rethrowBlocked);
    res = await run();
  }
  return res
    .filter((r) => r.result && !(r.result as any).missing && !(r.result as any).error)
    .map((r) => ({ frameId: r.frameId, value: (r.result as any).value }));
}
