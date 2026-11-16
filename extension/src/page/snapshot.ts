// Page script: the text snapshot of the page, with a ref for each interactive element.

import { w, clean, isVisible, isInteractive, accessibleName, kindOf } from "./dom";
import { syncRefCount, refOf } from "./find";
import { frameToken } from "./frames";
import { comboValue } from "./combo";

const SKIP = new Set(["script", "style", "noscript", "template", "svg", "canvas", "meta", "link", "head", "object"]);
const BLOCK = new Set([
  "address", "article", "aside", "blockquote", "details", "dialog", "dd", "div", "dl", "dt", "fieldset",
  "figcaption", "figure", "footer", "form", "h1", "h2", "h3", "h4", "h5", "h6", "header", "hr", "li", "main",
  "nav", "ol", "p", "pre", "section", "table", "tr", "ul", "br", "summary", "caption", "thead", "tbody", "tfoot",
]);
// Link targets that are code or inline payloads, not destinations; left out of snapshots.
const SCRIPT_SCHEMES = new Set(["javascript:", "data:", "vbscript:"]);

let snapSeen: Record<string, number> = {};
let snapScoped = false;

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
    let u = "";
    try {
      // URL() trims and lowercases the scheme, so " JavaScript:" is caught too.
      const url = new URL(href, location.href);
      if (!SCRIPT_SCHEMES.has(url.protocol))
        u = url.origin === location.origin ? url.pathname + url.search + url.hash : url.href;
    } catch { /* malformed href: nothing useful to show */ }
    if (u) extra += ` -> ${clean(u, 100)}`;
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

export function snapshot(selector: string | null, maxChars: number, interactiveOnly: boolean) {
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
        push(`\u0001${frameToken(el as HTMLIFrameElement)}`); // replaced by the frame's snapshot in background/frames.ts
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
