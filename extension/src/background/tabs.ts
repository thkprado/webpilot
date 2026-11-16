// Service worker: the agent's tabs (current tab, tab group), page loads, and tab info for results.

import { retryTabEdit } from "../tabedit";
import { Args, config } from "./config";
import { OffLimits, checkBlocked } from "./domains";

type State = { currentTabId?: number; groupId?: number };

export const getState = async () => (await chrome.storage.session.get(["currentTabId", "groupId"])) as State;
export const setState = (s: State) => chrome.storage.session.set(s);

/** When the last action or navigation in a tab started (epoch ms), for `requests --new`. */
export const markKey = (tabId: number) => `actionAt${tabId}`;
export const markAction = (tabId: number) => chrome.storage.session.set({ [markKey(tabId)]: Date.now() });

async function addToGroup(tabId: number) {
  const st = await getState();
  if (st.groupId !== undefined) {
    try {
      await retryTabEdit(() => chrome.tabs.group({ tabIds: [tabId], groupId: st.groupId }));
      return;
    } catch { /* group was closed */ }
  }
  try {
    const groupId = await retryTabEdit(() => chrome.tabs.group({ tabIds: [tabId] }));
    await retryTabEdit(() => chrome.tabGroups.update(groupId, { title: "WebPilot", color: "purple" }));
    await setState({ groupId });
  } catch { /* tab groups unavailable */ }
}

export async function newTab(): Promise<chrome.tabs.Tab> {
  const tab = await retryTabEdit(() => chrome.tabs.create({ url: "about:blank", active: true }));
  if (config?.mode === "real") await addToGroup(tab.id!);
  await setState({ currentTabId: tab.id });
  return tab;
}

/** The tab a command acts on: args.tabId, else the agent's current tab, else a fresh one. */
export async function resolveTab(args: Args): Promise<chrome.tabs.Tab> {
  const explicit = args.tabId !== undefined && args.tabId !== null;
  const id = explicit ? Number(args.tabId) : (await getState()).currentTabId;
  if (id !== undefined) {
    try {
      const tab = await chrome.tabs.get(id);
      checkBlocked(tab.url);
      return tab;
    } catch (e: any) {
      if (explicit || e instanceof OffLimits) throw new Error(String(e?.message ?? e));
    }
  }
  return newTab();
}

export function waitForLoad(tabId: number, timeoutMs = 30000): Promise<boolean> {
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

export async function tabInfo(tabId: number) {
  const t = await chrome.tabs.get(tabId);
  return { tabId, url: t.url, title: t.title, status: t.status };
}
