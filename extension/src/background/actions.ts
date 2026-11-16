// Service worker: how an action or a navigation runs: wait for the target, act, settle, report what changed.

import { Args } from "./config";
import { checkBlocked, checkLanded } from "./domains";
import { markAction, waitForLoad, tabInfo } from "./tabs";
import { PageBlocked, rethrowBlocked, answering, frameCall } from "./scripts";
import { cdp } from "./cdp";
import { Loc } from "./frames";
import { domIdle, watchNetwork, settle, waitTarget, waitFor, waitNotBusy } from "./wait";
import { Dialog, armDialogs, takeDialogs, withLoadShim, acceptUnload, checkDialogArg, anyDismissed, DISMISSED } from "./dialogs";
import { autoCaptcha } from "./captcha";

export type ActResult = { desc?: string; count: number; reresolved?: boolean; toggled?: boolean; extra?: Record<string, unknown> };

/**
 * Runs click/type/press/submit: waits for the target, performs the action, settles, reports whether
 * the page changed, and optionally waits for something (args.waitText / args.waitSelector) that
 * marks the next state. With such a marker the settle gives up on DOM churn sooner, since the
 * marker is what tells that the next state arrived (pages with a running clock never go quiet).
 * `after` adds fields read once the page settled; `check` is the page function that tells the target is ready.
 */
export async function act(
  tabId: number, a: Args, target: string | null, key: string, run: (loc: Loc) => Promise<ActResult>,
  after?: () => Promise<Record<string, unknown>>, check = "ready",
) {
  checkDialogArg(a);
  const found = target ? await waitTarget(tabId, target, (a.timeout ?? 5) * 1000, check) : { frameId: 0, target: "", reresolved: false };
  const url = (await chrome.tabs.get(tabId)).url;
  await armDialogs(tabId, a.dialog === "accept", a.promptText ?? null);
  let armed = true;
  const net = watchNetwork(tabId);
  await markAction(tabId);
  try {
    // A page of the same site that the action opens (a link, a form) gets the shim before its inline scripts.
    return await withLoadShim(url, async () => {
      const r = await answering(tabId, [found.frameId], run(found));
      const marker = !!(a.waitText || a.waitSelector);
      const { navigated, busy } = await settle(tabId, net, found.frameId, marker ? 1500 : 5000);
      await checkLanded(tabId);
      const late = after ? await after() : {};
      const info = await tabInfo(tabId);
      let count = r.count;
      let frameUrl: string | undefined;
      try {
        const s = await frameCall(tabId, found.frameId, "idle");
        count = s.count;
        if (found.frameId !== 0) frameUrl = s.url;
      } catch (e) { rethrowBlocked(e); /* restricted page */ }
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
      armed = false;
      const dialogs = await takeDialogs(tabId);
      if (dialogs.length) {
        out.dialogs = dialogs;
        if (anyDismissed(dialogs)) out.hint = DISMISSED;
      }
      return out;
    });
  } catch (e) {
    if (e instanceof PageBlocked) armed = false; // nothing more runs in that page
    throw e;
  } finally {
    net.stop();
    if (armed) void takeDialogs(tabId).catch(() => {});
  }
}

/** Adds a `hint` to an action's result when the page showed no change (and no awaited marker appeared). */
export function unchangedHint(out: any, alternatives: string) {
  if (out.changed || out.hint || out.waited?.found || out.dialogs) return out;
  return { ...out, hint: `the page showed no change; if it should have reacted, try ${alternatives}` };
}

/** DOM mutation count before an action that does not go through a page function. */
export async function armCount(tabId: number, frameId = 0): Promise<number> {
  try { return (await frameCall(tabId, frameId, "arm")).count; } catch (e) { rethrowBlocked(e); return 0; }
}

/**
 * Runs a navigation of the tab to url and waits for the new page. Dialogs it opens while loading are dismissed
 * (see withLoadShim) and a beforeunload prompt of the page being left is accepted (see acceptUnload); both
 * are reported in `dialogs`.
 */
export async function navigate(tabId: number, url: string | undefined, action: () => Promise<unknown>) {
  const dialogs: Dialog[] = [];
  const release = await acceptUnload(tabId, dialogs);
  try {
    return await withLoadShim(url, async () => {
      const loaded = waitForLoad(tabId);
      await markAction(tabId);
      await action();
      const ok = await answering(tabId, [0], loaded);
      await checkLanded(tabId); // before anything runs in a page off limits
      if (ok) await domIdle(tabId, 300, 3000); // let client-side rendering finish before a snapshot
      dialogs.push(...(await takeDialogs(tabId)));
      const captcha = await autoCaptcha(tabId);
      return { ...(await tabInfo(tabId)), loaded: ok, ...(dialogs.length ? { dialogs } : {}), ...(captcha ? { captcha } : {}) };
    });
  } finally {
    await release();
  }
}

/**
 * Moves one entry back (-1) or forward (1) in the tab's history. chrome.tabs.goBack skips the entries of
 * pages that never had a user gesture (Chromium's history intervention against back-button hijacking),
 * which is every page an agent only opened or clicked without --trusted, and then fails with "Cannot find
 * a next page in history". DevTools goes to the adjacent entry, like history.back() from the page.
 */
export async function historyStep(tabId: number, step: -1 | 1) {
  const h = await cdp(tabId, "Page.getNavigationHistory");
  const entry = h.entries[h.currentIndex + step];
  if (!entry) throw new Error(`no ${step < 0 ? "previous" : "next"} page in this tab's history`);
  checkBlocked(entry.url);
  return navigate(tabId, entry.url, () => cdp(tabId, "Page.navigateToHistoryEntry", { entryId: entry.id }));
}
