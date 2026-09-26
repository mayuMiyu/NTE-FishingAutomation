// Types mirror the Python-side JSON config (fishbot_gui_cfg.json) field-for-
// field (snake_case kept on purpose) so the two sides serialize without a
// translation layer. See FISHBOT_HANDOFF.md §2/§8 for the source of truth.


export type FButtonState = "IDLE" | "HOOKED" | "RESULT";
export type BotState = FButtonState | "MINIGAME" | "NONE";

export interface ColorCalibration {
  hex: string;
  lo: [number, number, number];
  hi: [number, number, number];
}

/** Region stored as a fraction of the game window's client rect (v2/v3 style). */
export interface RegionFraction {
  x: number;
  y: number;
  w: number;
  h: number;
}

export interface FishbotConfig {
  window_title: string; // "" = not yet resolved / primary monitor fallback
  bar: RegionFraction | null;
  fbtn: RegionFraction | null;
  fish: ColorCalibration | null;
  rod: ColorCalibration | null;

  steer: boolean;
  invert_ad: boolean;
  deadzone: number; // fraction of fish-bar width, recommended 0.10-0.25, capped 0.4
  lead: number; // seconds, overshoot prediction

  f_repeat: number; // 0 = press F once per state entry
  f_min_gap: number; // seconds between presses, default 0.6
  f_debounce: number; // seconds a state must hold before it counts, default 0.25
  blue_min: number;
  grey_min: number;
  white_min: number;
  act: Record<FButtonState, boolean>;

  debug_preview: boolean;
}

export const DEFAULT_CONFIG: FishbotConfig = {
  window_title: "",
  bar: null,
  fbtn: null,
  fish: null,
  rod: null,
  steer: true,
  invert_ad: false,
  deadzone: 0.15,
  lead: 0.08,
  f_repeat: 0,
  f_min_gap: 0.6,
  f_debounce: 0.25,
  blue_min: 0.02,
  grey_min: 0.06,
  white_min: 0.008,
  act: { IDLE: true, HOOKED: true, RESULT: true },
  debug_preview: false,
};

export interface GameWindowInfo {
  title: string;
  hwnd: number;
}

export interface LiveStatus {
  state: BotState;
  armed: boolean;
  barFound: { fish: boolean; rod: boolean };
  ratios: { blue: number; grey: number; white: number } | null;
  err: number | null;
  heldKey: "a" | "d" | null;
  loopsPerSec: number;
  message: string;
}

export const IDLE_STATUS: LiveStatus = {
  state: "NONE",
  armed: false,
  barFound: { fish: false, rod: false },
  ratios: null,
  err: null,
  heldKey: null,
  loopsPerSec: 0,
  message: "not connected",
};

/**
 * Contract expected of the native host (Python/pywebview, Tauri, or Electron
 * preload). The web UI never touches Win32/mss/pydirectinput directly - it
 * only talks to this bridge, which the host injects as `window.fishbot`.
 */
export interface FishbotBridge {
  /** Case-insensitive substring search, resolves null if nothing matches. */
  findWindow(titleHint: string): Promise<GameWindowInfo | null>;
  listWindows(): Promise<GameWindowInfo[]>;

  getConfig(): Promise<FishbotConfig>;
  setConfig(patch: Partial<FishbotConfig>): Promise<FishbotConfig>;

  /** Subscribes to the ~10Hz status stream; returns an unsubscribe fn. */
  onStatus(cb: (status: LiveStatus) => void): () => void;

  start(): Promise<void>;
  stop(): Promise<void>;

  /** Opens the native selectROI + eyedropper flow for the fish/rod bar. */
  calibrateBar(): Promise<{ bar: RegionFraction; fish: ColorCalibration; rod: ColorCalibration } | null>;
  /** Opens the native selectROI flow for the F-button circle. */
  calibrateFButton(): Promise<RegionFraction | null>;

  isAdmin(): Promise<boolean>;
  relaunchAsAdmin(): Promise<void>;
}

declare global {
  interface Window {
    fishbot?: FishbotBridge;
  }
}

/**
 * Fallback used when no native host has injected `window.fishbot` - lets the
 * UI be previewed in a plain browser. Simulates finding "NTE" after a short
 * delay and emits a slowly-cycling fake status stream once "started".
 */
function createMockBridge(): FishbotBridge {
  let config: FishbotConfig = { ...DEFAULT_CONFIG };
  let armed = false;
  let listeners: ((s: LiveStatus) => void)[] = [];
  let tick: ReturnType<typeof setInterval> | null = null;

  const emit = (s: LiveStatus) => listeners.forEach((cb) => cb(s));

  const cycle: BotState[] = ["NONE", "IDLE", "MINIGAME", "MINIGAME", "HOOKED", "RESULT"];
  let step = 0;

  return {
    async findWindow(titleHint) {
      await new Promise((r) => setTimeout(r, 900));
      // Mock always "finds" it so the happy path is previewable.
      return { title: `${titleHint} - Live`, hwnd: 123456 };
    },
    async listWindows() {
      return [
        { title: "NTE - Live", hwnd: 123456 },
        { title: "Discord", hwnd: 234567 },
        { title: "Google Chrome", hwnd: 345678 },
      ];
    },
    async getConfig() {
      return config;
    },
    async setConfig(patch) {
      config = { ...config, ...patch, act: { ...config.act, ...(patch.act ?? {}) } };
      return config;
    },
    onStatus(cb) {
      listeners.push(cb);
      if (!tick) {
        tick = setInterval(() => {
          if (!armed) {
            emit({ ...IDLE_STATUS, message: "stopped - detect only" });
            return;
          }
          step = (step + 1) % cycle.length;
          const state = cycle[step];
          emit({
            state,
            armed: true,
            barFound: { fish: state === "MINIGAME", rod: state === "MINIGAME" },
            ratios:
              state === "IDLE" || state === "HOOKED" || state === "RESULT"
                ? {
                    blue: state === "HOOKED" ? 0.041 : 0.003,
                    grey: state === "RESULT" ? 0.11 : 0.01,
                    white: state === "IDLE" ? 0.02 : 0.001,
                  }
                : null,
            err: state === "MINIGAME" ? Math.round((Math.random() - 0.5) * 300) : null,
            heldKey: state === "MINIGAME" ? (Math.random() > 0.5 ? "a" : "d") : null,
            loopsPerSec: 110 + Math.round(Math.random() * 20),
            message: "",
          });
        }, 700);
      }
      return () => {
        listeners = listeners.filter((l) => l !== cb);
      };
    },
    async start() {
      armed = true;
    },
    async stop() {
      armed = false;
      emit({ ...IDLE_STATUS, message: "stopped - detect only" });
    },
    async calibrateBar() {
      await new Promise((r) => setTimeout(r, 600));
      return {
        bar: { x: 0.32, y: 0.08, w: 0.36, h: 0.03 },
        fish: { hex: "#29C6AB", lo: [65, 30, 116], hi: [85, 170, 255] },
        rod: { hex: "#FEF7A4", lo: [22, 0, 195], hi: [38, 50, 255] },
      };
    },
    async calibrateFButton() {
      await new Promise((r) => setTimeout(r, 600));
      return { x: 0.86, y: 0.78, w: 0.08, h: 0.12 };
    },
    async isAdmin() {
      return false;
    },
    async relaunchAsAdmin() {
      // no-op in mock
    },
  };
}

let cached: FishbotBridge | null = null;

/** Returns the native bridge if the host injected one, else a mock for preview. */
export function getFishbotBridge(): FishbotBridge {
  if (window.fishbot) return window.fishbot;
  if (!cached) cached = createMockBridge();
  return cached;
}
