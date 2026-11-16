// Page script: the document's finished requests (Resource Timing), for `requests`.

import { w } from "./dom";

/** background/fetch.ts adds this fragment to the URLs of WebPilot's own `fetch` (a fragment never reaches the server). */
const OWN_FETCH = "#webpilot-fetch";
const KEEP_REQUESTS = 1000;
type Req = { url: string; type: string; status: number; ms: number; bytes: number; contentType: string; start: number };

const addRequests = (list: PerformanceEntryList) => {
  const kept: Req[] = w.__wpRequests;
  for (const e of list as PerformanceResourceTiming[]) {
    if (e.name.endsWith(OWN_FETCH)) continue;
    kept.push({
      url: e.name, type: e.initiatorType === "xmlhttprequest" ? "xhr" : e.initiatorType, status: e.responseStatus ?? 0,
      ms: Math.round(e.duration), bytes: e.decodedBodySize, contentType: (e as any).contentType ?? "", start: e.startTime,
    });
  }
  if (kept.length > KEEP_REQUESTS) kept.splice(0, kept.length - KEEP_REQUESTS);
};

/**
 * Keeps this document's finished requests in a list of its own, from those the browser buffered before page.js
 * arrived on: the browser's buffer stops at 250 entries, and the page may clear it.
 */
function watchRequests() {
  if (w.__wpRequests) return;
  w.__wpRequests = [];
  try {
    w.__wpRequestObserver = new PerformanceObserver((l) => addRequests(l.getEntries()));
    w.__wpRequestObserver.observe({ type: "resource", buffered: true });
  } catch { /* no Resource Timing here */ }
}
watchRequests();

/**
 * This document's finished requests, oldest first: only fetch and XHR unless `all`; only those whose URL contains
 * `filter` (any case); only those started after `since` (epoch ms), if given. `at` is when each started (epoch ms).
 */
export function requests(all: boolean, filter: string | null, since: number | null) {
  addRequests(w.__wpRequestObserver?.takeRecords() ?? []);
  const now = performance.now(), epoch = Date.now();
  const from = since === null ? -Infinity : now - (epoch - since);
  const want = filter?.toLowerCase();
  return (w.__wpRequests as Req[])
    .filter((r) => (all || r.type === "fetch" || r.type === "xhr") && r.start >= from
      && (!want || r.url.toLowerCase().includes(want)))
    .map(({ start, ...r }) => ({ ...r, at: Math.round(epoch - (now - start)) }));
}
