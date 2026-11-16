// Page script: DOM helpers shared by the other page modules (visibility, names, shadow roots, events).

export type Err = { error: string; fatal?: boolean };

const ROLES = new Set([
  "button", "link", "checkbox", "radio", "tab", "menuitem", "menuitemcheckbox", "menuitemradio",
  "option", "combobox", "textbox", "searchbox", "switch", "slider", "spinbutton", "treeitem",
]);

export const w = globalThis as any;
w.__wpRefCount = w.__wpRefCount || 0;
// ref -> what it pointed to, so a ref can be found again after the page re-renders that element.
w.__wpRefInfo = w.__wpRefInfo || {};

/** Elements matching the selector in the document and in the open shadow roots inside it (snapshots walk them too). */
export function deepAll(selector: string, root: Document | ShadowRoot = document): Element[] {
  const out = Array.from(root.querySelectorAll(selector));
  for (const el of Array.from(root.querySelectorAll("*"))) {
    if (el.shadowRoot) out.push(...deepAll(selector, el.shadowRoot));
  }
  return out;
}

/** The first match in the document, else in an open shadow root. */
export function deepFirst(selector: string): Element | null {
  return document.querySelector(selector) || deepAll(selector)[0] || null;
}

/** The document or shadow root an element lives in, for lookups by id that must stay inside it. */
export const rootOf = (el: Element) => el.getRootNode() as Document | ShadowRoot;

export const clean = (s: string | null | undefined, max = 80) => {
  const t = (s || "").replace(/\s+/g, " ").trim();
  return t.length > max ? t.slice(0, max - 3) + "..." : t;
};

export function isVisible(el: Element): boolean {
  const anyEl = el as any;
  if (typeof anyEl.checkVisibility === "function") {
    if (anyEl.checkVisibility({ checkVisibilityCSS: true })) return true;
    // display:contents has no box but its children may be visible.
    return getComputedStyle(el).display === "contents";
  }
  const r = el.getBoundingClientRect();
  return r.width > 0 || r.height > 0;
}

export function isInteractive(el: Element): boolean {
  const tag = el.localName;
  if (tag === "a") return el.hasAttribute("href");
  if (tag === "button" || tag === "select" || tag === "textarea" || tag === "summary") return true;
  if (tag === "input") return (el as HTMLInputElement).type !== "hidden";
  const role = el.getAttribute("role");
  if (role && ROLES.has(role)) return true;
  const h = el as HTMLElement;
  if (h.isContentEditable && !(h.parentElement && h.parentElement.isContentEditable)) return true;
  return el.hasAttribute("onclick");
}

export function accessibleName(el: Element): string {
  const tag = el.localName;
  let n = el.getAttribute("aria-label") || "";
  if (!n) {
    const ids = el.getAttribute("aria-labelledby");
    if (ids) n = ids.split(/\s+/).map((id) => rootOf(el).getElementById(id)?.textContent || "").join(" ");
  }
  const isField = tag === "input" || tag === "textarea" || tag === "select";
  if (!n && isField) {
    if (el.id) n = rootOf(el).querySelector(`label[for="${CSS.escape(el.id)}"]`)?.textContent || "";
    if (!n) n = el.closest("label")?.textContent || "";
    if (!n) n = (el as HTMLInputElement).placeholder || "";
  }
  if (!n && !isField) n = (el as HTMLElement).innerText || "";
  if (!n && tag === "input" && /^(submit|button|reset)$/.test((el as HTMLInputElement).type)) {
    n = (el as HTMLInputElement).value || ((el as HTMLInputElement).type === "submit" ? "Submit" : "");
  }
  if (!n) n = el.querySelector("img[alt]")?.getAttribute("alt") || "";
  if (!n) n = el.getAttribute("title") || el.getAttribute("name") || "";
  return clean(n);
}

export function kindOf(el: Element): string {
  const tag = el.localName;
  if (tag === "input") {
    if (el.getAttribute("role") === "combobox") return "combobox";
    const type = (el as HTMLInputElement).type || "text";
    return type === "submit" || type === "button" || type === "reset" ? "button" : `input:${type}`;
  }
  return el.getAttribute("role") || (tag === "a" ? "link" : tag);
}

/** The item with a label equal to `want` (ignoring case and spacing), else the one with the shortest label containing it. */
export function bestMatch<T>(items: T[], labels: (t: T) => string[], want: string): T | undefined {
  const norm = (s: string) => s.replace(/\s+/g, " ").trim().toLowerCase();
  const w = norm(want);
  let best: T | undefined;
  let bestLen = Infinity;
  for (const it of items) {
    for (const s of labels(it).map(norm).filter(Boolean)) {
      if (s === w) return it;
      if (s.includes(w) && s.length < bestLen) {
        best = it;
        bestLen = s.length;
      }
    }
  }
  return best;
}

export function short(el: Element): string {
  const label = accessibleName(el) || clean((el as HTMLInputElement).value, 60);
  return `${el.localName}${el.id ? "#" + el.id : ""}${label ? ` "${label}"` : ""}`;
}

/** The parent element, or the host of the shadow root the element is in. */
export const parentOf = (el: Element): Element | null =>
  el.parentElement || ((el.parentNode as ShadowRoot | null)?.host ?? null);

/** Whether `el` is `anc` or inside it, across shadow roots. */
export function within(el: Element | null, anc: Element): boolean {
  for (; el; el = parentOf(el)) if (el === anc) return true;
  return false;
}

/** The events of a mouse click. Like a browser, focuses only when the page did not cancel mousedown
 * (dropdown menus cancel it to keep the focus in their input, and close when it leaves). */
export function fireClick(h: HTMLElement) {
  h.scrollIntoView({ block: "center", inline: "center", behavior: "instant" });
  const r = h.getBoundingClientRect();
  const opts = { bubbles: true, cancelable: true, composed: true, clientX: r.left + r.width / 2, clientY: r.top + r.height / 2, button: 0 };
  h.dispatchEvent(new PointerEvent("pointerdown", opts));
  if (h.dispatchEvent(new MouseEvent("mousedown", opts))) h.focus?.();
  h.dispatchEvent(new PointerEvent("pointerup", opts));
  h.dispatchEvent(new MouseEvent("mouseup", opts));
  h.click();
}

/** The element and the elements around it, innermost first, across shadow roots. */
export function chainOf(el: Element): Element[] {
  const out: Element[] = [];
  for (let e: Element | null = el; e; e = parentOf(e)) out.push(e);
  return out;
}

const yieldTask = () => new Promise<void>((r) => {
  const c = new MessageChannel();
  c.port1.onmessage = () => r();
  c.port2.postMessage(null);
});

/** Polls get() until it returns something truthy or ms pass. The first polls only yield to the event
 * loop (a re-render after a key), then every 25 ms (timers run at most once a second in hidden windows). */
export async function until<T>(get: () => T, ms: number): Promise<T> {
  const end = performance.now() + ms;
  let v = get();
  for (let i = 0; !v && performance.now() < end; i++) {
    await (i < 50 ? yieldTask() : new Promise((r) => setTimeout(r, 25)));
    v = get();
  }
  return v;
}
