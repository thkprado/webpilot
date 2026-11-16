// Page script: html, text and captcha widgets of the page.

export function html(selector: string | null) {
  const el = selector ? document.querySelector(selector) : document.documentElement;
  if (!el) return { error: `selector not found: ${selector}` };
  return { url: location.href, title: document.title, html: el.outerHTML };
}

export function text(selector: string | null, maxChars: number) {
  const el = (selector ? document.querySelector(selector) : document.body) as HTMLElement | null;
  if (!el) return { error: `selector not found: ${selector}` };
  const t = el.innerText || "";
  return { url: location.href, title: document.title, text: t.slice(0, maxChars), truncated: t.length > maxChars };
}

/** Finds captcha checkbox widgets (reCAPTCHA, hCaptcha, Turnstile) and whether an image challenge is showing. */
export function findCaptcha() {
  const widgets: { kind: string; x: number; y: number; w: number; h: number }[] = [];
  let challenge = false;
  for (const f of Array.from(document.querySelectorAll("iframe"))) {
    const src = f.getAttribute("src") || "";
    const r = f.getBoundingClientRect();
    const shown = r.width > 20 && r.height > 20 && r.top > -1000 && getComputedStyle(f).visibility !== "hidden";
    if (/\/recaptcha\/(api2|enterprise)\/bframe/.test(src) || (/hcaptcha\.com/.test(src) && /frame=challenge/.test(src))) {
      if (shown && r.height > 150) challenge = true;
      continue;
    }
    let kind = "";
    if (/\/recaptcha\/(api2|enterprise)\/anchor/.test(src)) kind = "recaptcha";
    else if (/hcaptcha\.com/.test(src) && /frame=checkbox/.test(src)) kind = "hcaptcha";
    else if (/challenges\.cloudflare\.com/.test(src)) kind = "turnstile";
    if (!kind || !shown || widgets.length) continue;
    f.scrollIntoView({ block: "center", inline: "center", behavior: "instant" });
    const rr = f.getBoundingClientRect();
    widgets.push({ kind, x: rr.left, y: rr.top, w: rr.width, h: rr.height });
  }
  const val = (sel: string) => (document.querySelector(sel) as HTMLInputElement | null)?.value || "";
  const solved = !!(
    val('textarea[name="g-recaptcha-response"]') ||
    val('[name="cf-turnstile-response"]') ||
    val('textarea[name="h-captcha-response"]')
  );
  return { widgets: solved ? [] : widgets, challenge, solved };
}
