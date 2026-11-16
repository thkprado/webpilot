// Service worker: the command table: one entry per command the daemon sends.

import { PROFILE_NAME, PROFILE_NAME_HINT } from "../profile";
import { retryTabEdit } from "../tabedit";
import { Args, config, profileName } from "./config";
import { checkBlocked } from "./domains";
import { getState, setState, markKey, newTab, resolveTab, tabInfo } from "./tabs";
import { RESTRICTED, explain, PageBlocked, answering, frameCall, pageCall, allFramesCall } from "./scripts";
import { cdp, assertVisible, mouseClick, pressKey } from "./cdp";
import { Loc, FrameRead, inlineFrames, selectorCall, locateAbs, locateUncovered, SHOT_MARGIN } from "./frames";
import { domIdle, waitTarget, waitFor } from "./wait";
import { Dialog, acceptUnload, answerNatively, checkDialogArg, anyDismissed, DISMISSED } from "./dialogs";
import { solveCheckbox } from "./captcha";
import { ActResult, act, unchangedHint, armCount, navigate, historyStep } from "./actions";
import { uploadOnClick, uploadTrusted } from "./upload";
import { evaluate } from "./eval";
import { OWN_FETCH, pageFetch } from "./fetch";

export const commands: Record<string, (a: Args) => Promise<any>> = {
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
    checkBlocked(a.url); // before the tab opens, so a refused URL leaves the current tab as it was
    const tab = await newTab();
    if (!a.url) return tabInfo(tab.id!);
    return navigate(tab.id!, a.url, () => retryTabEdit(() => chrome.tabs.update(tab.id!, { url: a.url })));
  },
  "tab.use": async (a) => {
    const tab = await chrome.tabs.get(Number(a.tabId));
    checkBlocked(tab.url);
    await retryTabEdit(() => chrome.tabs.update(tab.id!, { active: true }));
    await setState({ currentTabId: tab.id });
    return tabInfo(tab.id!);
  },
  "tab.close": async (a) => {
    const st = await getState();
    const id = a.tabId ?? st.currentTabId;
    if (id === undefined) throw new Error("no tab to close");
    const dialogs: Dialog[] = [];
    const release = await acceptUnload(Number(id), dialogs); // or a beforeunload prompt keeps the tab open
    try {
      await retryTabEdit(() => chrome.tabs.remove(Number(id)));
    } finally {
      await release();
    }
    await chrome.storage.session.remove(markKey(Number(id)));
    if (Number(id) === st.currentTabId) await chrome.storage.session.remove("currentTabId");
    return { closed: Number(id), ...(dialogs.length ? { dialogs } : {}) };
  },
  "tab.info": async (a) => tabInfo((await resolveTab(a)).id!),

  goto: async (a) => {
    if (!a.url) throw new Error("url is required");
    checkBlocked(a.url);
    const tab = a.newTab ? await newTab() : await resolveTab(a);
    return navigate(tab.id!, a.url, () => retryTabEdit(() => chrome.tabs.update(tab.id!, { url: a.url })));
  },
  back: async (a) => {
    const tab = await resolveTab(a);
    return historyStep(tab.id!, -1);
  },
  forward: async (a) => {
    const tab = await resolveTab(a);
    return historyStep(tab.id!, 1);
  },
  reload: async (a) => {
    const tab = await resolveTab(a);
    return navigate(tab.id!, tab.url, () => retryTabEdit(() => chrome.tabs.reload(tab.id!)));
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
    const out = await act(tab.id!, a, a.target, "clicked", async (loc) => {
      if (a.trusted) await assertVisible(tab.id!, loc.frameId);
      if (await frameCall(tab.id!, loc.frameId, "watchOption", loc.target)) option = loc;
      if (!a.trusted) return frameCall(tab.id!, loc.frameId, "click", loc.target);
      // Counted after the wait, so an overlay going away does not read as the click changing the page.
      const p = await locateUncovered(tab.id!, loc, String(a.target), (a.timeout ?? 5) * 1000);
      const count = await armCount(tab.id!, loc.frameId);
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
    return unchangedHint(out, a.trusted ? "submit (for a form) or another element"
      : "click --trusted, submit (for a form) or another element");
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
    const out = await act(tab.id!, a, a.target ?? null, "submitted",
      (loc) => frameCall(tab.id!, loc.frameId, "submitForm", a.target ? loc.target : null));
    return unchangedHint(out, "click on the form's submit button (snapshot -i shows it)");
  },
  upload: async (a) => {
    const tab = await resolveTab(a);
    const files = Array.isArray(a.files) ? a.files : [];
    if (!files.length) throw new Error("no files to upload");
    const drop = !!a.drop;
    if (a.trusted && drop) throw new Error("upload --trusted cannot drop files: drop them without --trusted");
    if (a.trusted && files.some((f: any) => typeof f?.path !== "string")) throw new Error("upload --trusted needs the files' paths");
    const tabId = tab.id!;
    // Without drop the target may be a hidden file input, or the label or button in front of it.
    return act(tabId, a, a.target, drop ? "dropped" : "uploaded", async (loc) => {
      if (drop) return frameCall(tabId, loc.frameId, "upload", loc.target, files, true);
      if (a.trusted) return uploadTrusted(tabId, loc, a, files);
      if (await frameCall(tabId, loc.frameId, "nearFileInput", loc.target)) {
        return frameCall(tabId, loc.frameId, "upload", loc.target, files, false, false);
      }
      // No file input near the target: it may make one when clicked. Only then the inputs further away.
      return (await uploadOnClick(tabId, loc, files)) ?? frameCall(tabId, loc.frameId, "upload", loc.target, files, false, true);
    }, undefined, drop ? "ready" : "readyUpload");
  },
  fill: async (a) => {
    const tab = await resolveTab(a);
    const fields: { target: string; value: string }[] = Array.isArray(a.fields) ? a.fields : [];
    if (!fields.length) throw new Error("no fields to fill");
    const timeoutMs = (a.timeout ?? 5) * 1000;
    return act(tab.id!, a, null, "filled", async () => {
      const count = await armCount(tab.id!);
      const filled: Record<string, unknown>[] = [];
      let toggled = false;
      let last: Loc | null = null;
      for (const [i, f] of fields.entries()) {
        const target = String(f.target);
        try {
          // Let what the previous field set off render (a field that appears, options that load).
          if (last) await domIdle(tab.id!, 150, 1500, last.frameId);
          const loc = await waitTarget(tab.id!, target, timeoutMs);
          const r = await frameCall(tab.id!, loc.frameId, "fillField", loc.target, String(f.value));
          filled.push({ target, ...r.extra, ...(r.reresolved || loc.reresolved ? { reresolved: true } : {}) });
          toggled ||= !!r.toggled;
          last = loc;
        } catch (e: any) {
          const before = filled.length ? `filled before it: ${filled.map((x) => x.target).join(", ")}` : "nothing filled";
          const msg = `field ${i + 1} (${target}): ${e?.message ?? e}; ${before}`;
          throw e instanceof PageBlocked ? new PageBlocked(msg) : new Error(msg);
        }
      }
      let submitted: string | undefined;
      if (a.submit) {
        const s = await frameCall(tab.id!, last!.frameId, "submitForm", last!.target);
        submitted = s.desc;
      }
      return { count, toggled, extra: { filled, ...(submitted ? { submitted } : {}) } };
    });
  },
  hover: async (a) => {
    const tab = await resolveTab(a);
    const out = await act(tab.id!, a, a.target, "hovered", async (loc) => {
      if (!a.trusted) return frameCall(tab.id!, loc.frameId, "hover", loc.target);
      await assertVisible(tab.id!, loc.frameId);
      const p = await locateUncovered(tab.id!, loc, String(a.target), (a.timeout ?? 5) * 1000, "hover");
      const count = await armCount(tab.id!, loc.frameId);
      await cdp(tab.id!, "Input.dispatchMouseEvent", { type: "mouseMoved", x: p.x, y: p.y });
      return { desc: p.desc, count };
    }, undefined, "shown");
    // A menu opened by CSS :hover changes no DOM, so after --trusted "no change" says nothing: read the page.
    return a.trusted ? out : unchangedHint(out, "hover --trusted (menus opened by CSS :hover need the real pointer)");
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
    checkDialogArg(a);
    const tab = await resolveTab(a);
    const dialogs: Dialog[] = [];
    const value = await answerNatively(tab.id!, a.dialog === "accept", a.promptText ?? null, dialogs,
      () => evaluate(tab.id!, a));
    // The page's value stays apart from WebPilot's fields; the client unwraps it.
    return { value, ...(dialogs.length ? { dialogs } : {}), ...(anyDismissed(dialogs) ? { hint: DISMISSED } : {}) };
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
    let url: URL;
    try { url = new URL(String(a.url), tab.url); } catch { throw new Error(`bad URL for this tab: ${a.url}`); }
    checkBlocked(url.href);
    url.hash = OWN_FETCH; // so `requests` leaves it out; the fragment never reaches the server
    const [res] = await answering(tab.id!, [0], chrome.scripting.executeScript({
      target: { tabId: tab.id! }, func: pageFetch, world: "MAIN", // the isolated world's requests never left the tab
      args: [url.href, method, a.headers ?? {}, a.body ?? null, a.timeoutMs ?? 120000],
    })).catch((e) => { throw explain(e); });
    const r = res?.result as any;
    if (!r) throw new Error(RESTRICTED);
    if (r.error) throw new Error(r.error);
    checkBlocked(r.url); // after redirects
    return r;
  },
  requests: async (a) => {
    const tab = await resolveTab(a);
    const max = a.max ?? 50;
    if (!Number.isInteger(max) || max < 1) throw new Error(`max must be a positive whole number, not ${a.max}`);
    let since: number | null = null;
    if (a.new) since = ((await chrome.storage.session.get(markKey(tab.id!)))[markKey(tab.id!)] as number | undefined) ?? null;
    const found = await allFramesCall(tab.id!, "requests", !!a.all, a.filter ?? null, since);
    if (!found.length) throw new Error(RESTRICTED);
    // The same URL from the same frame (polling, retries) is one entry with its count, at its latest position.
    const byKey = new Map<string, any>();
    for (const f of found) {
      for (const r of f.value ?? []) {
        const key = `${f.frameId} ${r.url}`;
        const prev = byKey.get(key);
        byKey.delete(key);
        byKey.set(key, { ...r, ...(f.frameId ? { frame: `f${f.frameId}` } : {}), n: (prev?.n ?? 0) + 1 });
      }
    }
    const list = [...byKey.values()].sort((x, y) => x.at - y.at).map(({ at, n, type, contentType, ...r }) => ({
      ...r, ...(a.all ? { type } : {}), ...(contentType ? { contentType } : {}), ...(n > 1 ? { n } : {}),
    }));
    const shown = list.slice(-max);
    const out: any = { tabId: tab.id, url: tab.url, requests: shown };
    if (list.length > shown.length) out.omitted = list.length - shown.length;
    if (a.new && since === null) out.hint = "no earlier action in this tab: these are all the page's requests";
    else if (!shown.length) {
      out.hint = (a.new ? "no requests since the last action" : "no requests in this page")
        + (a.filter ? ` whose URL contains ${JSON.stringify(a.filter)}` : "")
        + (a.all ? "" : " (fetch and XHR only; --all adds images, scripts and the rest)")
        + "; requests still waiting for an answer are not listed";
    }
    return out;
  },
  screenshot: async (a) => {
    const tab = await resolveTab(a);
    const params: any = { format: "png" };
    if (a.target) {
      if (a.full) throw new Error("screenshot takes a target or --full, not both");
      const loc = await waitTarget(tab.id!, String(a.target), (a.timeout ?? 5) * 1000, "shown");
      const p = await locateAbs(tab.id!, loc); // scrolls it to the middle of the viewport
      // The clip is in document coordinates: add the page's scroll. A margin around the element, inside the page.
      const m = await cdp(tab.id!, "Page.getLayoutMetrics");
      const vp = m.cssVisualViewport || m.visualViewport;
      const size = m.cssContentSize || m.contentSize;
      const x0 = Math.max(0, vp.pageX + p.x - p.w / 2 - SHOT_MARGIN);
      const y0 = Math.max(0, vp.pageY + p.y - p.h / 2 - SHOT_MARGIN);
      const x1 = Math.min(size.width, vp.pageX + p.x + p.w / 2 + SHOT_MARGIN);
      const y1 = Math.min(size.height, vp.pageY + p.y + p.h / 2 + SHOT_MARGIN, y0 + 16000);
      if (x1 - x0 < 1 || y1 - y0 < 1) throw new Error(`${a.target} (${p.desc}) has no size to capture`);
      params.clip = { x: x0, y: y0, width: x1 - x0, height: y1 - y0, scale: 1 };
      // Only an element larger than the viewport needs the page laid out past it (which resizes it for a moment).
      if (x1 - x0 > vp.clientWidth || y1 - y0 > vp.clientHeight) params.captureBeyondViewport = true;
      const r = await cdp(tab.id!, "Page.captureScreenshot", params);
      return { tabId: tab.id, format: "png", target: p.desc, data: r.data };
    }
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
