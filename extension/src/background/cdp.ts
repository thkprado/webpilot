// Service worker: the debugger (CDP) connection to a tab, its events, trusted mouse and key input, screenshots.

import { retryTabEdit } from "../tabedit";
import { sleep } from "./config";
import { rethrowBlocked, frameCall } from "./scripts";

const attached = new Set<number>();
const detachTimers = new Map<number, ReturnType<typeof setTimeout>>();
const inFlight = new Map<number, number>();
chrome.debugger.onDetach.addListener((src) => {
  if (!src.tabId) return;
  attached.delete(src.tabId);
  // Pending commands reject on detach and their `finally` keeps inFlight right; only drop the timer.
  clearTimeout(detachTimers.get(src.tabId));
  detachTimers.delete(src.tabId);
});

async function attach(tabId: number) {
  if (attached.has(tabId)) return;
  try {
    await chrome.debugger.attach({ tabId }, "1.3");
  } catch (e: any) {
    if (!String(e?.message).includes("already attached")) throw e;
  }
  attached.add(tabId);
}

/** Sends a CDP command. Once the tab is attached, calls made one after another reach it in that order. */
export async function cdp(tabId: number, method: string, params: { [key: string]: unknown } = {}): Promise<any> {
  if (!attached.has(tabId)) await attach(tabId);
  // Detach when idle so the "is debugging this browser" bar goes away. The idle timer starts only
  // after the last in-flight command finishes, so a long Runtime.evaluate (awaitPromise) is not cut
  // by "Detached while handling command".
  clearTimeout(detachTimers.get(tabId));
  detachTimers.delete(tabId);
  inFlight.set(tabId, (inFlight.get(tabId) ?? 0) + 1);
  try {
    return await chrome.debugger.sendCommand({ tabId }, method, params);
  } finally {
    const left = (inFlight.get(tabId) ?? 1) - 1;
    if (left > 0) {
      inFlight.set(tabId, left);
    } else {
      inFlight.delete(tabId);
      detachTimers.set(tabId, setTimeout(() => {
        detachTimers.delete(tabId);
        attached.delete(tabId);
        chrome.debugger.detach({ tabId }).catch(() => {});
      }, 20000));
    }
  }
}

/** Page.javascriptDialogOpening handlers of tabs whose navigation may meet a beforeunload prompt. */
export const dialogHandlers = new Map<number, (p: any) => void>();
chrome.debugger.onEvent.addListener((src, method, params) => {
  if (method === "Page.javascriptDialogOpening" && src.tabId) dialogHandlers.get(src.tabId)?.(params);
  if (method === "Page.fileChooserOpened" && src.tabId) chooserHandlers.get(src.tabId)?.(params);
});

/** Page.fileChooserOpened handlers of tabs where upload --trusted clicks a target that may open a file picker. */
export const chooserHandlers = new Map<number, (p: any) => void>();

/**
 * Trusted input sent to a minimized window, or one Chromium sees as covered, is dropped without an
 * error. The window state is checked too: while the debugger is attached, a minimized window's page
 * still reports "visible". A background tab of a visible window is hidden as well but does get the
 * input, so its page is not checked.
 */
export async function assertVisible(tabId: number, frameId = 0) {
  const tab = await chrome.tabs.get(tabId);
  let hidden = (await chrome.windows.get(tab.windowId)).state === "minimized";
  if (!hidden && tab.active) {
    try { hidden = (await frameCall(tabId, frameId, "visibility")) === "hidden"; } catch (e) { rethrowBlocked(e); /* restricted page */ }
  }
  if (hidden) {
    throw new Error("the browser window is minimized or covered, so real input would be lost; ask the user to bring " +
      "it to the front, or use click/type without --trusted, submit instead of type --submit, or select");
  }
}

