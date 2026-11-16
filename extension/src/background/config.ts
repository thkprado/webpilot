// Service worker: the config written by `webpilot setup`, this profile's name, and small shared helpers.

type Config = {
  token: string;
  port: number;
  mode: "real" | "temp";
  autoCaptcha?: boolean;
  blockedDomains?: string[];
  allowedDomains?: string[];
};
export type Args = Record<string, any>;

export let config: Config | null = null;

export const sleep = (ms: number) => new Promise((r) => setTimeout(r, ms));

/** Name this browser profile reports to the daemon; kept in storage.local, which is per profile. */
export async function profileName(): Promise<string> {
  const { profile } = await chrome.storage.local.get("profile");
  if (typeof profile === "string" && profile) return profile;
  const name = `profile-${crypto.randomUUID().slice(0, 4)}`;
  await chrome.storage.local.set({ profile: name });
  return name;
}

/** Reads dist/config.json again into `config`; null when it is missing. */
export async function reloadConfig(): Promise<Config | null> {
  config = await loadConfig();
  return config;
}

async function loadConfig(): Promise<Config | null> {
  try {
    const r = await fetch(chrome.runtime.getURL("config.json"), { cache: "no-store" });
    return r.ok ? await r.json() : null;
  } catch {
    return null;
  }
}
