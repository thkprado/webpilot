// Page script: <select> options and custom dropdowns (role=combobox): reading and choosing values.

import { Err, w, clean, isVisible, isInteractive, bestMatch, short, fireClick, until } from "./dom";
import { reresolved, syncRefCount, refOf, find } from "./find";
import { arm } from "./wait";

const notFound = (text: string, labels: string[]) =>
  ({ error: `option not found: "${text}"; options: ${labels.slice(0, 15).map((s) => clean(s, 40)).join(" | ") || "(none)"}${labels.length > 15 ? " ..." : ""}` });

/** The <select> option whose value is `text`, or whose text matches it as bestMatch does. */
export function nativeOption(el: HTMLSelectElement, text: string): HTMLOptionElement | Err {
  const opts = Array.from(el.options);
  return opts.find((o) => o.value === text) || bestMatch(opts, (o) => [o.text], text) || notFound(text, opts.map((o) => o.text));
}

/** Text of the element minus that of some of its descendants (placeholders, live regions, menus). */
function textWithout(el: HTMLElement, skip: Element[]): string {
  let t = el.innerText || "";
  for (const s of skip) if (el.contains(s)) t = t.replace((s as HTMLElement).innerText || "", " ");
  return clean(t, 100);
}

/** The value a combobox shows: its own value (autocompletes), else the text next to it, as in
 * react-select, which keeps the input for the search text and shows the value in a sibling. */
export function comboValue(field: HTMLElement): string {
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
export function watchOption(target: string) {
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
export function optionResult() {
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
export async function choose(target: string, text: string) {
  const el = find(target);
  if ("error" in el) return el;
  return chooseIn(el, text);
}

/** choose() on an element; with freeText, an editable combobox that opens no list keeps the typed text. */
export async function chooseIn(el: Element, text: string, freeText = false) {
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
  if (!box) {
    return { error: `not a combobox: ${short(el)}; target the dropdown's input (role=combobox in snapshot -i) or an element around it` };
  }
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
    if (!listboxOf(nodes, before)) {
      if (freeText && editable) {
        // An autocomplete with nothing to suggest: the typed text is the value.
        field.dispatchEvent(new Event("change", { bubbles: true }));
        return { desc: short(box), count, reresolved: again, extra: { value: clean((field as HTMLInputElement).value, 100) } };
      }
      return { error: `no list of options opened for ${short(box)}: not a listbox-style dropdown; click it, then snapshot -i` };
    }
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
