// Service worker: keeps a WebSocket to the local `webpilot` daemon and executes its commands. The commands are
// in background/commands.ts; this file holds the connection and the check that the build on disk is this one.

import { Args, profileName, reloadConfig } from "./background/config";
import { commands } from "./background/commands";

let ws: WebSocket | null = null;
let connecting = false;
let backoff = 500;

/** The build this worker was loaded from (build.mjs puts it in), and whether extension/dist holds another one. */
declare const __WP_BUILD__: string;
let stale = false;

const STALE_HINT = "the WebPilot extension running in the browser is older than its build in extension/dist " +
  "(rebuilt since the browser loaded it): ask the user to click reload on the WebPilot card of the browser's " +
  "extensions page (chrome://extensions, edge://extensions, ...), then retry";

/** Rebuilt but not reloaded: this worker runs the old code, while scripts injected into pages come from the new
 * build. Unpacked extensions serve their files from disk, so dist/build.json is the build there now. */
async function checkStale(): Promise<boolean> {
  try {
    const r = await fetch(chrome.runtime.getURL("build.json"), { cache: "no-store" });
    const disk = r.ok ? (await r.json()).build : null;
    const now = typeof disk === "string" && disk !== __WP_BUILD__;
    if (now !== stale) {
      stale = now;
      if (ws?.readyState === WebSocket.OPEN) {
        badge(stale ? "OLD" : "ON", stale ? "#b35c00" : "#1b7f3b");
        ws.send(JSON.stringify({ type: "info", stale }));
      }
    }
  } catch {
    // build.json unreadable: keep the last answer
  }
  return stale;
}

function badge(text: string, color: string) {
  chrome.action.setBadgeText({ text }).catch(() => {});
  chrome.action.setBadgeBackgroundColor({ color }).catch(() => {});
}

// ---------------------------------------------------------------- connection

async function connect() {
  if (connecting || (ws && ws.readyState <= WebSocket.OPEN)) return;
  connecting = true;
  try {
    const cfg = await reloadConfig();
    if (!cfg) {
      badge("CFG", "#b00020"); // run `webpilot setup`
      return;
    }
    const profile = await profileName();
    chrome.action.setTitle({ title: `WebPilot (profile: ${profile})` }).catch(() => {});
    const sock = new WebSocket(`ws://127.0.0.1:${cfg.port}`);
    ws = sock;
    sock.onopen = async () => {
      backoff = 500;
      await checkStale();
      sock.send(JSON.stringify({
        type: "hello", role: "extension", mode: cfg.mode, token: cfg.token, profile,
        version: chrome.runtime.getManifest().version, build: __WP_BUILD__, stale, ua: navigator.userAgent,
      }));
      badge(stale ? "OLD" : "ON", stale ? "#b35c00" : "#1b7f3b");
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
chrome.alarms.onAlarm.addListener(() => void connect().then(checkStale));
chrome.runtime.onStartup.addListener(() => void connect());
chrome.runtime.onInstalled.addListener(() => void connect());
void connect();

async function handle(sock: WebSocket, req: { id: string; cmd: string; args?: Args; agent?: unknown }) {
  let reply: any;
  try {
    const fn = commands[req.cmd];
    if (!fn) throw new Error(`unknown command: ${req.cmd}`);
    // Whose current tab the command uses (background/tabs.ts): from the request, never from the command's args.
    const args: Args = { ...(req.args || {}), _agent: typeof req.agent === "string" && req.agent ? req.agent : undefined };
    reply = { id: req.id, ok: true, result: (await fn(args)) ?? null };
  } catch (e: any) {
    const error = String(e?.message ?? e);
    // An old worker fails in ways its error cannot explain (an unknown command, a page script it does not match).
    reply = { id: req.id, ok: false, error: (await checkStale()) ? `${error}; ${STALE_HINT}` : error };
  }
  if (sock.readyState === WebSocket.OPEN) sock.send(JSON.stringify(reply));
}
