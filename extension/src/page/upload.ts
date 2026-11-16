// Page script: file inputs found for a target, files given to them or dropped, and marks for upload --trusted.

import { Err, deepAll, rootOf, clean, short } from "./dom";
import { reresolved, find, ready } from "./find";
import { arm } from "./wait";

const isFileInput = (e: unknown): e is HTMLInputElement => e instanceof HTMLInputElement && e.type === "file";

/** A file input as the agent can tell it from others: id, name, label, accept, multiple. */
function fileDesc(i: HTMLInputElement): string {
  const accept = i.getAttribute("accept");
  return `${short(i)}${i.name ? ` name=${i.name}` : ""}${accept ? ` accept=${clean(accept, 40)}` : ""}${i.multiple ? " multiple" : ""}`;
}

/**
 * The file input an upload to `el` goes to: el itself, its label's control, the only file input inside it or its
 * form ("near"); with `far`, else the only one in its shadow root or the document. Such inputs are often hidden
 * behind a styled label or button, so visibility does not matter. Several candidates at the first level that has
 * any is an error; none is null. upload clicks the target before looking far (it may make its input in script).
 */
function fileInputFor(el: Element, far: boolean): HTMLInputElement | Err | null {
  if (isFileInput(el)) return el;
  const label = el instanceof HTMLLabelElement ? el : el.closest("label");
  if (isFileInput(label?.control)) return label!.control as HTMLInputElement;
  const levels: Element[][] = [[
    ...Array.from(el.querySelectorAll("input[type=file]")),
    ...(el.shadowRoot ? deepAll("input[type=file]", el.shadowRoot) : []),
  ]];
  const form = (el as HTMLButtonElement).form || el.closest("form");
  if (form) levels.push(Array.from(form.elements).filter(isFileInput));
  if (far) {
    const root = rootOf(el);
    levels.push(deepAll("input[type=file]", root));
    if (root !== document) levels.push(deepAll("input[type=file]"));
  }
  for (const level of levels) {
    const found = Array.from(new Set(level));
    if (found.length === 1) return found[0] as HTMLInputElement;
    if (found.length > 1) {
      const list = found.slice(0, 8).map((i) => fileDesc(i as HTMLInputElement)).join("; ");
      return { error: `several file inputs for ${short(el)}: ${list}; target one of them (a selector such as input[name=...])`, fatal: true };
    }
  }
  return null;
}

const noFileInput = (el: Element, clicked: boolean): Err => ({
  error: `no file input for ${short(el)}${clicked ? ", and clicking it opened no file picker" : ""}: target the ` +
    "input[type=file], its label or the button that opens it; for a drop zone, pass --drop",
});

/**
 * ready() for upload: the target exists and leads to an enabled file input, which may be hidden; or, with no file
 * input near it, it is visible and enabled, since upload will click it (it may make its input in script).
 */
export function readyUpload(target: string) {
  const el = find(target);
  if ("error" in el) return { ok: false, reason: el.error, fatal: !!el.fatal };
  const near = fileInputFor(el, false);
  if (!near) {
    const r = ready(target);
    if (r.ok) return r;
    const far = fileInputFor(el, true);
    if (!far) return { ok: false, reason: noFileInput(el, false).error };
    if ("error" in far) return { ok: false, reason: far.error, fatal: !!far.fatal };
    return { ok: true, reresolved };
  }
  if ("error" in near) return { ok: false, reason: near.error, fatal: !!near.fatal };
  if (near.disabled) return { ok: false, reason: `the file input is disabled: ${fileDesc(near)}` };
  return { ok: true, reresolved };
}

/** Whether the target has a file input near it (see fileInputFor), so upload needs no click. */
export function nearFileInput(target: string): boolean {
  const el = find(target);
  return !("error" in el) && fileInputFor(el, false) !== null;
}

type UpFile = { name: string; type: string; data: string; lastModified?: number };

/**
 * Gives the files to the target's file input (see fileInputFor; `far` once a click opened no picker) and fires
 * input and change, as choosing them in the file picker does; with drop, fires dragenter, dragover and drop
 * carrying them on the target instead, for drop zones. The files come as base64 and are built here, so this
 * needs no debugger and works in any frame.
 */
export function upload(target: string, files: UpFile[], drop: boolean, far = true) {
  const el = find(target);
  if ("error" in el) return el;
  const again = reresolved;
  const input = drop ? null : (fileInputFor(el, far) ?? noFileInput(el, far));
  if (input && "error" in input) return input;
  if (input && files.length > 1 && !input.multiple) {
    return { error: `${files.length} files for a file input that takes one (no multiple attribute): ${fileDesc(input)}` };
  }
  const dt = new DataTransfer();
  for (const f of files) {
    const bin = atob(f.data);
    const bytes = new Uint8Array(bin.length);
    for (let i = 0; i < bin.length; i++) bytes[i] = bin.charCodeAt(i);
    dt.items.add(new File([bytes], f.name, { type: f.type, lastModified: f.lastModified ?? Date.now() }));
  }
  const { count } = arm();
  const sent = Array.from(dt.files, (f) => ({ name: f.name, bytes: f.size }));
  if (input) {
    const desc = fileDesc(input); // before the files: the input's value names them
    input.files = dt.files;
    input.dispatchEvent(new Event("input", { bubbles: true, composed: true }));
    input.dispatchEvent(new Event("change", { bubbles: true }));
    return { desc, count, reresolved: again, toggled: true, extra: { files: sent } };
  }
  el.scrollIntoView({ block: "center", inline: "center", behavior: "instant" });
  const r = el.getBoundingClientRect();
  const opts = { bubbles: true, cancelable: true, composed: true, dataTransfer: dt, clientX: r.left + r.width / 2, clientY: r.top + r.height / 2 };
  el.dispatchEvent(new DragEvent("dragenter", opts));
  const over = !el.dispatchEvent(new DragEvent("dragover", opts));
  const dropped = !el.dispatchEvent(new DragEvent("drop", opts));
  // A drop zone cancels dragover (to accept the drop) and drop (so the browser does not open the file).
  const extra: Record<string, unknown> = { files: sent };
  if (!over && !dropped) {
    extra.hint = "nothing on the page took the drop (no handler cancelled dragover or drop); target the drop zone " +
      "itself, or its file input without --drop";
  }
  return { desc: short(el), count, reresolved: again, extra };
}

/**
 * upload --trusted: marks the target's file input (see fileInputFor) with data-wp-upload=tok, for the debugger to
 * find it and give it the files by path. With none near it, marks the target instead, so the debugger can tell
 * it reaches the frame before clicking it. n: the number of files.
 */
export function markUpload(target: string, tok: string, n: number, far: boolean) {
  const el = find(target);
  if ("error" in el) return el;
  const again = reresolved;
  const input = fileInputFor(el, far) ?? (far ? noFileInput(el, true) : null);
  if (input && "error" in input) return input;
  if (input && n > 1 && !input.multiple) {
    return { error: `${n} files for a file input that takes one (no multiple attribute): ${fileDesc(input)}` };
  }
  if (input?.disabled) return { error: `the file input is disabled: ${fileDesc(input)}` };
  const { count } = arm();
  (input ?? el).setAttribute("data-wp-upload", tok);
  return { input: input ? fileDesc(input) : null, desc: short(el), count, reresolved: again };
}

export function unmarkUpload(tok: string) {
  for (const e of deepAll(`[data-wp-upload="${CSS.escape(tok)}"]`)) e.removeAttribute("data-wp-upload");
}
