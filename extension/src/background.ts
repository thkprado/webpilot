// Service worker: keeps a WebSocket to the local `webpilot` daemon and executes its commands.

import { PROFILE_NAME, PROFILE_NAME_HINT } from "./profile";

type Config = {
  token: string;
  port: number;
  mode: "real" | "temp";
  autoCaptcha?: boolean;
  blockedDomains?: string[];
};
type Args = Record<string, any>;
type State = { currentTabId?: number; groupId?: number };

let config: Config | null = null;
let ws: WebSocket | null = null;
let connecting = false;
let backoff = 500;

const sleep = (ms: number) => new Promise((r) => setTimeout(r, ms));

function badge(text: string, color: string) {
  chrome.action.setBadgeText({ text }).catch(() => {});
  chrome.action.setBadgeBackgroundColor({ color }).catch(() => {});
}

/** Name this browser profile reports to the daemon; kept in storage.local, which is per profile. */
async function profileName(): Promise<string> {
  const { profile } = await chrome.storage.local.get("profile");
  if (typeof profile === "string" && profile) return profile;
  const name = `profile-${crypto.randomUUID().slice(0, 4)}`;
  await chrome.storage.local.set({ profile: name });
  return name;
}

async function loadConfig(): Promise<Config | null> {
  try {
    const r = await fetch(chrome.runtime.getURL("config.json"), { cache: "no-store" });
    return r.ok ? await r.json() : null;
  } catch {
    return null;
  }
}

// ---------------------------------------------------------------- connection

async function connect() {
  if (connecting || (ws && ws.readyState <= WebSocket.OPEN)) return;
  connecting = true;
  try {
    config = await loadConfig();
    if (!config) {
      badge("CFG", "#b00020"); // run `webpilot setup`
      return;
    }
    const cfg = config;
    const profile = await profileName();
    chrome.action.setTitle({ title: `WebPilot (profile: ${profile})` }).catch(() => {});
    const sock = new WebSocket(`ws://127.0.0.1:${cfg.port}`);
    ws = sock;
    sock.onopen = () => {
      backoff = 500;
      sock.send(JSON.stringify({
        type: "hello", role: "extension", mode: cfg.mode, token: cfg.token, profile,
        version: chrome.runtime.getManifest().version, ua: navigator.userAgent,
      }));
      badge("ON", "#1b7f3b");
    };
    sock.onmessage = (ev) => {
      let msg: any;
      try { msg = JSON.parse(ev.data); } catch { return; }
      if (msg.id && msg.cmd) void handle(sock, msg);
    };
    sock.onclose = (ev) => {
      if (ws === sock) ws = null;
      // 4001: another profile already connected under this name; rename one with `webpilot profile rename`.
      if (ev.code === 4001) badge("DUP", "#b00020");
      else badge("OFF", "#777777");
      setTimeout(connect, backoff);
      backoff = Math.min(backoff * 2, 5000);
    };
    sock.onerror = () => {};
  } finally {
    connecting = false;
  }
}

// Traffic on the socket keeps the MV3 service worker alive; the alarm revives it if it was stopped anyway.
setInterval(() => {
  if (ws?.readyState === WebSocket.OPEN) ws.send('{"type":"ping"}');
}, 20000);
// Renamed (popup or `webpilot profile rename`): reconnect so the daemon sees the new name. The delay lets a
// pending reply to profile.set go out first. No oldValue = the name was just generated, nothing to redo.
chrome.storage.onChanged.addListener((changes, area) => {
  if (area === "local" && changes.profile?.oldValue) setTimeout(() => ws?.close(), 200);
});
chrome.alarms.create("webpilot-keepalive", { periodInMinutes: 0.5 });
chrome.alarms.onAlarm.addListener(() => void connect());
chrome.runtime.onStartup.addListener(() => void connect());
chrome.runtime.onInstalled.addListener(() => void connect());
void connect();

async function handle(sock: WebSocket, req: { id: string; cmd: string; args?: Args }) {
  let reply: any;
  try {
    const fn = commands[req.cmd];
    if (!fn) throw new Error(`unknown command: ${req.cmd}`);
    reply = { id: req.id, ok: true, result: (await fn(req.args || {})) ?? null };
  } catch (e: any) {
    reply = { id: req.id, ok: false, error: String(e?.message ?? e) };
  }
  if (sock.readyState === WebSocket.OPEN) sock.send(JSON.stringify(reply));
}

