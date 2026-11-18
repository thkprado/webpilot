// Service worker: the agents' tabs (each agent's current tab, the tab group), page loads, and tab info for results.

import { retryTabEdit } from "../tabedit";
import { Args, config } from "./config";
import { OffLimits, checkBlocked } from "./domains";

type State = { groupId?: number };

export const getState = async () => (await chrome.storage.session.get(["groupId"])) as State;
export const setState = (s: State) => chrome.storage.session.set(s);

/** When the last action or navigation in a tab started (epoch ms), for `requests --new`. */
export const markKey = (tabId: number) => `actionAt${tabId}`;
export const markAction = (tabId: number) => chrome.storage.session.set({ [markKey(tabId)]: Date.now() });

/**
 * Each agent has its own current tab: `cur:<key>` in session storage, the key coming from the client as `a._agent`
 * (see agent.py). A command without a key (an older client, `Browser(agent="")`) uses the shared slot. One storage
 * entry per agent, so two commands at once never overwrite each other's read-modify-write of a shared map.
 */
const SHARED = "currentTabId";
const slot = (agent?: string) => (agent ? `cur:${agent}` : SHARED);
const isSlot = (k: string) => k === SHARED || k.startsWith("cur:");

export async function currentTab(agent?: string): Promise<number | undefined> {
  const k = slot(agent);
  return (await chrome.storage.session.get(k))[k] as number | undefined;
}
export const setCurrentTab = (agent: string | undefined, tabId: number) =>
  chrome.storage.session.set({ [slot(agent)]: tabId });
export const clearCurrentTab = (agent?: string) => chrome.storage.session.remove(slot(agent));

/** The tabs that are the current tab of another agent (or of the shared slot, for a caller with a key). */
export async function othersTabs(agent?: string): Promise<Set<number>> {
  const all = await chrome.storage.session.get(null);
  const mine = slot(agent);
  return new Set(Object.entries(all).filter(([k]) => isSlot(k) && k !== mine).map(([, v]) => v as number));
}

// A closed tab is no one's current tab any more (whoever closed it).
chrome.tabs.onRemoved.addListener(async (tabId) => {
  const all = await chrome.storage.session.get(null);
  const stale = Object.keys(all).filter((k) => (isSlot(k) && all[k] === tabId) || k === markKey(tabId));
  if (stale.length) await chrome.storage.session.remove(stale);
});

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

/** Opens a tab and makes it the current tab of the agent that sent args (`args._agent`). */
export async function newTab(args: Args): Promise<chrome.tabs.Tab> {
  const tab = await retryTabEdit(() => chrome.tabs.create({ url: "about:blank", active: true }));
  if (config?.mode === "real") await addToGroup(tab.id!);
  await setCurrentTab(args._agent, tab.id!);
  return tab;
}

/** The tab a command acts on: args.tabId, else the calling agent's current tab, else a fresh one. */
export async function resolveTab(args: Args): Promise<chrome.tabs.Tab> {
  const explicit = args.tabId !== undefined && args.tabId !== null;
  const id = explicit ? Number(args.tabId) : await currentTab(args._agent);
  if (id !== undefined) {
    try {
      const tab = await chrome.tabs.get(id);
      checkBlocked(tab.url);
      return tab;
    } catch (e: any) {
      if (explicit || e instanceof OffLimits) throw new Error(String(e?.message ?? e));
    }
  }
  return newTab(args);
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
