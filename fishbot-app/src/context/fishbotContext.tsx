import { createContext, useCallback, useContext, useEffect, useRef, useState } from "react";
import {
  DEFAULT_CONFIG,
  IDLE_STATUS,
  getFishbotBridge,
  type FishbotConfig,
  type GameWindowInfo,
  type LiveStatus,
} from "../lib/fishbotBridge";

const NTE_HINT = "NTE";

interface FishbotContextType {
  config: FishbotConfig;
  updateConfig: (patch: Partial<FishbotConfig>) => Promise<void>;

  status: LiveStatus;

  gameWindow: GameWindowInfo | null;
  windowSearching: boolean;
  /** True once auto-search for NTE has finished (found or not). */
  windowSearchDone: boolean;
  searchForNte: () => Promise<void>;
  selectWindow: (info: GameWindowInfo) => Promise<void>;
  listWindows: () => Promise<GameWindowInfo[]>;

  start: () => Promise<void>;
  stop: () => Promise<void>;

  calibrateBar: () => Promise<boolean>;
  calibrateFButton: () => Promise<boolean>;

  isAdmin: boolean;
  relaunchAsAdmin: () => Promise<void>;
}

const FishbotContext = createContext<FishbotContextType | null>(null);

export function FishbotProvider({ children }: { children: React.ReactNode }) {
  const bridge = useRef(getFishbotBridge());
  const [config, setConfig] = useState<FishbotConfig>(DEFAULT_CONFIG);
  const [status, setStatus] = useState<LiveStatus>(IDLE_STATUS);
  const [gameWindow, setGameWindow] = useState<GameWindowInfo | null>(null);
  const [windowSearching, setWindowSearching] = useState(false);
  const [windowSearchDone, setWindowSearchDone] = useState(false);
  const [isAdmin, setIsAdmin] = useState(false);

  useEffect(() => {
    bridge.current.getConfig().then(setConfig);
    bridge.current.isAdmin().then(setIsAdmin);
    const unsub = bridge.current.onStatus(setStatus);
    return unsub;
  }, []);

  const updateConfig = useCallback(async (patch: Partial<FishbotConfig>) => {
    const next = await bridge.current.setConfig(patch);
    setConfig(next);
  }, []);

  const searchForNte = useCallback(async () => {
    setWindowSearching(true);
    setWindowSearchDone(false);
    const found = await bridge.current.findWindow(NTE_HINT);
    if (found) {
      setGameWindow(found);
      await updateConfig({ window_title: found.title });
    }
    setWindowSearching(false);
    setWindowSearchDone(true);
  }, [updateConfig]);

  const selectWindow = useCallback(
    async (info: GameWindowInfo) => {
      setGameWindow(info);
      await updateConfig({ window_title: info.title });
    },
    [updateConfig]
  );

  const listWindows = useCallback(() => bridge.current.listWindows(), []);

  const start = useCallback(() => bridge.current.start(), []);
  const stop = useCallback(() => bridge.current.stop(), []);

  const calibrateBar = useCallback(async () => {
    const result = await bridge.current.calibrateBar();
    if (!result) return false;
    await updateConfig({ bar: result.bar, fish: result.fish, rod: result.rod });
    return true;
  }, [updateConfig]);

  const calibrateFButton = useCallback(async () => {
    const fbtn = await bridge.current.calibrateFButton();
    if (!fbtn) return false;
    await updateConfig({ fbtn });
    return true;
  }, [updateConfig]);

  const relaunchAsAdmin = useCallback(() => bridge.current.relaunchAsAdmin(), []);

  return (
    <FishbotContext.Provider
      value={{
        config,
        updateConfig,
        status,
        gameWindow,
        windowSearching,
        windowSearchDone,
        searchForNte,
        selectWindow,
        listWindows,
        start,
        stop,
        calibrateBar,
        calibrateFButton,
        isAdmin,
        relaunchAsAdmin,
      }}
    >
      {children}
    </FishbotContext.Provider>
  );
}

export function useFishbot() {
  const ctx = useContext(FishbotContext);
  if (!ctx) throw new Error("useFishbot must be used inside <FishbotProvider>");
  return ctx;
}
