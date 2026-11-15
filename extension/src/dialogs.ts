// Runs in the page's main world (executeScript during an action, or a content script registered while a
// navigation loads). Wraps alert/confirm/prompt so that, while an agent's command acts on the page, they
// answer at once instead of blocking the page (and every script the extension runs in it), and are
// reported in the command's result. Outside a command the page's own dialogs show as usual.
// The background reads and sets the state through window[Symbol.for("webpilot.dialogs")].

export {};

type Dialog = { type: "alert" | "confirm" | "prompt"; message: string; answer: unknown };
type DialogState = { accept: boolean; text: string | null; until: number; queue: Dialog[] };

(() => {
  const KEY = Symbol.for("webpilot.dialogs");
  const w = window as any;
  if (w[KEY]) return;
  // Loaded by a navigation: answer (by dismissing) for the first 30 s of the document, until the command
  // that navigated sets the policy or ends.
  const state: DialogState = { accept: false, text: null, until: Date.now() + 30000, queue: [] };
  Object.defineProperty(w, KEY, { value: state });
  const cut = (m: unknown) => (m === undefined ? "" : String(m)).slice(0, 300);
  for (const type of ["alert", "confirm", "prompt"] as const) {
    const original = w[type];
    if (typeof original !== "function") continue;
    const wrapper = {
      // A method, not an arrow function: same `this` handling and arity-free signature as the original.
      [type](this: unknown, ...args: unknown[]) {
        if (Date.now() > state.until) return original.apply(this, args);
        let answer: unknown;
        if (type === "alert") answer = undefined;
        else if (type === "confirm") answer = state.accept;
        else answer = state.accept ? (state.text ?? (args[1] === undefined ? "" : String(args[1]))) : null;
        state.queue.push({ type, message: cut(args[0]), answer: answer ?? null });
        if (state.queue.length > 50) state.queue.shift(); // a page calling alert in a loop
        return answer;
      },
    }[type];
    w[type] = wrapper;
  }
})();
