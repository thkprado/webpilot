// Service worker: alert/confirm/prompt answered by dialogs.js (src/dialogs.ts) or natively by the debugger,
// and beforeunload prompts accepted during navigations.

import { Args, sleep } from "./config";
import { siteMatches } from "./domains";
import { rethrowBlocked, answering } from "./scripts";
import { cdp, dialogHandlers } from "./cdp";

export type Dialog = { type: string; message: string; answer: unknown; frame?: string };

/** Main world: sets the policy of dialogs.js in this document; ms = how long it answers (0: no more). */
const dialogPolicy = (accept: boolean, text: string | null, ms: number) => {
  const s = (window as any)[Symbol.for("webpilot.dialogs")];
  if (s) Object.assign(s, { accept, text, until: ms ? Date.now() + ms : 0 });
};

/** Main world: stops answering and returns the dialogs answered so far. */
const dialogTake = () => {
  const s = (window as any)[Symbol.for("webpilot.dialogs")];
  if (!s) return [];
  s.until = 0;
  return s.queue.splice(0);
};

/**
 * Makes every frame of the tab answer its dialogs (accepting or dismissing them) instead of blocking, for up
 * to 2 minutes or until takeDialogs. Pages that cannot be scripted are left alone: the action fails there anyway.
 */
export async function armDialogs(tabId: number, accept: boolean, text: string | null) {
  const target = { tabId, allFrames: true };
  try {
    await answering(tabId, "all", chrome.scripting.executeScript({ target, files: ["dialogs.js"], world: "MAIN", injectImmediately: true }));
    await answering(tabId, "all", chrome.scripting.executeScript({
      target, func: dialogPolicy, args: [accept, text, 120000], world: "MAIN", injectImmediately: true,
    }));
  } catch (e) {
    rethrowBlocked(e);
  }
}

/** The dialogs the frames answered since armDialogs (or since the page loaded), and no more answering. */
export async function takeDialogs(tabId: number): Promise<Dialog[]> {
  try {
    const res = await answering(tabId, "all", chrome.scripting.executeScript({
      target: { tabId, allFrames: true }, func: dialogTake, world: "MAIN", injectImmediately: true,
    }));
    return res.flatMap((r) => ((r.result as Dialog[]) ?? []).map((d) => (r.frameId ? { ...d, frame: `f${r.frameId}` } : d)));
  } catch (e) {
    rethrowBlocked(e);
    return [];
  }
}

let shimSeq = 0;
// Left over by a service worker that stopped during a navigation.
chrome.scripting.getRegisteredContentScripts()
  .then((list) => {
    const ids = list.map((s) => s.id).filter((id) => id.startsWith("wp-dialogs-"));
    if (ids.length) return chrome.scripting.unregisterContentScripts({ ids });
  })
  .catch(() => {});

/**
 * Runs fn (a navigation) with dialogs.js registered at document_start for the target's site, so an alert in an
 * inline script of the new page is answered before anything else runs. Only that site, only meanwhile.
 */
export async function withLoadShim<T>(url: string | undefined, fn: () => Promise<T>): Promise<T> {
  const matches = siteMatches(url);
  const id = `wp-dialogs-${++shimSeq}-${Date.now()}`;
  let registered = false;
  if (matches.length) {
    try {
      await chrome.scripting.registerContentScripts([{
        id, js: ["dialogs.js"], matches, allFrames: true, runAt: "document_start", world: "MAIN", persistAcrossSessions: false,
      }]);
      registered = true;
    } catch { /* older browser: the action's own shim and the not-answering check remain */ }
  }
  try {
    return await fn();
  } finally {
    if (registered) chrome.scripting.unregisterContentScripts({ ids: [id] }).catch(() => {});
  }
}

/**
 * A page that had a user gesture (a --trusted click, or the user) may stop a navigation with a beforeunload
 * prompt ("Leave site?"), which no page script can answer. For those pages only, the debugger watches the
 * navigation: beforeunload is accepted (the agent asked to leave), other dialogs dismissed; all go to `out`.
 * Returns the function that stops watching.
 */
export async function acceptUnload(tabId: number, out: Dialog[]): Promise<() => Promise<void>> {
  const check = chrome.scripting.executeScript({
    target: { tabId, allFrames: true }, func: () => !!(navigator as any).userActivation?.hasBeenActive,
  }).catch(() => []);
  // A page blocked by a dialog does not answer; the navigation closes that dialog anyway.
  const res = await Promise.race([check, sleep(1500).then(() => [])]);
  if (!res.some((r) => r.result === true)) return async () => {};
  dialogHandlers.set(tabId, (p) => {
    const type = String(p.type);
    const accept = type === "beforeunload" || type === "alert";
    out.push({ type, message: String(p.message ?? "").slice(0, 300), answer: type === "beforeunload" ? true : type === "confirm" ? false : null });
    cdp(tabId, "Page.handleJavaScriptDialog", { accept }).catch(() => {});
  });
  try {
    await cdp(tabId, "Page.enable");
  } catch {
    dialogHandlers.delete(tabId);
    return async () => {};
  }
  return async () => {
    dialogHandlers.delete(tabId);
    await cdp(tabId, "Page.disable").catch(() => {});
  };
}

/**
 * For commands that go through the debugger anyway (eval): answers the tab's dialogs natively while fn runs, by
 * the policy of --dialog/--prompt-text, and reports them in `out`. No race with the page and nothing for it
 * to see, unlike the shim. beforeunload is accepted, as in navigate(): the expression asked to leave.
 */
export async function answerNatively<T>(tabId: number, accept: boolean, text: string | null, out: Dialog[],
                                 fn: () => Promise<T>): Promise<T> {
  const previous = dialogHandlers.get(tabId); // a navigation's acceptUnload in the same tab
  dialogHandlers.set(tabId, (p) => {
    const type = String(p.type);
    let answer: unknown = null;
    let ok = accept;
    if (type === "alert" || type === "beforeunload") ok = true;
    if (type === "confirm" || type === "beforeunload") answer = ok;
    if (type === "prompt" && ok) answer = text ?? String(p.defaultPrompt ?? "");
    out.push({ type, message: String(p.message ?? "").slice(0, 300), answer });
    cdp(tabId, "Page.handleJavaScriptDialog", { accept: ok, ...(type === "prompt" && ok ? { promptText: answer } : {}) })
      .catch(() => {});
  });
  try {
    // Hangs when a dialog is already open (Page.enable must come first): the not-answering check then fails it.
    if (!previous) await answering(tabId, [0], cdp(tabId, "Page.enable"));
    return await fn();
  } finally {
    if (previous) dialogHandlers.set(tabId, previous);
    else {
      dialogHandlers.delete(tabId);
      await cdp(tabId, "Page.disable").catch(() => {});
    }
  }
}

/** --dialog: accept or dismiss (the default). */
export function checkDialogArg(a: Args) {
  if (a.dialog !== undefined && a.dialog !== "accept" && a.dialog !== "dismiss") {
    throw new Error(`dialog must be accept or dismiss, not ${JSON.stringify(a.dialog)}`);
  }
}

/** A confirm or prompt that was dismissed: the page asked, and the agent may need to ask the user. */
export const anyDismissed = (dialogs: Dialog[]) =>
  dialogs.some((d) => (d.type === "confirm" || d.type === "prompt") && (d.answer === false || d.answer === null));

export const DISMISSED = "the page asked for confirmation and it was dismissed; if the user agreed to this, repeat with " +
  "--dialog accept";