// ---------------------------------------------------------------- tabs

const getState = async () => (await chrome.storage.session.get(["currentTabId", "groupId"])) as State;
const setState = (s: State) => chrome.storage.session.set(s);

function checkBlocked(url?: string) {
  if (!url || !config?.blockedDomains?.length) return;
  let host = "";
  try { host = new URL(url).hostname; } catch { return; }
  for (const d of config.blockedDomains) {
    if (host === d || host.endsWith("." + d)) throw new Error(`domain blocked by WebPilot config: ${host}`);
  }
}

async function addToGroup(tabId: number) {
  const st = await getState();
  if (st.groupId !== undefined) {
    try {
      await chrome.tabs.group({ tabIds: [tabId], groupId: st.groupId });
      return;
    } catch { /* group was closed */ }
  }
  try {
    const groupId = await chrome.tabs.group({ tabIds: [tabId] });
    await chrome.tabGroups.update(groupId, { title: "WebPilot", color: "purple" });
    await setState({ groupId });
  } catch { /* tab groups unavailable */ }
}

async function newTab(): Promise<chrome.tabs.Tab> {
  const tab = await chrome.tabs.create({ url: "about:blank", active: true });
  if (config?.mode === "real") await addToGroup(tab.id!);
  await setState({ currentTabId: tab.id });
  return tab;
}

/** The tab a command acts on: args.tabId, else the agent's current tab, else a fresh one. */
async function resolveTab(args: Args): Promise<chrome.tabs.Tab> {
  const explicit = args.tabId !== undefined && args.tabId !== null;
  const id = explicit ? Number(args.tabId) : (await getState()).currentTabId;
  if (id !== undefined) {
    try {
      const tab = await chrome.tabs.get(id);
      checkBlocked(tab.url);
      return tab;
    } catch (e: any) {
      if (explicit || String(e?.message).includes("blocked")) throw new Error(String(e?.message ?? e));
    }
  }
  return newTab();
}

function waitForLoad(tabId: number, timeoutMs = 30000): Promise<boolean> {
  return new Promise((resolve) => {
    let sawLoading = false;
    const listener = (id: number, info: chrome.tabs.OnUpdatedInfo) => {
      if (id !== tabId) return;
      if (info.status === "loading") sawLoading = true;
      if (info.status === "complete" && sawLoading) done(true);
    };
    // Same-document navigations (hash changes) never report "loading".
    const probe = setTimeout(async () => {
      if (sawLoading) return;
      try { if ((await chrome.tabs.get(tabId)).status === "complete") done(true); } catch { done(false); }
    }, 3000);
    const timer = setTimeout(() => done(false), timeoutMs);
    function done(v: boolean) {
      chrome.tabs.onUpdated.removeListener(listener);
      clearTimeout(timer);
      clearTimeout(probe);
      resolve(v);
    }
    chrome.tabs.onUpdated.addListener(listener);
  });
}

/** Waits until the DOM has had no mutations for quietMs (AJAX updates never change the tab status). */
async function domIdle(tabId: number, quietMs: number, capMs: number) {
  const end = Date.now() + capMs;
  while (Date.now() < end) {
    try { if ((await pageCall(tabId, "idle")).sinceMs >= quietMs) return; } catch { /* navigating */ }
    await sleep(100);
  }
}

type Net = { pending: () => number; quietMs: () => number; stop: () => void };

/**
 * Counts the tab's in-flight page loads and XHR/fetch requests while an action settles. Listeners
 * exist only during the action, so other browsing never wakes the service worker.
 */
function watchNetwork(tabId: number): Net {
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
async function settle(
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
      } catch { /* navigating */ }
    }
    await sleep(100);
  }
}

/**
 * Polls until the target exists, is visible and enabled (it may still be rendering). Selectors and
 * text= targets not found in the main frame are looked for in iframes. Returns the frame and
 * whether a stale ref was re-resolved.
 */
