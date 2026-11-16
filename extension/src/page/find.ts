// Page script: targets (refs, text=, selectors) found again, refs handed out, and where a target is on screen.

import { Err, w, deepAll, deepFirst, clean, isVisible, isInteractive, accessibleName, kindOf, bestMatch, short, parentOf, within } from "./dom";

export let reresolved = false;

/** Refs left in the page by an earlier injection (before the extension was reloaded) are never handed out again. */
export function syncRefCount() {
  for (const el of deepAll("[data-wp-ref]")) {
    w.__wpRefCount = Math.max(w.__wpRefCount, Number(el.getAttribute("data-wp-ref")!.slice(1)) || 0);
  }
}

export function refOf(el: Element): string {
  let ref = el.getAttribute("data-wp-ref");
  if (!ref) {
    ref = "e" + ++w.__wpRefCount;
    el.setAttribute("data-wp-ref", ref);
  }
  return ref;
}

/** A ref whose element was replaced (AJAX re-render): adopt the element with the same kind and name. */
function refind(ref: string): Element | Err {
  const info = w.__wpRefInfo[ref];
  if (!info) {
    return { error: `ref ${ref} not found: refs are reset when the page navigates; run snapshot -i again and use its refs`, fatal: true };
  }
  const matches = deepAll("*").filter(
    (c) => isInteractive(c) && kindOf(c) === info.kind && accessibleName(c) === info.name && isVisible(c),
  );
  const el = matches.length === 1 ? matches[0] : info.nth >= 0 ? matches[info.nth] : undefined;
  const other = el?.getAttribute("data-wp-ref");
  if (!el || (other && other !== ref)) {
    const what = `ref ${ref} (${info.kind}${info.name ? ` "${info.name}"` : ""}) is gone`;
    // Options vanish when their menu closes between commands (it closes when the window loses focus).
    if (info.kind === "option") {
      return { error: `${what}: its menu closed; choose in one command with select <combobox ref> <option text>` };
    }
    return { error: `${what}: the page changed; run snapshot -i again and use its refs` };
  }
  el.setAttribute("data-wp-ref", ref);
  reresolved = true;
  return el;
}

export function find(target: string): Element | Err {
  let el: Element | null = null;
  reresolved = false;
  if (/[\r\n]/.test(target)) {
    // "e9\ne\ne": the shell's quoting broke the command; no element will ever match, so do not wait for one.
    return { error: `the target has a line break: check the quoting (${JSON.stringify(target)})`, fatal: true };
  }
  if (/^e\d+$/.test(target)) {
    return deepFirst(`[data-wp-ref="${target}"]`) || refind(target);
  }
  if (target.startsWith("text=")) {
    // "text=Next|Próximo|›": alternatives tried in order; an exact label beats the shortest containing one.
    const wants = target.slice(5).split("|").map((s) => s.trim().toLowerCase()).filter(Boolean);
    const cands = deepAll(
      "a,button,input[type=submit],input[type=button],[role=button],[role=link],[role=tab],[role=menuitem],[role=option],[role=checkbox],label,summary,[onclick]",
    ).filter(isVisible);
    // Visible text and aria-label both count ("1" in a pager may be labelled "Go to page 1").
    const labels = (c: Element) => [(c as HTMLElement).innerText || (c as HTMLInputElement).value || "", c.getAttribute("aria-label") || ""];
    for (const want of wants) {
      el = bestMatch(cands, labels, want) || null;
      if (el) break;
    }
  } else {
    try {
      el = deepFirst(target);
    } catch {
      return { error: `invalid selector: ${target}`, fatal: true };
    }
  }
  return el || { error: `element not found: ${target}` };
}

/** Whether the target exists, is visible and enabled; `fatal` means waiting will not help. */
export function ready(target: string) {
  const el = find(target);
  if ("error" in el) return { ok: false, reason: el.error, fatal: !!el.fatal };
  if (!isVisible(el)) return { ok: false, reason: `element is not visible: ${short(el)}` };
  if ((el as any).disabled) return { ok: false, reason: `element is disabled: ${short(el)}` };
  return { ok: true, reresolved };
}

/** Whether the target exists and is visible, enabled or not (hover a disabled button for its tooltip, picture it). */
export function shown(target: string) {
  const el = find(target);
  if ("error" in el) return { ok: false, reason: el.error, fatal: !!el.fatal };
  if (!isVisible(el)) return { ok: false, reason: `element is not visible: ${short(el)}` };
  return { ok: true, reresolved };
}

export function locate(target: string) {
  const el = find(target);
  if ("error" in el) return el;
  el.scrollIntoView({ block: "center", inline: "center", behavior: "instant" });
  const r = el.getBoundingClientRect();
  const x = r.left + r.width / 2, y = r.top + r.height / 2;
  return { x, y, w: r.width, h: r.height, desc: short(el), covered: coverAt(el, x, y) };
}

/** The element a real click at this viewport point lands on, descending into open shadow roots. */
function hitAt(x: number, y: number): Element | null {
  let hit = document.elementFromPoint(x, y);
  while (hit?.shadowRoot) {
    const inner = hit.shadowRoot.elementFromPoint(x, y);
    if (!inner || inner === hit) break;
    hit = inner;
  }
  return hit;
}

/**
 * What a real click at (x, y) lands on instead of `el` (a banner, a modal), described, or null when it reaches
 * `el`: the hit is `el`, inside it, around it, or in one of its labels (custom checkboxes draw a span over a
 * transparent input). The description is of the outermost element around the hit that does not contain `el`,
 * so the banner rather than the paragraph in it.
 */
export function coverAt(el: Element, x: number, y: number): string | null {
  const hit = hitAt(x, y);
  if (!hit || within(hit, el) || within(el, hit)) return null;
  if (Array.from((el as HTMLInputElement).labels || []).some((l) => within(hit, l))) return null;
  let top = hit;
  for (let p = parentOf(top); p && p !== document.body && p !== document.documentElement && !within(el, p); p = parentOf(p)) {
    top = p;
  }
  const cls = typeof top.className === "string" ? top.className.trim().split(/\s+/)[0] : "";
  const name = clean(top.getAttribute("aria-label") || (top as HTMLElement).innerText, 60);
  return `${top.localName}${top.id ? "#" + top.id : cls ? "." + cls : ""}${name ? ` "${name}"` : ""}`;
}
