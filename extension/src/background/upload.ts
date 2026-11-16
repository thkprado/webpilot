// Service worker: upload to inputs made on click (filehook.js) and upload --trusted (files given by path).

import { Args, sleep } from "./config";
import { rethrowBlocked, answering, frameCall } from "./scripts";
import { cdp, dialogHandlers, chooserHandlers, assertVisible, mouseClick } from "./cdp";
import { Loc, locateUncovered } from "./frames";
import { ActResult } from "./actions";

/** What filehook.js caught: the input the page opened and the files it got, or why it could not take them. */
type Caught = { desc?: string; files?: { name: string; bytes: number }[]; error?: string };

/** How long upload waits, after clicking a target with no file input near it, for the page to open a picker. */
const PICKER_WAIT_MS = 2000;

/** Main world: arms filehook.js in this document for ms, with the files (null with native). */
const fileHookArm = (files: unknown[] | null, native: boolean, ms: number) => {
  const s = (window as any)[Symbol.for("webpilot.files")];
  if (s) Object.assign(s, { files, native, caught: null, until: Date.now() + ms });
};

/** Main world: what filehook.js caught so far (null: nothing); with stop, disarms it. */
const fileHookRead = (stop: boolean) => {
  const s = (window as any)[Symbol.for("webpilot.files")];
  if (!s) return null;
  const caught = s.caught;
  if (stop) Object.assign(s, { until: 0, files: null, caught: null });
  return caught;
};

async function armFileHook(tabId: number, frameId: number, files: unknown[] | null, native: boolean) {
  const target = { tabId, frameIds: [frameId] };
  await answering(tabId, [frameId], chrome.scripting.executeScript({ target, files: ["filehook.js"], world: "MAIN", injectImmediately: true }));
  await answering(tabId, [frameId], chrome.scripting.executeScript({
    target, func: fileHookArm, args: [files, native, 15000], world: "MAIN", injectImmediately: true,
  }));
}

async function readFileHook(tabId: number, frameId: number, stop: boolean): Promise<Caught | null> {
  try {
    const [r] = await answering(tabId, [frameId], chrome.scripting.executeScript({
      target: { tabId, frameIds: [frameId] }, func: fileHookRead, args: [stop], world: "MAIN", injectImmediately: true,
    }));
    return (r?.result as Caught | null) ?? null;
  } catch (e) {
    rethrowBlocked(e);
    return null; // the click navigated
  }
}

/**
 * upload to a target with no file input near it: clicks it with filehook.js armed, for pages that make their file
 * input in script on click and open it with click() or showPicker(). Null when no picker opened in PICKER_WAIT_MS.
 */
export async function uploadOnClick(tabId: number, loc: Loc, files: unknown[]): Promise<ActResult | null> {
  await armFileHook(tabId, loc.frameId, files, false);
  try {
    const clicked = await frameCall(tabId, loc.frameId, "click", loc.target);
    const end = Date.now() + PICKER_WAIT_MS;
    for (;;) {
      const c = await readFileHook(tabId, loc.frameId, false);
      if (c?.error) throw new Error(c.error);
      if (c) return { desc: c.desc, count: clicked.count, toggled: true, extra: { files: c.files, clicked: clicked.desc } };
      if (Date.now() >= end) return null;
      await sleep(50);
    }
  } finally {
    await readFileHook(tabId, loc.frameId, true);
  }
}

const UNREACHABLE = "upload --trusted cannot reach this frame (an iframe of another site, run by another process); " +
  "without --trusted, upload takes files up to 50 MB there";

/** The DOM node page/upload.ts marked with data-wp-upload=tok, in any frame the tab's debugger reaches; null elsewhere. */
async function markedNode(tabId: number, tok: string): Promise<number | null> {
  await cdp(tabId, "DOM.getDocument", { depth: 0 });
  // Plain text, not a selector: the search then also looks inside shadow roots.
  const { searchId, resultCount } = await cdp(tabId, "DOM.performSearch", { query: tok });
  try {
    if (!resultCount) return null;
    const { nodeIds } = await cdp(tabId, "DOM.getSearchResults", { searchId, fromIndex: 0, toIndex: resultCount });
    return nodeIds?.[0] ?? null;
  } finally {
    await cdp(tabId, "DOM.discardSearchResults", { searchId }).catch(() => {});
  }
}

