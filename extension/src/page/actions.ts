// Page script: click, hover, focus, type, fill, submit and scroll with synthetic events.

import { w, clean, isVisible, short, fireClick, chainOf, until } from "./dom";
import { reresolved, find } from "./find";
import { nativeOption, chooseIn } from "./combo";
import { arm } from "./wait";

export function click(target: string) {
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

/**
 * The events of the pointer moving onto the element's center, from the element the last hover left it on: out and
 * leave there, over and enter here (enter on each element around it the pointer was not in yet, outermost first),
 * then a move. Opens menus and tooltips run by script; CSS :hover needs the real pointer (hover --trusted).
 */
export function hover(target: string) {
  const el = find(target);
  if ("error" in el) return el;
  const { count } = arm();
  const desc = short(el); // before the menu it opens adds its text
  el.scrollIntoView({ block: "center", inline: "center", behavior: "instant" });
  const r = el.getBoundingClientRect();
  const at = { clientX: r.left + r.width / 2, clientY: r.top + r.height / 2, pointerId: 1, pointerType: "mouse", isPrimary: true };
  const prev = w.__wpHovered as Element | undefined;
  const from = prev && prev !== el && prev.isConnected ? prev : null;
  const fromChain = from ? chainOf(from) : [];
  const toChain = chainOf(el);
  const fire = (t: Element, Kind: typeof MouseEvent, type: string, bubbles: boolean, relatedTarget: Element | null) =>
    t.dispatchEvent(new Kind(type, { ...at, bubbles, cancelable: bubbles, composed: bubbles, relatedTarget }));
  if (from) {
    fire(from, PointerEvent, "pointerout", true, el);
    for (const t of fromChain.filter((t) => !toChain.includes(t))) fire(t, PointerEvent, "pointerleave", false, el);
    fire(from, MouseEvent, "mouseout", true, el);
    for (const t of fromChain.filter((t) => !toChain.includes(t))) fire(t, MouseEvent, "mouseleave", false, el);
  }
  const entered = toChain.filter((t) => !fromChain.includes(t)).reverse();
  fire(el, PointerEvent, "pointerover", true, from);
  for (const t of entered) fire(t, PointerEvent, "pointerenter", false, from);
  fire(el, MouseEvent, "mouseover", true, from);
  for (const t of entered) fire(t, MouseEvent, "mouseenter", false, from);
  fire(el, PointerEvent, "pointermove", true, null);
  fire(el, MouseEvent, "mousemove", true, null);
  w.__wpHovered = el;
  return { desc, count, reresolved };
}

/** Focuses the element (optionally selecting its content so typed text replaces it). */
export function focus(target: string, selectAll: boolean) {
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

export function typeText(target: string, text: string, clear: boolean) {
  const el = find(target);
  if ("error" in el) return el;
  return typeInto(el, text, clear);
}

function typeInto(el: Element, text: string, clear: boolean) {
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

const TOGGLE_ROLES = new Set(["checkbox", "radio", "switch", "menuitemcheckbox", "menuitemradio"]);
const NOT_TEXT = /^(checkbox|radio|submit|button|reset|file|image|hidden)$/;

/** Whether a checkbox, radio or switch is on: its `checked`, else its aria-checked. */
function isOn(el: Element): boolean {
  if (el instanceof HTMLInputElement) return el.checked;
  return el.getAttribute("aria-checked") === "true";
}

/**
 * One field of `fill`: types into a text field, chooses an option in a <select> or combobox, or checks or unchecks
 * a checkbox, radio or switch ("true"/"false"), clicking only when its state differs. A label stands for its field.
 * Returns what the field holds afterwards, in `extra`.
 */
export async function fillField(target: string, value: string) {
  const found = find(target);
  if ("error" in found) return found;
  const again = reresolved;
  const el = found instanceof HTMLLabelElement && found.control ? found.control : found;
  const role = el.getAttribute("role") || "";
  const input = el instanceof HTMLInputElement ? el : null;
  if (input?.type === "file") return { error: `${short(el)} is a file input: use upload ${target} FILE` };
  if ((input || el instanceof HTMLTextAreaElement) && (el as HTMLInputElement).readOnly && role !== "combobox") {
    return { error: `${short(el)} is read-only` };
  }

  if (input?.type === "checkbox" || input?.type === "radio" || TOGGLE_ROLES.has(role)) {
    const kind = input ? input.type : role;
    const want = value.trim().toLowerCase();
    if (want !== "true" && want !== "false") return { error: `a ${kind} takes true or false, not ${JSON.stringify(value)}` };
    const on = want === "true";
    const { count } = arm();
    const desc = short(el);
    if (isOn(el) === on) return { desc, count, reresolved: again, extra: { field: desc, checked: on } };
    if (!on && (kind === "radio" || kind === "menuitemradio")) {
      return { error: `${desc} is checked; a radio button is unchecked by checking another one of its group (true)` };
    }
    // Through a visible label, like click: some sites only react to label clicks.
    const lbl = input ? Array.from(input.labels || []).find(isVisible) : undefined;
    fireClick((lbl || el) as HTMLElement);
    // A custom switch may re-render: then read the element the target names now.
    const now = () => {
      const e = el.isConnected ? el : find(target);
      return !("error" in e) && isOn(e) === on;
    };
    if (!(await until(now, 1000))) return { error: `clicking ${desc} did not ${on ? "check" : "uncheck"} it; try click --trusted` };
    return { desc, count, reresolved: again, toggled: true, extra: { field: desc, checked: on } };
  }

  const editable = (!!input && !NOT_TEXT.test(input.type)) || el instanceof HTMLTextAreaElement || (el as HTMLElement).isContentEditable;
  if (el instanceof HTMLSelectElement || role === "combobox" || (!editable && el.querySelector("[role=combobox]"))) {
    const r: any = await chooseIn(el, value, true);
    if (r.error) return r;
    const { selected, ...shown } = r.extra;
    return { ...r, extra: { field: r.desc, ...shown } };
  }
  if (!editable) {
    return {
      error: `${short(el)} is not a form field: fill takes text fields, selects, comboboxes, checkboxes, radios and ` +
        "switches (click buttons and links)",
    };
  }
  const r: any = typeInto(el, value, true);
  if (r.error) return r;
  // What the field kept (a mask or maxlength may change it); never a password's.
  const now = input || el instanceof HTMLTextAreaElement ? (el as HTMLInputElement).value : (el as HTMLElement).innerText;
  const extra = input?.type === "password" ? {} : { value: clean(now, 200) };
  return { ...r, reresolved: again, extra: { field: r.desc, ...extra } };
}

/** Submits the target's form (or the focused / first visible form) the way a submit button would. */
export function submitForm(target: string | null) {
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

export function scroll(to: string, amount: number | null) {
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
