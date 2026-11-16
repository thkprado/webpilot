// Service worker: blocked_domains and allowed_domains, checked before and after a command reaches a page.

import { config } from "./config";

/** Without the trailing dot: "bank.com." is the same site as "bank.com". URL() already lowercases. */
const bareHost = (h: string) => h.replace(/\.+$/, "");

/** A blocked_domains or allowed_domains entry as a hostname: "*.Bank.com", " bank.com. " and "https://bank.com/x" give "bank.com". */
function listHost(entry: unknown): string {
  const s = String(entry).trim().replace(/^[a-z][a-z\d+.-]*:\/\//i, "").replace(/^(\*?\.)+/, "");
  try { return bareHost(new URL(`http://${s}`).hostname); } catch { return ""; }
}

/** Whether host is an entry of the list or a subdomain of one. */
const inList = (host: string, list: unknown[]) =>
  list.map(listHost).some((d) => d && (host === d || host.endsWith("." + d)));

/** A URL the config puts off limits: thrown by checkBlocked; resolveTab passes it on instead of opening a tab. */
export class OffLimits extends Error {}

/**
 * Throws OffLimits when the config keeps the agent away from url: its domain is in blocked_domains, or
 * allowed_domains is not empty and the domain is not in it (blocked wins over allowed). An empty URL and
 * about: pages (blank, srcdoc) pass. With an allow list, URLs with no host (file:, data:) fail like any other
 * domain not listed. blob: and view-source: are judged by the URL they wrap.
 */
export function checkBlocked(url?: string) {
  const blocked = config?.blockedDomains ?? [], allowed = config?.allowedDomains ?? [];
  if (!url || /^about:/i.test(url) || (!blocked.length && !allowed.length)) return;
  let u: URL;
  try { u = new URL(url.replace(/^(view-source:|blob:)+/i, "")); } catch {
    if (allowed.length) throw new OffLimits(`URL not in allowed_domains of the WebPilot config: ${url.slice(0, 80)}; ask the user`);
    return;
  }
  const host = bareHost(u.hostname);
  if (host && inList(host, blocked)) throw new OffLimits(`domain blocked by WebPilot config: ${host}`);
  if (allowed.length && !(host && inList(host, allowed))) {
    throw new OffLimits(`domain not in allowed_domains of the WebPilot config: ${host || u.protocol + " URL"}; ask the user`);
  }
}

/**
 * After a command that may have moved the tab (a navigation, a click, a redirect): fails when the tab ended on
 * a page the config puts off limits, so nothing of that page is reported, and tells that the tab is now locked.
 */
export async function checkLanded(tabId: number) {
  try {
    checkBlocked((await chrome.tabs.get(tabId)).url);
  } catch (e) {
    if (!(e instanceof OffLimits)) throw e;
    throw new OffLimits(`the tab went to a page off limits (${e.message}); commands on this tab will fail, continue in another one (tab new URL)`);
  }
}

/** Match patterns for the site of a URL (the host and its subdomains), for the load-time shim. */
export function siteMatches(url?: string): string[] {
  let u: URL;
  try { u = new URL(url ?? ""); } catch { return []; }
  if (!/^https?:$/.test(u.protocol) || u.hostname.startsWith("[")) return [];
  const host = bareHost(u.hostname);
  const base = host.replace(/^www\./, "");
  if (/^[\d.]+$/.test(host) || !base.includes(".")) return [`*://${host}/*`];
  return [`*://${base}/*`, `*://*.${base}/*`];
}
