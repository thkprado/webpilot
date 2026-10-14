// Popup: shows the connection state and lets the user rename this browser profile.
// The name lives in storage.local; the service worker reconnects when it changes.

import { PROFILE_NAME } from "./profile";

const STATES: Record<string, [string, string]> = {
  ON: ["Connected to the daemon", "on"],
  OFF: ["Daemon is not running (it starts on the first webpilot command)", "off"],
  CFG: ["Not configured: run webpilot setup", "err"],
  DUP: ["Another connected profile already uses this name: pick another", "err"],
};

const $ = <T extends HTMLElement>(id: string) => document.getElementById(id) as T;
const input = $<HTMLInputElement>("name");
const form = $<HTMLFormElement>("form");
const msg = $("msg");

async function showState() {
  const text = await chrome.action.getBadgeText({});
  const [label, cls] = STATES[text] ?? ["Starting...", "off"];
  const el = $("state");
  el.textContent = label;
  el.className = `state ${cls}`;
}

async function load() {
  const { profile } = await chrome.storage.local.get("profile");
  input.value = typeof profile === "string" ? profile : "";
  input.placeholder = "no name yet";
}

form.addEventListener("submit", async (ev) => {
  ev.preventDefault();
  const name = input.value.trim();
  if (!PROFILE_NAME.test(name)) {
    msg.textContent = "Invalid name: use 1 to 32 letters, digits, - or _.";
    msg.className = "msg err";
    return;
  }
  await chrome.storage.local.set({ profile: name });
  msg.textContent = "Saved. Reconnecting...";
  msg.className = "msg";
});

input.addEventListener("input", () => (msg.textContent = ""));

void load();
void showState();
setInterval(showState, 500); // the reconnect after a rename (or a DUP refusal) shows up here
