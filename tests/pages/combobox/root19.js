// React 18+ root: updates from an event are flushed in a microtask, after the event.
import { createRoot } from "react-dom/client";

export const render = (el, node) => createRoot(node).render(el);
