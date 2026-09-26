import type {
  FishbotBridge,
  FishbotConfig,
  GameWindowInfo,
  LiveStatus,
  RegionFraction,
  ColorCalibration,
} from "./fishbotBridge";

export function installPywebviewBridge(timeoutMs = 1500): Promise<void> {
  return new Promise((resolve) => {
    if ((window as any).pywebview?.api) {
      window.fishbot = buildBridge();
      resolve();
      return;
    }

    const onReady = () => {
      document.removeEventListener("pywebviewready", onReady);
      window.fishbot = buildBridge();
      resolve();
    };
    document.addEventListener("pywebviewready", onReady);

    // Not running inside pywebview at all (plain browser dev) - don't hang forever.
    setTimeout(() => {
      document.removeEventListener("pywebviewready", onReady);
      resolve();
    }, timeoutMs);
  });
}

function buildBridge(): FishbotBridge {
  const api = (window as any).pywebview.api;
  let statusListeners: ((s: LiveStatus) => void)[] = [];

  // Python calls this via window.evaluate_js(...) on its status-push thread.
  (window as any).__fishbotPushStatus = (status: LiveStatus) => {
    statusListeners.forEach((cb) => cb(status));
  };

  return {
    async findWindow(titleHint: string): Promise<GameWindowInfo | null> {
      return api.find_window(titleHint);
    },
    async listWindows(): Promise<GameWindowInfo[]> {
      return api.list_windows();
    },
    async getConfig(): Promise<FishbotConfig> {
      return api.get_config();
    },
    async setConfig(patch: Partial<FishbotConfig>): Promise<FishbotConfig> {
      return api.set_config(patch);
    },
    onStatus(cb: (status: LiveStatus) => void): () => void {
      statusListeners.push(cb);
      return () => {
        statusListeners = statusListeners.filter((l) => l !== cb);
      };
    },
    async start(): Promise<void> {
      await api.start();
    },
    async stop(): Promise<void> {
      await api.stop();
    },
    async calibrateBar(): Promise<{ bar: RegionFraction; fish: ColorCalibration; rod: ColorCalibration } | null> {
      return api.calibrate_bar();
    },
    async calibrateFButton(): Promise<RegionFraction | null> {
      return api.calibrate_f_button();
    },
    async isAdmin(): Promise<boolean> {
      return api.is_admin();
    },
    async relaunchAsAdmin(): Promise<void> {
      await api.relaunch_as_admin();
    },
  };
}
