// Runs inside web pages (extension isolated world). Injected on demand by background.ts,
// which then calls globalThis.__wp[name](...args). Every function returns JSON-serialisable data;
// failures are returned as {error} so they survive executeScript.

type Err = { error: string; fatal?: boolean };

const ROLES = new Set([
  "button", "link", "checkbox", "radio", "tab", "menuitem", "menuitemcheckbox", "menuitemradio",
  "option", "combobox", "textbox", "searchbox", "switch", "slider", "spinbutton", "treeitem",
]);
const SKIP = new Set(["script", "style", "noscript", "template", "svg", "canvas", "meta", "link", "head", "object"]);
const BLOCK = new Set([
  "address", "article", "aside", "blockquote", "details", "dialog", "dd", "div", "dl", "dt", "fieldset",
  "figcaption", "figure", "footer", "form", "h1", "h2", "h3", "h4", "h5", "h6", "header", "hr", "li", "main",
  "nav", "ol", "p", "pre", "section", "table", "tr", "ul", "br", "summary", "caption", "thead", "tbody", "tfoot",
]);

const w = globalThis as any;
w.__wpRefCount = w.__wpRefCount || 0;
// ref -> what it pointed to, so a ref can be found again after the page re-renders that element.
w.__wpRefInfo = w.__wpRefInfo || {};
let snapSeen: Record<string, number> = {};
let snapScoped = false;
let reresolved = false;

// A parent frame tells each child iframe its token (see frameToken), so background.ts can match
// frame ids to <iframe> elements and inline child snapshots in the right place.
if (!w.__wpFrameListener) {
  w.__wpFrameListener = true;
  addEventListener("message", (e) => {
    if (e.source === parent && parent !== window && typeof e.data?.__wpFrame === "string") w.__wpFrameToken = e.data.__wpFrame;
  });
}

function frameToken(f: HTMLIFrameElement): string {
  let t = f.getAttribute("data-wp-frame");
  if (!t) {
    t = "w" + Math.random().toString(36).slice(2, 10);
    f.setAttribute("data-wp-frame", t);
  }
  f.contentWindow?.postMessage({ __wpFrame: t }, "*");
  return t;
}

const clean = (s: string | null | undefined, max = 80) => {
  const t = (s || "").replace(/\s+/g, " ").trim();
  return t.length > max ? t.slice(0, max - 3) + "..." : t;
};

function isVisible(el: Element): boolean {
  const anyEl = el as any;
  if (typeof anyEl.checkVisibility === "function") {
    if (anyEl.checkVisibility({ checkVisibilityCSS: true })) return true;
    // display:contents has no box but its children may be visible.
    return getComputedStyle(el).display === "contents";
  }
  const r = el.getBoundingClientRect();
  return r.width > 0 || r.height > 0;
}

