// Service worker: `fetch` from the page's context (runs in the page through executeScript).

/** Marks WebPilot's own fetch in the page's Resource Timing (see page/requests.ts). */
export const OWN_FETCH = "#webpilot-fetch";

/** HTTP request from the page's context (its cookies and session); runs via executeScript, so self-contained. */
export const pageFetch = async (url: string, method: string, headers: Record<string, string>, body: string | null,
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