async function waitTarget(tabId: number, raw: string, timeoutMs: number): Promise<Loc & { reresolved: boolean }> {
  const loc = splitRef(raw);
  const anyFrame = loc.frameId === 0 && !/^e\d+$/.test(loc.target);
  const end = Date.now() + timeoutMs;
  for (;;) {
    let r: { ok: boolean; reason?: string; fatal?: boolean; reresolved?: boolean };
    try {
      r = await frameCall(tabId, loc.frameId, "ready", loc.target);
    } catch (e: any) {
      r = { ok: false, reason: String(e?.message ?? e) }; // page navigating or restricted
    }
    if (r.ok) return { ...loc, reresolved: !!r.reresolved };
    if (r.fatal) throw new Error(r.reason);
    if (anyFrame) {
      try {
        const hit = (await allFramesCall(tabId, "ready", loc.target)).find((f) => f.frameId !== 0 && f.value?.ok);
        if (hit) return { frameId: hit.frameId, target: loc.target, reresolved: false };
      } catch { /* navigating */ }
    }
    const reason = r.reason;
    if (Date.now() >= end) throw new Error(`${reason} (waited ${timeoutMs / 1000}s)`);
    await sleep(150);
  }
}

/** Polls until the selector is visible and/or the text is in some frame of the page (or, with gone, in none). */
async function waitFor(tabId: number, selector: string | null, text: string | null, timeoutMs: number, gone = false) {
  const start = Date.now();
  while (Date.now() - start < timeoutMs) {
    try {
      const present = (await allFramesCall(tabId, "check", selector, text)).some((f) => f.value === true);
      if (present !== gone) return { found: true, ms: Date.now() - start };
    } catch { /* page navigating */ }
    await sleep(250);
  }
  return { found: false, ms: Date.now() - start };
}

/** Waits until no frame has a visible aria-busy="true" element (up to timeoutMs). */
async function waitNotBusy(tabId: number, timeoutMs: number) {
  const end = Date.now() + timeoutMs;
  while (Date.now() < end) {
    try {
      if (!(await allFramesCall(tabId, "idle")).some((f) => f.value?.busy)) return;
    } catch { /* navigating */ }
    await sleep(100);
  }
}

type ActResult = { desc?: string; count: number; reresolved?: boolean; toggled?: boolean; extra?: Record<string, unknown> };

/**
 * Runs click/type/press/submit: waits for the target, performs the action, settles, reports whether
 * the page changed, and optionally waits for something (args.waitText / args.waitSelector) that
 * marks the next state. With such a marker the settle gives up on DOM churn sooner, since the
 * marker is what tells that the next state arrived (pages with a running clock never go quiet).
 * `after` adds fields read once the page settled.
 */
async function act(
  tabId: number, a: Args, target: string | null, key: string, run: (loc: Loc) => Promise<ActResult>,
  after?: () => Promise<Record<string, unknown>>,
) {
  const found = target ? await waitTarget(tabId, target, (a.timeout ?? 5) * 1000) : { frameId: 0, target: "", reresolved: false };
  const url = (await chrome.tabs.get(tabId)).url;
  const net = watchNetwork(tabId);
  try {
    const r = await run(found);
    const marker = !!(a.waitText || a.waitSelector);
    const { navigated, busy } = await settle(tabId, net, found.frameId, marker ? 1500 : 5000);
    const late = after ? await after() : {};
    const info = await tabInfo(tabId);
    let count = r.count;
    let frameUrl: string | undefined;
    try {
      const s = await frameCall(tabId, found.frameId, "idle");
      count = s.count;
      if (found.frameId !== 0) frameUrl = s.url;
    } catch { /* restricted page */ }
    const out: any = {
      ...(r.desc ? { [key]: r.desc } : {}),
      ...r.extra,
      ...late,
      ...(found.reresolved || r.reresolved ? { reresolved: true } : {}),
      changed: navigated || !!r.toggled || info.url !== url || count > r.count,
      ...(busy ? { busy } : {}),
      ...info,
      ...(frameUrl ? { frameUrl } : {}),
    };
    if (a.waitText || a.waitSelector) {
      out.waited = await waitFor(tabId, a.waitSelector ?? null, a.waitText ?? null, (a.waitTimeout ?? 10) * 1000);
      // The marker can show before the rest of the step (AJAX players): let aria-busy regions finish.
      if (out.waited.found) await waitNotBusy(tabId, 3000);
    }
    return out;
  } finally {
    net.stop();
  }
}

/** DOM mutation count before an action that does not go through a page function. */
async function armCount(tabId: number, frameId = 0): Promise<number> {
  try { return (await frameCall(tabId, frameId, "arm")).count; } catch { return 0; }
}

async function tabInfo(tabId: number) {
  const t = await chrome.tabs.get(tabId);
  return { tabId, url: t.url, title: t.title, status: t.status };
}

// ---------------------------------------------------------------- page scripts