function isInteractive(el: Element): boolean {
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

function accessibleName(el: Element): string {
  const tag = el.localName;
  let n = el.getAttribute("aria-label") || "";
  if (!n) {
    const ids = el.getAttribute("aria-labelledby");
    if (ids) n = ids.split(/\s+/).map((id) => document.getElementById(id)?.textContent || "").join(" ");
  }
  const isField = tag === "input" || tag === "textarea" || tag === "select";
  if (!n && isField) {
    if (el.id) n = document.querySelector(`label[for="${CSS.escape(el.id)}"]`)?.textContent || "";
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

/** Refs left in the page by an earlier injection (before the extension was reloaded) are never handed out again. */
function syncRefCount() {
  for (const el of Array.from(document.querySelectorAll("[data-wp-ref]"))) {
    w.__wpRefCount = Math.max(w.__wpRefCount, Number(el.getAttribute("data-wp-ref")!.slice(1)) || 0);
  }
}

function refOf(el: Element): string {
  let ref = el.getAttribute("data-wp-ref");
  if (!ref) {
    ref = "e" + ++w.__wpRefCount;
    el.setAttribute("data-wp-ref", ref);
  }
  return ref;
}

function kindOf(el: Element): string {
  const tag = el.localName;
  if (tag === "input") {
    if (el.getAttribute("role") === "combobox") return "combobox";
    const type = (el as HTMLInputElement).type || "text";
    return type === "submit" || type === "button" || type === "reset" ? "button" : `input:${type}`;
  }
  return el.getAttribute("role") || (tag === "a" ? "link" : tag);
}

function describe(el: Element): string {
  const tag = el.localName;
  const kind = kindOf(el);
  let extra = "";
  if (kind === "combobox") {
    // react-select keeps its input for the search text and shows the value next to it.
    const v = comboValue(el as HTMLElement);
    if (v) extra += ` value="${clean(v, 60)}"`;
  } else if (kind === "option") {
    if (el.getAttribute("aria-selected") === "true") extra += " selected";
    if (el.id && document.querySelector(`[aria-activedescendant="${CSS.escape(el.id)}"]`)) extra += " active";
  } else if (tag === "input") {
    const i = el as HTMLInputElement;
    const type = i.type || "text";
    if (type === "checkbox" || type === "radio") extra += i.checked ? " checked" : " unchecked";
    else if (i.value && type !== "password" && kind !== "button") extra += ` value="${clean(i.value, 60)}"`;
  } else if (tag === "textarea") {
    const v = (el as HTMLTextAreaElement).value;
    if (v) extra += ` value="${clean(v, 60)}"`;
  } else if (tag === "select") {
    const s = el as HTMLSelectElement;
    const opts = Array.from(s.options).slice(0, 15).map((o) => clean(o.text, 30)).join("|");
    extra += ` value="${clean(s.options[s.selectedIndex]?.text)}" options=[${opts}${s.options.length > 15 ? "|..." : ""}]`;
  } else if (tag === "a") {
    const href = el.getAttribute("href") || "";
    let u = href;
    try {
      const url = new URL(href, location.href);
      u = url.origin === location.origin ? url.pathname + url.search + url.hash : url.href;
    } catch { /* keep raw */ }
    if (u && !u.startsWith("javascript:")) extra += ` -> ${clean(u, 100)}`;
  }
  if ((el as any).disabled) extra += " disabled";
  const exp = el.getAttribute("aria-expanded");
  if (exp) extra += ` expanded=${exp}`;
  const name = accessibleName(el);
  const ref = refOf(el);
  const key = kind + "|" + name;
  snapSeen[key] = (snapSeen[key] ?? -1) + 1;
  // nth counts within a -S subtree only, so it says nothing about position in the whole page.
  w.__wpRefInfo[ref] = { kind, name, nth: snapScoped ? -1 : snapSeen[key] };
  return `[${ref} ${kind}${name ? ` "${name}"` : ""}${extra}]`;
}

function snapshot(selector: string | null, maxChars: number, interactiveOnly: boolean) {
  const root = selector ? document.querySelector(selector) : document.body;
  if (!root) return { error: `selector not found: ${selector}` };
  syncRefCount();
  snapSeen = {};
  snapScoped = !!selector;
  const lines: string[] = [];
  let cur = "";
  let total = 0;
  let truncated = false;

  const push = (line: string) => {
    if (!line || lines[lines.length - 1] === line) return;
    lines.push(line);
    total += line.length + 1;
    if (total > maxChars) truncated = true;
  };
  const flush = () => {
    const t = cur.replace(/\s+/g, " ").trim();
    cur = "";
    push(t);
  };

  const walk = (node: Node) => {
    if (truncated) return;
    if (node.nodeType === Node.TEXT_NODE) {
      if (!interactiveOnly) cur += node.textContent;
      return;
    }
    if (node.nodeType !== Node.ELEMENT_NODE) return;
    const el = node as Element;
    const tag = el.localName;
    if (SKIP.has(tag) || !isVisible(el)) return;
    if (tag === "iframe") {
      const r = el.getBoundingClientRect();
      if (r.width > 100 && r.height > 50) {
        flush();
        push(`[iframe ${clean(el.getAttribute("title") || el.getAttribute("src"), 80)}]`);
        push(`\u0001${frameToken(el as HTMLIFrameElement)}`); // replaced by the frame's snapshot in background.ts
      }
      return;
    }
    if (tag === "img") {
      const alt = el.getAttribute("alt");
      if (alt && !interactiveOnly) cur += ` [img "${clean(alt, 60)}"] `;
      return;
    }
    if (tag === "label") {
      // A label holding only its own control: print the control once (its name already is the label text).
      const ctl = (el as HTMLLabelElement).control;
      const inner = Array.from(el.querySelectorAll("*")).filter(isInteractive);
      if (ctl && inner.length === 1 && inner[0] === ctl && isVisible(ctl)) {
        const d = describe(ctl);
        if (interactiveOnly) push(d);
        else cur += ` ${d} `;
        return;
      }
    }
    if (isInteractive(el)) {
      const d = describe(el);
      if (interactiveOnly) push(d);
      else cur += ` ${d} `;
      // Large clickable containers (cards, wrappers) still get their content walked.
      if (tag === "select" || ((el as HTMLElement).innerText || "").length <= 300) return;
    }
    const block = BLOCK.has(tag);
    if (block) flush();
    if (/^h[1-6]$/.test(tag) && !interactiveOnly) cur += "#".repeat(Number(tag[1])) + " ";
    if ((tag === "td" || tag === "th") && !interactiveOnly) cur += " | ";
    let kids: ArrayLike<Node> = el.childNodes;
    if ((el as HTMLElement).shadowRoot) kids = (el as HTMLElement).shadowRoot!.childNodes;
    else if (tag === "slot") {
      const assigned = (el as HTMLSlotElement).assignedNodes();
      if (assigned.length) kids = assigned;
    }
    for (const k of Array.from(kids)) walk(k);
    if (block) flush();
  };

  walk(root);
  flush();
  let text = lines.join("\n");
  if (text.length > maxChars) {
    text = text.slice(0, maxChars);
    truncated = true;
  }
  return {
    url: location.href,
    title: document.title,
    text,
    truncated,
    scroll: { y: Math.round(scrollY), height: document.documentElement.scrollHeight, viewport: innerHeight },
  };
}

/** A ref whose element was replaced (AJAX re-render): adopt the element with the same kind and name. */
function refind(ref: string): Element | Err {
  const info = w.__wpRefInfo[ref];
  if (!info) return { error: `ref ${ref} not found (refs are reset on navigation; take a new snapshot)`, fatal: true };
  const matches = Array.from(document.querySelectorAll("*")).filter(
    (c) => isInteractive(c) && kindOf(c) === info.kind && accessibleName(c) === info.name && isVisible(c),
  );
  const el = matches.length === 1 ? matches[0] : info.nth >= 0 ? matches[info.nth] : undefined;
  const other = el?.getAttribute("data-wp-ref");
  if (!el || (other && other !== ref)) {
    return { error: `ref ${ref} (${info.kind}${info.name ? ` "${info.name}"` : ""}) is gone; take a new snapshot` };
  }
  el.setAttribute("data-wp-ref", ref);
  reresolved = true;
  return el;
}

/** The item with a label equal to `want` (ignoring case and spacing), else the one with the shortest label containing it. */
function bestMatch<T>(items: T[], labels: (t: T) => string[], want: string): T | undefined {
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

function find(target: string): Element | Err {
  let el: Element | null = null;
  reresolved = false;
  if (/^e\d+$/.test(target)) {
    return document.querySelector(`[data-wp-ref="${target}"]`) || refind(target);
  }
  if (target.startsWith("text=")) {
    // "text=Next|Próximo|›": alternatives tried in order; an exact label beats the shortest containing one.
    const wants = target.slice(5).split("|").map((s) => s.trim().toLowerCase()).filter(Boolean);
    const cands = Array.from(document.querySelectorAll(
      "a,button,input[type=submit],input[type=button],[role=button],[role=link],[role=tab],[role=menuitem],[role=option],[role=checkbox],label,summary,[onclick]",
    )).filter(isVisible);
    // Visible text and aria-label both count ("1" in a pager may be labelled "Go to page 1").
    const labels = (c: Element) => [(c as HTMLElement).innerText || (c as HTMLInputElement).value || "", c.getAttribute("aria-label") || ""];
    for (const want of wants) {
      el = bestMatch(cands, labels, want) || null;
      if (el) break;
    }
  } else {
    try {
      el = document.querySelector(target);
    } catch {
      return { error: `invalid selector: ${target}`, fatal: true };
    }
  }
  return el || { error: `element not found: ${target}` };
}

function short(el: Element): string {
  const label = accessibleName(el) || clean((el as HTMLInputElement).value, 60);
  return `${el.localName}${el.id ? "#" + el.id : ""}${label ? ` "${label}"` : ""}`;
}

/** Starts counting DOM mutations (once per document) and restarts the quiet timer. Returns the count so far. */
function arm() {
  if (!w.__wpObserver) {
    w.__wpMutCount = 0;
    w.__wpObserver = new MutationObserver((records) => {
      const real = records.filter((r) => r.attributeName !== "data-wp-ref" && r.attributeName !== "data-wp-frame").length;
      if (!real) return;
      w.__wpMutCount += real;
      w.__wpLastMut = performance.now();
    });
    w.__wpObserver.observe(document, { subtree: true, childList: true, attributes: true, characterData: true });
  }
  w.__wpLastMut = performance.now();
  return { count: w.__wpMutCount as number };
}

/** How long the DOM has been quiet, and how many mutations happened in this document so far. */
function idle() {
  if (!w.__wpObserver) arm();
  const busy = Array.from(document.querySelectorAll('[aria-busy="true"]')).some(isVisible);
  return { sinceMs: Math.round(performance.now() - w.__wpLastMut), count: w.__wpMutCount as number, busy, url: location.href };
}

/** Whether the target exists, is visible and enabled; `fatal` means waiting will not help. */
function ready(target: string) {
  const el = find(target);
  if ("error" in el) return { ok: false, reason: el.error, fatal: !!el.fatal };
  if (!isVisible(el)) return { ok: false, reason: `element is not visible: ${short(el)}` };
  if ((el as any).disabled) return { ok: false, reason: `element is disabled: ${short(el)}` };
  return { ok: true, reresolved };
}

function locate(target: string) {
  const el = find(target);
  if ("error" in el) return el;
  el.scrollIntoView({ block: "center", inline: "center", behavior: "instant" });
  const r = el.getBoundingClientRect();
  return { x: r.left + r.width / 2, y: r.top + r.height / 2, w: r.width, h: r.height, desc: short(el) };
}

function click(target: string) {
  const el = find(target);
  if ("error" in el) return el;
  const { count } = arm();
  // People click a checkbox/radio through its label; some sites only react to label clicks
  // (the label then checks the input itself).
  const choice = el instanceof HTMLInputElement && (el.type === "radio" || el.type === "checkbox");
  const lbl = choice ? Array.from((el as HTMLInputElement).labels || []).find(isVisible) : undefined;
  const h = (lbl || el) as HTMLElement;
  // Checking a box or radio changes no DOM, so report it explicitly.
  const checkedBefore = (el as HTMLInputElement).checked;
  fireClick(h);
  return { desc: short(el), count, reresolved, toggled: (el as HTMLInputElement).checked !== checkedBefore };
}

/** The events of a mouse click. Like a browser, focuses only when the page did not cancel mousedown
 * (dropdown menus cancel it to keep the focus in their input, and close when it leaves). */
function fireClick(h: HTMLElement) {
  h.scrollIntoView({ block: "center", inline: "center", behavior: "instant" });
  const r = h.getBoundingClientRect();
  const opts = { bubbles: true, cancelable: true, composed: true, clientX: r.left + r.width / 2, clientY: r.top + r.height / 2, button: 0 };
  h.dispatchEvent(new PointerEvent("pointerdown", opts));
  if (h.dispatchEvent(new MouseEvent("mousedown", opts))) h.focus?.();
  h.dispatchEvent(new PointerEvent("pointerup", opts));
  h.dispatchEvent(new MouseEvent("mouseup", opts));
  h.click();
}

/** Focuses the element (optionally selecting its content so typed text replaces it). */
function focus(target: string, selectAll: boolean) {
  const el = find(target);
  if ("error" in el) return el;
  const h = el as HTMLElement;
  const textInput = el instanceof HTMLInputElement && !/^(checkbox|radio|submit|button|reset|file|image|range|color)$/.test(el.type);
  if (!textInput && !(el instanceof HTMLTextAreaElement) && !h.isContentEditable) {
    return { error: `element is not editable: ${short(el)}` };
  }
  const { count } = arm();
  h.scrollIntoView({ block: "center", behavior: "instant" });
  h.focus();
  if (selectAll) {
    if (el instanceof HTMLInputElement || el instanceof HTMLTextAreaElement) el.select();
    else if (h.isContentEditable) document.execCommand("selectAll");
  }
  return { desc: short(el), count, reresolved };
}

function type(target: string, text: string, clear: boolean) {
  const el = find(target);
  if ("error" in el) return el;
  const { count } = arm();
  const h = el as HTMLElement;
  h.scrollIntoView({ block: "center", behavior: "instant" });
  h.focus();
  const fire = () => {
    el.dispatchEvent(new Event("input", { bubbles: true }));
    el.dispatchEvent(new Event("change", { bubbles: true }));
  };
  if (el instanceof HTMLInputElement || el instanceof HTMLTextAreaElement) {
    // Use the native setter so frameworks (React etc.) notice the change.
    const proto = el instanceof HTMLInputElement ? HTMLInputElement.prototype : HTMLTextAreaElement.prototype;
    Object.getOwnPropertyDescriptor(proto, "value")!.set!.call(el, clear ? text : el.value + text);
    fire();
  } else if (el instanceof HTMLSelectElement) {
    const opt = nativeOption(el, text);
    if ("error" in opt) return opt;
    el.value = opt.value;
    fire();
  } else if (h.isContentEditable) {
    if (clear) document.execCommand("selectAll");
    document.execCommand("insertText", false, text);
  } else {
    return { error: `element is not editable: ${short(el)}` };
  }
  return { desc: short(el), count, reresolved };
}

const notFound = (text: string, labels: string[]) =>
  ({ error: `option not found: "${text}"; options: ${labels.slice(0, 15).map((s) => clean(s, 40)).join(" | ") || "(none)"}${labels.length > 15 ? " ..." : ""}` });

/** The <select> option whose value is `text`, or whose text matches it as bestMatch does. */
function nativeOption(el: HTMLSelectElement, text: string): HTMLOptionElement | Err {
  const opts = Array.from(el.options);
  return opts.find((o) => o.value === text) || bestMatch(opts, (o) => [o.text], text) || notFound(text, opts.map((o) => o.text));
}

const yieldTask = () => new Promise<void>((r) => {
  const c = new MessageChannel();
  c.port1.onmessage = () => r();
  c.port2.postMessage(null);
});

/** Polls get() until it returns something truthy or ms pass. The first polls only yield to the event
 * loop (a re-render after a key), then every 25 ms (timers run at most once a second in hidden windows). */
async function until<T>(get: () => T, ms: number): Promise<T> {
  const end = performance.now() + ms;
  let v = get();
  for (let i = 0; !v && performance.now() < end; i++) {
    await (i < 50 ? yieldTask() : new Promise((r) => setTimeout(r, 25)));
    v = get();
  }
  return v;
}

/** Text of the element minus that of some of its descendants (placeholders, live regions, menus). */
function textWithout(el: HTMLElement, skip: Element[]): string {
  let t = el.innerText || "";
  for (const s of skip) if (el.contains(s)) t = t.replace((s as HTMLElement).innerText || "", " ");
  return clean(t, 100);
}

/** The value a combobox shows: its own value (autocompletes), else the text next to it, as in
 * react-select, which keeps the input for the search text and shows the value in a sibling. */
function comboValue(field: HTMLElement): string {
  if (field instanceof HTMLInputElement || field instanceof HTMLTextAreaElement) {
    if (field.value) return clean(field.value, 100);
  }
  const byIds = (attr: string) => (field.getAttribute(attr) || "").split(/\s+/).filter(Boolean).map((id) => document.getElementById(id));
  const labels: (Element | null)[] = [...byIds("aria-labelledby"), ...Array.from((field as HTMLInputElement).labels || [])];
  const skip = [
    ...byIds("aria-describedby"), ...byIds("aria-controls"), ...labels,
    ...Array.from(document.querySelectorAll('[aria-live],[role=log],[role=status],[role=listbox]')),
  ].filter((e): e is Element => !!e);
  let p: HTMLElement | null = field instanceof HTMLInputElement || field instanceof HTMLTextAreaElement ? field.parentElement : field;
  for (let i = 0; p && p !== document.body && i < 4; i++, p = p.parentElement) {
    // Past the field's own box: the text there belongs to other controls (search buttons, other fields' labels).
    const other = (c: Element) => c !== field && !field.contains(c) && !labels.includes(c) &&
      (isInteractive(c) || c.localName === "label") && isVisible(c);
    if (p !== field && Array.from(p.querySelectorAll("*")).some(other)) break;
    const t = textWithout(p, skip);
    if (t) return t;
  }
  return "";
}

/** The text field of a combobox: ARIA 1.1 comboboxes wrap it; react-select puts the role on the input itself. */
function fieldOf(box: Element): HTMLElement {
  return (box.matches("input,textarea") ? box : box.querySelector("input:not([type=hidden]),textarea") || box) as HTMLElement;
}

/**
 * Before a click on an option of a combobox's list: remembers the combobox, the option and the value
 * the field shows, so optionResult() can tell whether the click chose it (the click may land and choose
 * nothing, if the menu closed first). Returns whether the target is such an option.
 */
function watchOption(target: string) {
  w.__wpOptionWatch = null;
  const el = find(target);
  if ("error" in el) return false;
  const opt = el.closest("[role=option]") as HTMLElement | null;
  if (!opt) return false;
  const boxes = Array.from(document.querySelectorAll("[role=combobox]"));
  const controls = (b: Element) => ((b.getAttribute("aria-controls") || "") + " " + (b.getAttribute("aria-owns") || ""))
    .split(/\s+/).some((id) => id && document.getElementById(id)?.contains(opt));
  const open = boxes.filter((b) => b.getAttribute("aria-expanded") === "true");
  const box = boxes.find(controls) || (open.length === 1 ? open[0] : undefined);
  if (!box) return false;
  const field = fieldOf(box);
  w.__wpOptionWatch = {
    box, field, list: opt.closest("[role=listbox]") || opt.parentElement,
    option: clean(opt.innerText || opt.getAttribute("aria-label")), before: comboValue(field),
  };
  return true;
}

/** After the click watched by watchOption: whether the field shows the option now, and the combobox's ref. */
function optionResult() {
  const o = w.__wpOptionWatch;
  w.__wpOptionWatch = null;
  if (!o || !o.field.isConnected) return null;
  const value = comboValue(o.field);
  // An autocomplete holding the typed text, with its list still open, has not chosen anything.
  const listOpen = o.list.isConnected && isVisible(o.list);
  const selected = value.toLowerCase().includes(o.option.toLowerCase()) && (value !== o.before || !listOpen);
  syncRefCount();
  return { selected, value, option: o.option, ref: refOf(o.box) };
}

/** The open list of a combobox: the one it points to, else a visible [role=listbox] that was not there before. */
function listboxOf(nodes: Element[], before: Set<Element>): Element | null {
  for (const n of nodes) {
    for (const id of ((n.getAttribute("aria-controls") || "") + " " + (n.getAttribute("aria-owns") || "")).split(/\s+/)) {
      const c = id ? document.getElementById(id) : null;
      const lb = c && (c.getAttribute("role") === "listbox" ? c : c.querySelector("[role=listbox]"));
      if (lb && isVisible(lb)) return lb;
    }
  }
  const shown = Array.from(document.querySelectorAll("[role=listbox]")).filter(isVisible);
  return shown.find((l) => !before.has(l)) || (shown.length === 1 ? shown[0] : null);
}

function key(el: Element, k: "ArrowDown" | "ArrowUp" | "Enter" | "Escape") {
  const code = { ArrowDown: 40, ArrowUp: 38, Enter: 13, Escape: 27 }[k];
  el.dispatchEvent(new KeyboardEvent("keydown", { key: k, code: k, keyCode: code, which: code, bubbles: true, cancelable: true, composed: true }));
}

/**
 * Chooses the option matching `text` in a custom dropdown (role=combobox) or a <select>, in one call
 * and with synthetic events only, so it works with the window hidden or unfocused, and the menu has
 * no time to close between steps. Filters by typing when the field is editable, moves with
 * ArrowDown/ArrowUp (one per task, as the page re-renders in between) and confirms with Enter.
 */
async function choose(target: string, text: string) {
  const el = find(target);
  if ("error" in el) return el;
  const again = reresolved;
  const { count } = arm();
  if (el instanceof HTMLSelectElement) {
    const opt = nativeOption(el, text);
    if ("error" in opt) return opt;
    const prev = el.value;
    el.focus();
    el.value = opt.value;
    el.dispatchEvent(new Event("input", { bubbles: true }));
    el.dispatchEvent(new Event("change", { bubbles: true }));
    const shown = clean(el.options[el.selectedIndex]?.text);
    return {
      desc: short(el), count, reresolved: again, toggled: el.value !== prev,
      extra: { selected: true, option: clean(opt.text), value: shown },
    };
  }
  const box = (el.getAttribute("role") === "combobox" ? el : el.querySelector("[role=combobox]")) as HTMLElement | null;
  if (!box) return { error: `not a combobox: ${short(el)}` };
  const field = fieldOf(box);
  const nodes = [field, box];
  const attr = (a: string) => field.getAttribute(a) ?? box.getAttribute(a);
  const before = new Set(Array.from(document.querySelectorAll("[role=listbox]")).filter(isVisible));
  // react-select's non-searchable input is only aria-readonly.
  const editable = (field instanceof HTMLInputElement || field instanceof HTMLTextAreaElement) && !field.readOnly &&
    attr("aria-readonly") !== "true";

  box.scrollIntoView({ block: "center", behavior: "instant" });
  field.focus();
  if (editable) {
    const proto = field instanceof HTMLInputElement ? HTMLInputElement.prototype : HTMLTextAreaElement.prototype;
    Object.getOwnPropertyDescriptor(proto, "value")!.set!.call(field, text);
    field.dispatchEvent(new Event("input", { bubbles: true }));
    // Some comboboxes open their list only on a key.
    if (!(await until(() => listboxOf(nodes, before), 500))) key(field, "ArrowDown");
  } else if (!listboxOf(nodes, before)) {
    key(field, "ArrowDown");
  }

  // Options may arrive later (filtered on a server): wait for a match, not only for the list.
  let labels: string[] = [];
  const opt = await until(() => {
    const lb = listboxOf(nodes, before);
    if (!lb) return undefined;
    const opts = Array.from(lb.querySelectorAll("[role=option]")).filter(isVisible) as HTMLElement[];
    labels = opts.map((o) => o.innerText || o.getAttribute("aria-label") || "");
    return bestMatch(opts, (o) => [o.innerText || "", o.getAttribute("aria-label") || ""], text);
  }, 3000);
  if (!opt) {
    if (!listboxOf(nodes, before)) return { error: `no list of options opened for ${short(box)}` };
    if (editable && !labels.length) {
      // The typed text filtered everything out: clear it to list what there is.
      Object.getOwnPropertyDescriptor(Object.getPrototypeOf(field), "value")!.set!.call(field, "");
      field.dispatchEvent(new Event("input", { bubbles: true }));
      await until(() => {
        const lb = listboxOf(nodes, before);
        labels = Array.from(lb?.querySelectorAll("[role=option]") || []).filter(isVisible)
          .map((o) => (o as HTMLElement).innerText || o.getAttribute("aria-label") || "");
        return labels.length;
      }, 1000);
    }
    key(field, "Escape");
    return notFound(text, labels);
  }
  const option = clean(opt.innerText || opt.getAttribute("aria-label"));

  const active = () => attr("aria-activedescendant") || "";
  // react-select sets aria-activedescendant to "" while no option is active, and leaves it out on Apple devices.
  let reached = false;
  if (opt.id && attr("aria-activedescendant") !== null) {
    const opts = Array.from(listboxOf(nodes, before)?.querySelectorAll("[role=option]") || []);
    const goal = opts.indexOf(opt);
    for (let n = 0; !(reached = active() === opt.id) && n < 2 * opts.length; n++) {
      const cur = opts.findIndex((o) => o.id === active());
      const prev = active();
      key(field, cur !== -1 && cur > goal ? "ArrowUp" : "ArrowDown");
      await until(() => active() !== prev, 1000);
    }
  }
  if (reached) key(field, "Enter");
  else fireClick(opt);

  // A field that still holds the typed text with its list open has not chosen anything yet.
  const chosen = () => {
    const v = comboValue(field);
    const typed = editable && (field as HTMLInputElement).value === text && !!listboxOf(nodes, before);
    return !typed && v.toLowerCase().includes(option.toLowerCase()) ? v : "";
  };
  const value = await until(chosen, 1500);
  if (!value) return { error: `did not choose "${option}": the field shows "${comboValue(field)}"` };
  return { desc: short(box), count, reresolved: again, extra: { selected: true, option, value } };
}

/** Submits the target's form (or the focused / first visible form) the way a submit button would. */
function submitForm(target: string | null) {
  let form: HTMLFormElement | null = null;
  let submitter: HTMLElement | null = null;
  if (target) {
    const el = find(target);
    if ("error" in el) return el;
    form = el instanceof HTMLFormElement ? el : (el as HTMLInputElement).form || el.closest("form");
    if (!form) return { error: `no form around ${short(el)}` };
    const isSubmit = (el instanceof HTMLButtonElement && el.type === "submit") ||
      (el instanceof HTMLInputElement && (el.type === "submit" || el.type === "image"));
    if (isSubmit && (el as HTMLButtonElement).form === form) submitter = el as HTMLElement;
  } else {
    form = document.activeElement?.closest("form") || Array.from(document.forms).find(isVisible) || null;
    if (!form) return { error: "no form on the page" };
  }
  const { count } = arm();
  // requestSubmit runs the page's submit handlers and validation; form.submit() skips them.
  if (typeof form.requestSubmit === "function") form.requestSubmit(submitter);
  else form.submit();
  return { desc: short(form), count };
}

function scroll(to: string, amount: number | null) {
  const step = amount || Math.round(innerHeight * 0.8);
  if (to === "down") scrollBy(0, step);
  else if (to === "up") scrollBy(0, -step);
  else if (to === "top") scrollTo(0, 0);
  else if (to === "bottom") scrollTo(0, document.documentElement.scrollHeight);
  else {
    const el = find(to);
    if ("error" in el) return el;
    el.scrollIntoView({ block: "center", behavior: "instant" });
  }
  return { y: Math.round(scrollY), height: document.documentElement.scrollHeight, viewport: innerHeight };
}

function check(selector: string | null, text: string | null): boolean {
  if (selector) {
    const el = document.querySelector(selector);
    if (!el || !isVisible(el)) return false;
  }
  if (text && !(document.body?.innerText || "").includes(text)) return false;
  return true;
}

function html(selector: string | null) {
  const el = selector ? document.querySelector(selector) : document.documentElement;
  if (!el) return { error: `selector not found: ${selector}` };
  return { url: location.href, title: document.title, html: el.outerHTML };
}

function text(selector: string | null, maxChars: number) {
  const el = (selector ? document.querySelector(selector) : document.body) as HTMLElement | null;
  if (!el) return { error: `selector not found: ${selector}` };
  const t = el.innerText || "";
  return { url: location.href, title: document.title, text: t.slice(0, maxChars), truncated: t.length > maxChars };
}

/** Finds captcha checkbox widgets (reCAPTCHA, hCaptcha, Turnstile) and whether an image challenge is showing. */
function findCaptcha() {
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

/**
 * This frame's token, set by its parent's snapshot (null in the top frame or before a snapshot).
 * Also re-sends the tokens of this frame's child iframes, for children injected after the snapshot.
 */
function frameInfo() {
  for (const f of Array.from(document.querySelectorAll("iframe[data-wp-frame]"))) frameToken(f as HTMLIFrameElement);
  return { token: (w.__wpFrameToken as string | undefined) ?? null };
}

/** Viewport position of the content box of the child iframe with this token, or null if it is not in this frame. */
function frameOffset(token: string) {
  const f = document.querySelector(`iframe[data-wp-frame="${CSS.escape(token)}"]`) as HTMLIFrameElement | null;
  if (!f) return null;
  const r = f.getBoundingClientRect();
  const cs = getComputedStyle(f);
  return { x: r.left + f.clientLeft + parseFloat(cs.paddingLeft), y: r.top + f.clientTop + parseFloat(cs.paddingTop) };
}

const visibility = () => document.visibilityState;

w.__wp = {
  frameInfo, frameOffset, snapshot, locate, click, focus, type, scroll, check, html, text, findCaptcha, arm, idle, ready,
  submitForm, choose, watchOption, optionResult, visibility,
};