export async function mouseClick(tabId: number, x: number, y: number) {
  // In a background tab (another agent's is in front) Chromium answers a mouse move only at the next animation
  // frame, which hidden tabs do not draw: ~5 s. The press sends it on at once, so the move is awaited after it.
  await attach(tabId);
  const moved = cdp(tabId, "Input.dispatchMouseEvent", { type: "mouseMoved", x, y });
  moved.catch(() => {}); // awaited below; this only keeps an early failure from going unhandled
  await cdp(tabId, "Input.dispatchMouseEvent", { type: "mousePressed", x, y, button: "left", clickCount: 1 });
  await cdp(tabId, "Input.dispatchMouseEvent", { type: "mouseReleased", x, y, button: "left", clickCount: 1 });
  await moved;
}

const KEYS: Record<string, [string, number, string?]> = {
  Enter: ["Enter", 13, "\r"], Tab: ["Tab", 9], Escape: ["Escape", 27], Backspace: ["Backspace", 8],
  Delete: ["Delete", 46], ArrowUp: ["ArrowUp", 38], ArrowDown: ["ArrowDown", 40], ArrowLeft: ["ArrowLeft", 37],
  ArrowRight: ["ArrowRight", 39], Home: ["Home", 36], End: ["End", 35], PageUp: ["PageUp", 33],
  PageDown: ["PageDown", 34], Space: [" ", 32, " "],
};
const MODIFIERS: Record<string, number> = { Alt: 1, Control: 2, Ctrl: 2, Meta: 4, Shift: 8 };

export async function pressKey(tabId: number, combo: string) {
  const parts = combo.split("+");
  const name = parts.pop()!;
  let modifiers = 0;
  for (const m of parts) {
    if (!(m in MODIFIERS)) throw new Error(`unknown modifier: ${m}`);
    modifiers |= MODIFIERS[m];
  }
  let key: string, code: string, vk: number, text: string | undefined;
  if (KEYS[name]) {
    [key, vk, text] = KEYS[name];
    code = name;
  } else if (name.length === 1) {
    key = name;
    vk = name.toUpperCase().charCodeAt(0);
    code = /[a-z]/i.test(name) ? "Key" + name.toUpperCase() : /\d/.test(name) ? "Digit" + name : "";
    text = name;
  } else {
    throw new Error(`unknown key: ${name}`);
  }
  if (modifiers & 7) text = undefined; // shortcuts don't insert text
  const base = { modifiers, key, code, windowsVirtualKeyCode: vk, nativeVirtualKeyCode: vk };
  await cdp(tabId, "Input.dispatchKeyEvent", { ...base, type: text ? "keyDown" : "rawKeyDown", text, unmodifiedText: text });
  await cdp(tabId, "Input.dispatchKeyEvent", { ...base, type: "keyUp" });
}

let fronting: Promise<unknown> = Promise.resolve(); // one tab brought to the front at a time

/**
 * Waits for a CDP command that a background tab (another agent's tab is in front) answers late, because it waits
 * for a frame and hidden tabs draw none: a screenshot (0.1 to 15 s) or a lone mouse move (5 s). Still running
 * after half a second, it brings its tab to the front until it ends, then gives the window its previous tab
 * back, unless something else was put in front meanwhile.
 */
export async function frontIfSlow<T>(tabId: number, command: Promise<T>): Promise<T> {
  let done = false;
  const tracked = command.finally(() => { done = true; });
  await Promise.race([tracked.catch(() => {}), sleep(500)]);
  if (done || (await chrome.tabs.get(tabId)).active) return tracked;
  const front = fronting.then(async () => {
    if (done) return;
    const { windowId } = await chrome.tabs.get(tabId);
    const [prev] = await chrome.tabs.query({ active: true, windowId });
    await retryTabEdit(() => chrome.tabs.update(tabId, { active: true }));
    await tracked.catch(() => {});
    const [now] = await chrome.tabs.query({ active: true, windowId });
    if (prev?.id !== undefined && now?.id === tabId) {
      await retryTabEdit(() => chrome.tabs.update(prev.id!, { active: true })).catch(() => {});
    }
  });
  fronting = front.catch(() => {});
  await front.catch(() => {}); // could not bring it to the front: wait for the command as it is
  return tracked;
}

export const captureScreenshot = (tabId: number, params: Record<string, unknown>) =>
  frontIfSlow(tabId, cdp(tabId, "Page.captureScreenshot", params));