// Async so that page functions may return a Promise (executeScript awaits the one returned here).
const callWp = async (n: string, a: any[]) => {
  const wp = (globalThis as any).__wp;
  // Missing, or injected by an older build of the extension that lacks this function.
  if (!wp || typeof wp[n] !== "function") return { missing: true };
  try { return { value: await wp[n](...a) }; } catch (e: any) { return { error: String(e?.message ?? e) }; }
};

/** HTTP request from the page's context (its cookies and session); runs via executeScript, so self-contained. */
const pageFetch = async (url: string, method: string, headers: Record<string, string>, body: string | null,
                         timeoutMs: number) => {
  const ctl = new AbortController();
  const timer = setTimeout(() => ctl.abort(), timeoutMs);
  try {
    const r = await fetch(url, { method, headers, body, signal: ctl.signal });
    const buf = new Uint8Array(await r.arrayBuffer());
    const type = r.headers.get("content-type") || "";
    const charset = /charset=([^;]+)/i.exec(type)?.[1]?.trim() || "utf-8";
    const out: Record<string, unknown> = {
      status: r.status, statusText: r.statusText, url: r.url, headers: Object.fromEntries(r.headers),
    };
    let text: string | null = null;
    if (/^text\/|json|xml|javascript|ecmascript|csv|yaml|x-www-form-urlencoded/i.test(type)) {
      try { text = new TextDecoder(charset).decode(buf); } catch { text = new TextDecoder().decode(buf); }
    } else if (!type) {
      try { text = new TextDecoder("utf-8", { fatal: true }).decode(buf); } catch { /* binary */ }
    }
    if (text !== null) {
      out.body = text;
    } else {
      let bin = "";
      for (let i = 0; i < buf.length; i += 0x8000) bin += String.fromCharCode(...buf.subarray(i, i + 0x8000));
      out.bodyBase64 = btoa(bin);
    }
    return out;
  } catch (e: any) {
    if (ctl.signal.aborted) return { error: `fetch timed out after ${timeoutMs / 1000} s` };
    return { error: `fetch failed (network error, or CORS for another origin): ${e?.message ?? e}` };
  } finally {
    clearTimeout(timer);
  }
};

/** Calls globalThis.__wp[name](...args) in one frame of the tab, injecting page.js first if needed. */
async function frameCall<T = any>(tabId: number, frameId: number, name: string, ...args: any[]): Promise<T> {
  const target = { tabId, frameIds: [frameId] };
  const run = async () => {
    const [res] = await chrome.scripting.executeScript({ target, func: callWp, args: [name, args] });
    return res?.result as any;
  };
  let r = await run();
  if (r?.missing) {
    await chrome.scripting.executeScript({ target, files: ["page.js"] });
    r = await run();
  }
  if (!r) throw new Error("could not run script in this tab (restricted page?)");
  if (r.error) throw new Error(r.error);
  if (r.value && typeof r.value === "object" && r.value.error) throw new Error(r.value.error);
  return r.value;
}

/** Calls globalThis.__wp[name](...args) in the tab's main frame. */
const pageCall = <T = any>(tabId: number, name: string, ...args: any[]) => frameCall<T>(tabId, 0, name, ...args);

/** Calls globalThis.__wp[name](...args) in every frame that allows scripts; frames that fail are left out. */
async function allFramesCall(tabId: number, name: string, ...args: any[]): Promise<{ frameId: number; value: any }[]> {
  const run = () => chrome.scripting.executeScript({ target: { tabId, allFrames: true }, func: callWp, args: [name, args] });
  let res = await run();
  const missing = res.filter((r) => (r.result as any)?.missing).map((r) => r.frameId);
  if (missing.length) {
    await chrome.scripting.executeScript({ target: { tabId, frameIds: missing }, files: ["page.js"] }).catch(() => {});
    res = await run();
  }
  return res
    .filter((r) => r.result && !(r.result as any).missing && !(r.result as any).error)
    .map((r) => ({ frameId: r.frameId, value: (r.result as any).value }));
}

// ---------------------------------------------------------------- frames

/** Where an action runs: refs from inside an iframe look like f<frameId>e12. */
type Loc = { frameId: number; target: string };
type FrameRead = { url: string; chars: number };

function splitRef(target: string): Loc {
  const m = /^f(\d+)(e\d+)$/.exec(target);
  return m ? { frameId: Number(m[1]), target: m[2] } : { frameId: 0, target };
}

