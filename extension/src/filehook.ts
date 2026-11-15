// Runs in the page's main world, in the target's frame, while `upload` clicks a target that has no file input near
// it. Many pages make the input in script when their button is clicked (createElement, then click() or
// showPicker()) and never add it to the document. While armed, such a call opens no file picker: the files go to
// that input instead, and it gets input and change a moment later, as when the picker closes. With `native`
// (upload --trusted, whose real click lets the debugger catch the picker) input calls go through untouched.
// showOpenFilePicker() is refused either way (as if the user cancelled): its file handles cannot be made here.
// The background arms it and reads what it caught through window[Symbol.for("webpilot.files")].

export {};

type UpFile = { name: string; type: string; data: string; lastModified?: number };
type Caught = { desc?: string; files?: { name: string; bytes: number }[]; error?: string };
type FileHook = { until: number; native: boolean; files: UpFile[] | null; caught: Caught | null };

(() => {
  const KEY = Symbol.for("webpilot.files");
  const w = window as any;
  if (w[KEY]) return;
  const state: FileHook = { until: 0, native: false, files: null, caught: null };
  Object.defineProperty(w, KEY, { value: state });
  const armed = () => Date.now() <= state.until && !state.caught;

  const desc = (i: HTMLInputElement) => {
    const accept = i.getAttribute("accept");
    return `input${i.id ? "#" + i.id : ""}${i.name ? ` name=${i.name}` : ""}${accept ? ` accept=${accept.slice(0, 40)}` : ""}` +
      `${i.multiple ? " multiple" : ""}${i.isConnected ? "" : " (made by the page, not in the document)"}`;
  };

  /** Gives the armed files to the input; false when the call is not one to catch. */
  const take = (input: HTMLInputElement): boolean => {
    if (!armed() || state.native || input.type !== "file") return false;
    const files = state.files ?? [];
    state.files = null;
    if (files.length > 1 && !input.multiple) {
      state.caught = { error: `${files.length} files for a file input that takes one (no multiple attribute): ${desc(input)}` };
      return true;
    }
    const dt = new DataTransfer();
    for (const f of files) {
      const bin = atob(f.data);
      const bytes = new Uint8Array(bin.length);
      for (let i = 0; i < bin.length; i++) bytes[i] = bin.charCodeAt(i);
      dt.items.add(new File([bytes], f.name, { type: f.type, lastModified: f.lastModified ?? Date.now() }));
    }
    state.caught = { desc: desc(input), files: Array.from(dt.files, (f) => ({ name: f.name, bytes: f.size })) };
    // After the call returns, as a picker answers: pages often add their change listener right after click().
    setTimeout(() => {
      input.files = dt.files;
      input.dispatchEvent(new Event("input", { bubbles: true, composed: true }));
      input.dispatchEvent(new Event("change", { bubbles: true }));
    }, 0);
    return true;
  };

  const proto = HTMLInputElement.prototype as any;
  const click = proto.click;
  // Methods, not arrow functions: same `this` handling as the originals.
  proto.click = { click(this: HTMLInputElement) { if (!take(this)) return click.call(this); } }.click;
  const showPicker = proto.showPicker;
  if (typeof showPicker === "function") {
    proto.showPicker = { showPicker(this: HTMLInputElement) { if (!take(this)) return showPicker.call(this); } }.showPicker;
  }
  const open = w.showOpenFilePicker;
  if (typeof open === "function") {
    w.showOpenFilePicker = {
      showOpenFilePicker(this: unknown, ...args: unknown[]) {
        if (!armed()) return open.apply(this, args);
        state.caught = { error: "the page opens its file picker with showOpenFilePicker(), which upload cannot fill; " +
          "if it also takes dropped files, try upload --drop on its drop zone" };
        return Promise.reject(new DOMException("The user aborted a request.", "AbortError"));
      },
    }.showOpenFilePicker;
  }
})();
