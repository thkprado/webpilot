/** Matches Chromium's refusal while the user drags a tab: "Tabs cannot be edited right now (user may be dragging a tab)." */
const DRAGGING = /cannot be edited right now/i;

/**
 * Runs a tab edit (chrome.tabs.update, create, remove, reload, group...) and runs it again while Chromium refuses it
 * because the user is dragging a tab, which lasts until they let go. Other errors are thrown at once. After `limitMs`
 * the refusal is thrown with what to do.
 */
export async function retryTabEdit<T>(edit: () => Promise<T>, limitMs = 10000, stepMs = 200): Promise<T> {
  const deadline = Date.now() + limitMs;
  for (;;) {
    try {
      return await edit();
    } catch (e) {
      const message = e instanceof Error ? e.message : String(e);
      if (!DRAGGING.test(message)) throw e;
      if (Date.now() >= deadline) {
        throw new Error(`${message.replace(/\.$/, "")}; still refused after ${limitMs / 1000} s: retry once the tab is let go`);
      }
      await new Promise((r) => setTimeout(r, stepMs));
    }
  }
}
