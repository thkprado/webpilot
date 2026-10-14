// Legacy root (React 17): updates from an event are flushed before the event returns.
import { render as legacyRender } from "react-dom";

export const render = (el, node) => legacyRender(el, node);
