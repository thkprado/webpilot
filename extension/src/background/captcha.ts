// Service worker: captcha checkboxes (reCAPTCHA, hCaptcha, Turnstile) clicked with trusted input.

import { config, sleep } from "./config";
import { pageCall } from "./scripts";
import { mouseClick } from "./cdp";

export async function solveCheckbox(tabId: number) {
  const found = await pageCall(tabId, "findCaptcha");
  if (!found.widgets.length) {
    return { present: found.solved, solved: found.solved, challenge: found.challenge };
  }
  const w = found.widgets[0];
  await mouseClick(tabId, w.x + (w.kind === "recaptcha" ? 27 : 30), w.y + w.h / 2);
  await sleep(2500);
  const after = await pageCall(tabId, "findCaptcha");
  return {
    present: true,
    kind: w.kind,
    clicked: true,
    solved: after.solved,
    challenge: after.challenge,
    ...(after.challenge ? { note: "A visual challenge appeared; ask the user to solve it in the browser." } : {}),
  };
}

export async function autoCaptcha(tabId: number) {
  if (!config?.autoCaptcha) return undefined; // opt-in: "auto_captcha": true in ~/.webpilot/config.json
  try {
    const found = await pageCall(tabId, "findCaptcha");
    if (!found.widgets.length && !found.challenge) return undefined;
    return await solveCheckbox(tabId);
  } catch {
    return undefined;
  }
}
