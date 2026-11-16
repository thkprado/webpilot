// Runs inside web pages (extension isolated world). Injected on demand by background.ts,
// which then calls globalThis.__wp[name](...args). Every function returns JSON-serialisable data;
// failures are returned as {error} so they survive executeScript. The functions live in page/*.ts.

import { w } from "./page/dom";
import { ready, shown, locate } from "./page/find";
import { frameInfo, frameOffset } from "./page/frames";
import { watchOption, optionResult, choose } from "./page/combo";
import { snapshot } from "./page/snapshot";
import { arm, idle, check, visibility } from "./page/wait";
import { click, hover, focus, typeText, fillField, submitForm, scroll } from "./page/actions";
import { readyUpload, nearFileInput, upload, markUpload, unmarkUpload } from "./page/upload";
import { html, text, findCaptcha } from "./page/read";
import { requests } from "./page/requests";

w.__wp = {
  frameInfo, frameOffset, snapshot, locate, click, focus, type: typeText, scroll, check, html, text, findCaptcha, arm, idle, ready,
  submitForm, choose, watchOption, optionResult, visibility, readyUpload, nearFileInput, upload, markUpload, unmarkUpload, requests, shown, hover,
  fillField,
};