/**
 * Replaces the iframe placeholders (\u0001token lines) of a snapshot with the snapshots of those
 * frames, refs prefixed with the frame id. Frames that cannot be reached are left as [iframe ...].
 * Each inlined frame's URL and own text size go to `frames` (the session log credits them to their domain).
 */
async function inlineFrames(
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
async function selectorCall(tabId: number, selector: string | null, name: string, ...args: any[]) {
  try {
    return await pageCall(tabId, name, ...args);
  } catch (e: any) {
    if (!selector || !String(e?.message).startsWith("selector not found")) throw e;
    const hit = (await allFramesCall(tabId, name, ...args)).find((f) => f.frameId !== 0 && f.value && !f.value.error);
    if (!hit) throw e;
    return { ...hit.value, frame: `f${hit.frameId}` };
  }
}

/** Viewport coordinates of a target for trusted input, adding the offsets of the iframes it is in. */
async function locateAbs(tabId: number, loc: Loc) {
  const p = await frameCall(tabId, loc.frameId, "locate", loc.target);
  let frameId = loc.frameId;
  for (let depth = 0; frameId !== 0; depth++) {
    const { token } = await frameCall(tabId, frameId, "frameInfo");
    const hit = token && depth < 5 ? (await allFramesCall(tabId, "frameOffset", token)).find((f) => f.value) : undefined;
    if (!hit) throw new Error("could not locate the iframe on the page; take a new snapshot");
    p.x += hit.value.x;
    p.y += hit.value.y;
    frameId = hit.frameId;
  }
  return p;
}

// ---------------------------------------------------------------- debugger (trusted input)

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

async function cdp(tabId: number, method: string, params: { [key: string]: unknown } = {}): Promise<any> {
  if (!attached.has(tabId)) {
    try {
      await chrome.debugger.attach({ tabId }, "1.3");
    } catch (e: any) {
      if (!String(e?.message).includes("already attached")) throw e;
    }
    attached.add(tabId);
  }
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

/** Message for a failed `eval`. Runtime errors already carry a stack trace; syntax errors only say
 * "Invalid or unexpected token", so they get the line, the column and an excerpt of the source with
 * a caret under the offending character. Line breaks and tabs in the excerpt are shown as ⏎ and ⇥,
 * so the excerpt stays on one line and the caret lines up. */
function evalError(source: string, details: any, isFunction: boolean): string {
  const message = details.exception?.description || details.text || "evaluation failed";
  if (details.exception?.className !== "SyntaxError" || typeof details.lineNumber !== "number") return message;
  const line = details.lineNumber;
  // Runtime.callFunctionOn compiles the declaration inside parentheses: one extra column on line 0.
  const column = Math.max(0, (details.columnNumber ?? 0) - (isFunction && line === 0 ? 1 : 0));
  const lines = source.split("\n");
  if (line >= lines.length) return message;
  let offset = column;
  for (let i = 0; i < line; i++) offset += lines[i].length + 1;
  const start = Math.max(0, offset - 40);
  const end = Math.min(source.length, offset + 30);
  const visible = (s: string) => s.replace(/\n/g, "⏎").replace(/\t/g, "⇥").replace(/\r/g, "␍");
  const excerpt = (start > 0 ? "…" : "") + visible(source.slice(start, end)) + (end < source.length ? "…" : "");
  const caret = " ".repeat((start > 0 ? 1 : 0) + offset - start) + "^";
  return `${message} at line ${line + 1}, column ${column + 1}:\n  ${excerpt}\n  ${caret}`;
}

/**
 * Trusted input sent to a minimized window, or one Chromium sees as covered, is dropped without an
 * error. The window state is checked too: while the debugger is attached, a minimized window's page
 * still reports "visible". A background tab of a visible window is hidden as well but does get the
 * input, so its page is not checked.
 */
async function assertVisible(tabId: number, frameId = 0) {
  const tab = await chrome.tabs.get(tabId);
  let hidden = (await chrome.windows.get(tab.windowId)).state === "minimized";
  if (!hidden && tab.active) {
    try { hidden = (await frameCall(tabId, frameId, "visibility")) === "hidden"; } catch { /* restricted page */ }
  }
  if (hidden) {
    throw new Error("the browser window is minimized or covered, so real input would be lost; bring it to the front, " +
      "or use click/type without --trusted, or select");
  }
}

async function mouseClick(tabId: number, x: number, y: number) {
  await cdp(tabId, "Input.dispatchMouseEvent", { type: "mouseMoved", x, y });
  await cdp(tabId, "Input.dispatchMouseEvent", { type: "mousePressed", x, y, button: "left", clickCount: 1 });
  await cdp(tabId, "Input.dispatchMouseEvent", { type: "mouseReleased", x, y, button: "left", clickCount: 1 });
}

const KEYS: Record<string, [string, number, string?]> = {
  Enter: ["Enter", 13, "\r"], Tab: ["Tab", 9], Escape: ["Escape", 27], Backspace: ["Backspace", 8],
  Delete: ["Delete", 46], ArrowUp: ["ArrowUp", 38], ArrowDown: ["ArrowDown", 40], ArrowLeft: ["ArrowLeft", 37],
  ArrowRight: ["ArrowRight", 39], Home: ["Home", 36], End: ["End", 35], PageUp: ["PageUp", 33],
  PageDown: ["PageDown", 34], Space: [" ", 32, " "],
};
const MODIFIERS: Record<string, number> = { Alt: 1, Control: 2, Ctrl: 2, Meta: 4, Shift: 8 };

async function pressKey(tabId: number, combo: string) {
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

// ---------------------------------------------------------------- captcha

async function solveCheckbox(tabId: number) {
  const found = await pageCall(tabId, "findCaptcha");
  if (!found.widgets.length) {
    return { present: found.solved, solved: found.solved, challenge: found.challenge };
  }
  const w = found.widgets[0];
  await mouseClick(tabId, w.x + (w.kind === "recaptcha" ? 27 : 30), w.y + w.h / 2);
  await sleep(2500);
  const after = await pageCall(tabId, "findCaptcha");
  return {
    present: true,
    kind: w.kind,
    clicked: true,
    solved: after.solved,
    challenge: after.challenge,
    ...(after.challenge ? { note: "A visual challenge appeared; ask the user to solve it in the browser." } : {}),
  };
}

async function autoCaptcha(tabId: number) {
  if (!config?.autoCaptcha) return undefined; // opt-in: "auto_captcha": true in ~/.webpilot/config.json
  try {
    const found = await pageCall(tabId, "findCaptcha");
    if (!found.widgets.length && !found.challenge) return undefined;
    return await solveCheckbox(tabId);
  } catch {
    return undefined;
  }
}

// ---------------------------------------------------------------- commands

async function navigate(tabId: number, action: () => Promise<unknown>) {
  const loaded = waitForLoad(tabId);
  await action();
  const ok = await loaded;
  if (ok) await domIdle(tabId, 300, 3000); // let client-side rendering finish before a snapshot
  const captcha = await autoCaptcha(tabId);
  return { ...(await tabInfo(tabId)), loaded: ok, ...(captcha ? { captcha } : {}) };
}

const commands: Record<string, (a: Args) => Promise<any>> = {
  ping: async () => {
    const [tab] = await chrome.tabs.query({ active: true, lastFocusedWindow: true });
    return { pong: true, mode: config?.mode, profile: await profileName(),
             activeTab: tab ? { title: tab.title, url: tab.url } : null };
  },
  "profile.set": async (a) => {
    const name = String(a.name ?? "");
    if (!PROFILE_NAME.test(name)) throw new Error(`profile name: ${PROFILE_NAME_HINT}`);
    await chrome.storage.local.set({ profile: name }); // the storage listener reconnects under the new name
    return { profile: name };
  },

  "tabs.list": async () => {
    const st = await getState();
    return (await chrome.tabs.query({})).map((t) => ({
      id: t.id, title: t.title, url: t.url, active: t.active, windowId: t.windowId,
      agent: st.groupId !== undefined && t.groupId === st.groupId,
      current: t.id === st.currentTabId,
    }));
  },
  "tab.new": async (a) => {
    const tab = await newTab();
    if (!a.url) return tabInfo(tab.id!);
    checkBlocked(a.url);
    return navigate(tab.id!, () => chrome.tabs.update(tab.id!, { url: a.url }));
  },
  "tab.use": async (a) => {
    const tab = await chrome.tabs.get(Number(a.tabId));
    checkBlocked(tab.url);
    await chrome.tabs.update(tab.id!, { active: true });
    await setState({ currentTabId: tab.id });
    return tabInfo(tab.id!);
  },
  "tab.close": async (a) => {
    const st = await getState();
    const id = a.tabId ?? st.currentTabId;
    if (id === undefined) throw new Error("no tab to close");
    await chrome.tabs.remove(Number(id));
    if (Number(id) === st.currentTabId) await chrome.storage.session.remove("currentTabId");
    return { closed: Number(id) };
  },
  "tab.info": async (a) => tabInfo((await resolveTab(a)).id!),

  goto: async (a) => {
    if (!a.url) throw new Error("url is required");
    checkBlocked(a.url);
    const tab = a.newTab ? await newTab() : await resolveTab(a);
    return navigate(tab.id!, () => chrome.tabs.update(tab.id!, { url: a.url }));
  },
  back: async (a) => {
    const tab = await resolveTab(a);
    return navigate(tab.id!, () => chrome.tabs.goBack(tab.id!));
  },
  forward: async (a) => {
    const tab = await resolveTab(a);
    return navigate(tab.id!, () => chrome.tabs.goForward(tab.id!));
  },
  reload: async (a) => {
    const tab = await resolveTab(a);
    return navigate(tab.id!, () => chrome.tabs.reload(tab.id!));
  },

  snapshot: async (a) => {
    const tab = await resolveTab(a);
    const maxChars = a.maxChars ?? 15000;
    const snap = await pageCall(tab.id!, "snapshot", a.selector ?? null, maxChars, !!a.interactive);
    const frames: FrameRead[] = [];
    const text = await inlineFrames(tab.id!, snap.text, maxChars, !!a.interactive, frames);
    if (text.length > maxChars) snap.truncated = true;
    return { tabId: tab.id, ...snap, text: text.slice(0, maxChars), ...(frames.length ? { frames } : {}) };
  },
  html: async (a) => {
    const tab = await resolveTab(a);
    const page = await selectorCall(tab.id!, a.selector ?? null, "html", a.selector ?? null);
    if (!a.frames || a.selector) return { tabId: tab.id, ...page };
    // Whole documents of the iframes too, for parsers of embedded content (quizzes, widgets).
    const frames = (await allFramesCall(tab.id!, "html", null))
      .filter((f) => f.frameId !== 0 && f.value?.html)
      .map((f) => ({ frame: `f${f.frameId}`, ...f.value }));
    return { tabId: tab.id, ...page, frames };
  },
  text: async (a) => {
    const tab = await resolveTab(a);
    return { tabId: tab.id, ...(await selectorCall(tab.id!, a.selector ?? null, "text", a.selector ?? null, a.maxChars ?? 50000)) };
  },

  click: async (a) => {
    const tab = await resolveTab(a);
    // A click on a dropdown option can land and choose nothing (the menu closed first): say whether it chose.
    let option: Loc | null = null;
    return act(tab.id!, a, a.target, "clicked", async (loc) => {
      if (a.trusted) await assertVisible(tab.id!, loc.frameId);
      if (await frameCall(tab.id!, loc.frameId, "watchOption", loc.target)) option = loc;
      if (!a.trusted) return frameCall(tab.id!, loc.frameId, "click", loc.target);
      const count = await armCount(tab.id!, loc.frameId);
      const p = await locateAbs(tab.id!, loc);
      await mouseClick(tab.id!, p.x, p.y);
      return { desc: p.desc, count };
    }, async () => {
      const loc = option as Loc | null;
      const r = loc ? await frameCall(tab.id!, loc.frameId, "optionResult").catch(() => null) : null;
      if (!r) return {};
      if (r.selected) return { selected: true };
      const ref = (loc!.frameId ? `f${loc!.frameId}` : "") + r.ref;
      return { selected: false, value: r.value, hint: `use select ${ref} ${JSON.stringify(r.option)}` };
    });
  },
  type: async (a) => {
    const tab = await resolveTab(a);
    const clear = a.clear !== false;
    return act(tab.id!, a, a.target, "typed", async (loc) => {
      if (a.trusted || a.submit) await assertVisible(tab.id!, loc.frameId);
      let r: ActResult;
      if (a.trusted) {
        r = await frameCall(tab.id!, loc.frameId, "focus", loc.target, clear);
        await cdp(tab.id!, "Input.insertText", { text: String(a.text ?? "") });
      } else {
        r = await frameCall(tab.id!, loc.frameId, "type", loc.target, String(a.text ?? ""), clear);
      }
      if (a.submit) await pressKey(tab.id!, "Enter");
      return r;
    });
  },
  select: async (a) => {
    const tab = await resolveTab(a);
    return act(tab.id!, a, a.target, "chose",
      (loc) => frameCall(tab.id!, loc.frameId, "choose", loc.target, String(a.text ?? "")));
  },
  press: async (a) => {
    const tab = await resolveTab(a);
    return act(tab.id!, a, null, "pressed", async () => {
      await assertVisible(tab.id!);
      const count = await armCount(tab.id!);
      await pressKey(tab.id!, String(a.key));
      return { desc: String(a.key), count };
    });
  },
  submit: async (a) => {
    const tab = await resolveTab(a);
    return act(tab.id!, a, a.target ?? null, "submitted",
      (loc) => frameCall(tab.id!, loc.frameId, "submitForm", a.target ? loc.target : null));
  },
  scroll: async (a) => {
    const tab = await resolveTab(a);
    const to = a.to ?? "down";
    if (["down", "up", "top", "bottom"].includes(to)) return pageCall(tab.id!, "scroll", to, a.amount ?? null);
    const loc = await waitTarget(tab.id!, to, (a.timeout ?? 5) * 1000);
    return frameCall(tab.id!, loc.frameId, "scroll", loc.target, a.amount ?? null);
  },
  wait: async (a) => {
    const tab = await resolveTab(a);
    return waitFor(tab.id!, a.selector ?? null, a.text ?? null, (a.timeout ?? 10) * 1000, !!a.gone);
  },
  eval: async (a) => {
    const tab = await resolveTab(a);
    const source = String(a.expression);
    let r;
    if (Array.isArray(a.args)) {
      // The expression is a function; the arguments travel as JSON values, never as code.
      const global = await cdp(tab.id!, "Runtime.evaluate", { expression: "globalThis" });
      try {
        r = await cdp(tab.id!, "Runtime.callFunctionOn", {
          functionDeclaration: source, objectId: global.result.objectId,
          arguments: a.args.map((value: unknown) => ({ value })),
          returnByValue: true, awaitPromise: true, userGesture: true,
        });
      } catch (e: any) {
        if (String(e?.message).includes("does not evaluate to a function")) {
          throw new Error("with arguments, the expression must be a function, such as (text, n) => ...");
        }
        throw e;
      }
    } else {
      r = await cdp(tab.id!, "Runtime.evaluate", {
        expression: source, returnByValue: true, awaitPromise: true, userGesture: true,
      });
    }
    if (r.exceptionDetails) throw new Error(evalError(source, r.exceptionDetails, Array.isArray(a.args)));
    return r.result?.value ?? null;
  },
  fetch: async (a) => {
    const method = String(a.method ?? "GET").toUpperCase();
    if (!["GET", "HEAD"].includes(method) && !a.allowWrite) {
      throw new Error(`fetch ${method} can change data on the site: confirm with the user, then pass --allow-write`);
    }
    const tab = await resolveTab(a);
    if (!/^https?:/.test(tab.url ?? "")) {
      throw new Error(`fetch runs from the current tab's page, which is ${tab.url || "empty"}: open the site first (goto URL)`);
    }
    let url: string;
    try { url = new URL(String(a.url), tab.url).href; } catch { throw new Error(`bad URL for this tab: ${a.url}`); }
    checkBlocked(url);
    const [res] = await chrome.scripting.executeScript({
      target: { tabId: tab.id! }, func: pageFetch, world: "MAIN", // the isolated world's requests never left the tab
      args: [url, method, a.headers ?? {}, a.body ?? null, a.timeoutMs ?? 120000],
    });
    const r = res?.result as any;
    if (!r) throw new Error("could not run script in this tab (restricted page?)");
    if (r.error) throw new Error(r.error);
    checkBlocked(r.url); // after redirects
    return r;
  },
  screenshot: async (a) => {
    const tab = await resolveTab(a);
    const params: any = { format: "png" };
    if (a.full) {
      const m = await cdp(tab.id!, "Page.getLayoutMetrics");
      const size = m.cssContentSize || m.contentSize;
      params.captureBeyondViewport = true;
      params.clip = { x: 0, y: 0, width: size.width, height: Math.min(size.height, 16000), scale: 1 };
    }
    const r = await cdp(tab.id!, "Page.captureScreenshot", params);
    return { tabId: tab.id, format: "png", data: r.data };
  },
  captcha: async (a) => solveCheckbox((await resolveTab(a)).id!),
};