/** A file input as the debugger sees it, described like fileDesc in page/upload.ts. */
async function inputDesc(tabId: number, backendNodeId: number): Promise<string> {
  try {
    const { node } = await cdp(tabId, "DOM.describeNode", { backendNodeId });
    const list: string[] = node.attributes ?? [];
    const at: Record<string, string> = {};
    for (let i = 0; i + 1 < list.length; i += 2) at[list[i]] = list[i + 1];
    return `input${at.id ? "#" + at.id : ""}${at.name ? ` name=${at.name}` : ""}` +
      `${at.accept ? ` accept=${at.accept.slice(0, 40)}` : ""}${"multiple" in at ? " multiple" : ""}`;
  } catch {
    return "input";
  }
}

/**
 * upload --trusted to a target with no file input near it: a real click, with the debugger catching the file
 * picker it opens (the input may have been made in script) and giving it the files by path. Null when no picker
 * opened in PICKER_WAIT_MS.
 */
async function chooserOnClick(tabId: number, loc: Loc, target: string, timeoutMs: number, paths: string[]) {
  await assertVisible(tabId, loc.frameId);
  const p = await locateUncovered(tabId, loc, target, timeoutMs, "upload");
  let opened: any = null;
  chooserHandlers.set(tabId, (ev) => { opened = opened ?? ev; });
  const pageOn = dialogHandlers.has(tabId); // eval or a navigation enabled Page already
  // Lets click() and showPicker() through to the debugger; refuses showOpenFilePicker(), which it cannot fill.
  await armFileHook(tabId, loc.frameId, null, true);
  try {
    if (!pageOn) await answering(tabId, [0], cdp(tabId, "Page.enable"));
    await cdp(tabId, "Page.setInterceptFileChooserDialog", { enabled: true });
    await mouseClick(tabId, p.x, p.y);
    const end = Date.now() + PICKER_WAIT_MS;
    while (!opened) {
      const c = await readFileHook(tabId, loc.frameId, false);
      if (c?.error) throw new Error(c.error);
      if (Date.now() >= end) return null;
      await sleep(50);
    }
    const desc = await inputDesc(tabId, opened.backendNodeId);
    if (paths.length > 1 && opened.mode !== "selectMultiple") {
      throw new Error(`${paths.length} files for a file input that takes one (no multiple attribute): ${desc}`);
    }
    await cdp(tabId, "DOM.setFileInputFiles", { files: paths, backendNodeId: opened.backendNodeId });
    return { desc, clicked: String(p.desc) };
  } finally {
    chooserHandlers.delete(tabId);
    await cdp(tabId, "Page.setInterceptFileChooserDialog", { enabled: false }).catch(() => {});
    if (!pageOn) await cdp(tabId, "Page.disable").catch(() => {});
    await readFileHook(tabId, loc.frameId, true);
  }
}

/**
 * upload --trusted: the browser reads the files from their paths (DOM.setFileInputFiles), so there is no size
 * limit, and the input's change event is trusted. The input is found as without --trusted: near the target, else
 * the one a real click on it opens, else further away.
 */
export async function uploadTrusted(tabId: number, loc: Loc, a: Args, files: any[]): Promise<ActResult> {
  const paths = files.map((f) => String(f.path));
  const sent = files.map((f) => ({ name: String(f.name), bytes: Number(f.bytes) }));
  const byPath = async (far: boolean) => {
    const tok = `wpupload${crypto.randomUUID().replace(/-/g, "")}`;
    const m = await frameCall(tabId, loc.frameId, "markUpload", loc.target, tok, files.length, far);
    try {
      const nodeId = await markedNode(tabId, tok);
      if (!nodeId) throw new Error(UNREACHABLE);
      if (m.input) await cdp(tabId, "DOM.setFileInputFiles", { files: paths, nodeId });
    } finally {
      await frameCall(tabId, loc.frameId, "unmarkUpload", tok).catch(() => {});
    }
    return m;
  };
  const done = (m: any): ActResult => ({ desc: m.input, count: m.count, reresolved: m.reresolved, toggled: true, extra: { files: sent } });
  const near = await byPath(false);
  if (near.input) return done(near);
  // A hidden target cannot get a real click; then only the inputs further away remain.
  if ((await frameCall(tabId, loc.frameId, "ready", loc.target)).ok) {
    const opened = await chooserOnClick(tabId, loc, String(a.target), (a.timeout ?? 5) * 1000, paths);
    if (opened) return { desc: opened.desc, count: near.count, toggled: true, extra: { files: sent, clicked: opened.clicked } };
  }
  return done(await byPath(true));
}
