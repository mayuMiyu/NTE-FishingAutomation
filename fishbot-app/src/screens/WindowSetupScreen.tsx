import { useEffect, useState } from "react";
import { useNavigate } from "react-router";
import { motion, AnimatePresence } from "motion/react";
import { Fish, Search, CheckCircle2, MonitorX, RefreshCw } from "lucide-react";
import { useTheme } from "../context/themeContext";
import { useFishbot } from "../context/fishbotContext";
import type { GameWindowInfo } from "../lib/fishbotBridge";

export function WindowSetupScreen() {
  const navigate = useNavigate();
  const { theme } = useTheme();
  const isMinimal = theme === "minimal";
  const { gameWindow, windowSearching, windowSearchDone, searchForNte, selectWindow, listWindows } =
    useFishbot();

  const [manualList, setManualList] = useState<GameWindowInfo[] | null>(null);
  const [loadingList, setLoadingList] = useState(false);

  // Auto-search for "NTE" on mount. Manual picker only appears if this fails.
  useEffect(() => {
    searchForNte();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const needsManualPick = windowSearchDone && !windowSearching && !gameWindow;

  useEffect(() => {
    if (needsManualPick && manualList === null) {
      setLoadingList(true);
      listWindows()
        .then(setManualList)
        .finally(() => setLoadingList(false));
    }
  }, [needsManualPick, manualList, listWindows]);

  const confirmed = gameWindow !== null;

  return (
    <div className="flex-1 flex flex-col p-6 h-full max-h-full overflow-hidden relative z-10 items-center justify-center text-center">
      {!isMinimal && (
        <motion.div
          initial={{ scale: 0 }}
          animate={{ scale: 1 }}
          transition={{ type: "spring", bounce: 0.6 }}
          className="w-16 h-16 bg-white rounded-full mx-auto mb-5 flex items-center justify-center shadow-md shadow-pink-200"
        >
          <Fish className="w-8 h-8 text-pink-400" />
        </motion.div>
      )}

      <h1 className={`text-xl font-semibold mb-1 tracking-tight ${isMinimal ? "text-white" : "text-purple-800 font-bold"}`}>
        Fishbot Setup
      </h1>
      <p className={`text-sm mb-6 ${isMinimal ? "text-neutral-400" : "text-pink-600 font-medium"}`}>
        Looking for your game window
      </p>

      <AnimatePresence mode="wait">
        {windowSearching && (
          <motion.div
            key="searching"
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            className="flex flex-col items-center gap-3"
          >
            <motion.div
              animate={{ rotate: 360 }}
              transition={{ repeat: Infinity, duration: 1.1, ease: "linear" }}
              className={isMinimal ? "text-neutral-400" : "text-pink-400"}
            >
              <Search className="w-6 h-6" />
            </motion.div>
            <p className={`text-sm font-medium ${isMinimal ? "text-neutral-300" : "text-purple-700"}`}>
              Searching for "NTE"...
            </p>
          </motion.div>
        )}

        {confirmed && !windowSearching && (
          <motion.div
            key="found"
            initial={{ opacity: 0, y: 6 }}
            animate={{ opacity: 1, y: 0 }}
            className="w-full flex flex-col items-center gap-4"
          >
            <div
              className={`w-full flex items-center gap-3 px-4 py-3 ${
                isMinimal
                  ? "bg-neutral-900/50 border border-neutral-800 rounded-xl"
                  : "bg-white/80 border border-pink-100 rounded-2xl shadow-sm"
              }`}
            >
              <CheckCircle2 className={`w-5 h-5 shrink-0 ${isMinimal ? "text-emerald-500" : "text-green-500"}`} />
              <div className="text-left overflow-hidden">
                <p className={`text-xs ${isMinimal ? "text-neutral-500" : "text-purple-400"}`}>Connected to</p>
                <p className={`text-sm font-medium truncate ${isMinimal ? "text-neutral-100" : "text-purple-800"}`}>
                  {gameWindow?.title}
                </p>
              </div>
            </div>

            <motion.button
              whileHover={{ scale: 1.02 }}
              whileTap={{ scale: 0.98 }}
              onClick={() => navigate("/dashboard")}
              className={`w-full font-semibold text-sm py-3 flex items-center justify-center transition-all ${
                isMinimal
                  ? "bg-white text-black hover:bg-neutral-200 rounded-xl"
                  : "bg-gradient-to-r from-pink-400 to-purple-400 text-white rounded-full shadow-lg shadow-pink-300/50"
              }`}
            >
              Continue
            </motion.button>

            <button
              onClick={() => {
                setManualList(null);
                selectWindow(gameWindow!).then(() => {});
                // Force manual list open even though NTE was found, in case it's the wrong window.
                setLoadingList(true);
                listWindows()
                  .then(setManualList)
                  .finally(() => setLoadingList(false));
              }}
              className={`text-xs underline ${isMinimal ? "text-neutral-500 hover:text-neutral-300" : "text-pink-400 hover:text-pink-500"}`}
            >
              Not the right window? Choose manually
            </button>
          </motion.div>
        )}

        {needsManualPick && (
          <motion.div key="manual" initial={{ opacity: 0, y: 6 }} animate={{ opacity: 1, y: 0 }} className="w-full flex flex-col gap-3">
            <div
              className={`w-full flex items-center gap-3 px-4 py-3 mb-1 ${
                isMinimal
                  ? "bg-neutral-900/50 border border-neutral-800 rounded-xl"
                  : "bg-white/80 border border-pink-100 rounded-2xl shadow-sm"
              }`}
            >
              <MonitorX className={`w-5 h-5 shrink-0 ${isMinimal ? "text-red-500" : "text-pink-500"}`} />
              <p className={`text-sm text-left ${isMinimal ? "text-neutral-300" : "text-purple-700"}`}>
                Couldn't find "NTE" automatically. Pick your game window below.
              </p>
            </div>

            <div className="max-h-56 overflow-y-auto flex flex-col gap-2 pr-1">
              {loadingList && (
                <p className={`text-xs py-4 ${isMinimal ? "text-neutral-500" : "text-pink-400"}`}>Loading open windows...</p>
              )}
              {manualList?.map((w) => (
                <button
                  key={w.hwnd}
                  onClick={() => selectWindow(w).then(() => navigate("/dashboard"))}
                  className={`text-left px-4 py-2.5 text-sm font-medium transition-colors ${
                    isMinimal
                      ? "bg-neutral-900/40 border border-neutral-800/70 rounded-lg text-neutral-200 hover:border-neutral-600"
                      : "bg-white border border-pink-100 rounded-xl text-purple-700 hover:border-pink-300 shadow-sm"
                  }`}
                >
                  {w.title}
                </button>
              ))}
            </div>

            <button
              onClick={() => {
                setManualList(null);
                searchForNte();
              }}
              className={`mt-1 flex items-center justify-center gap-1.5 text-xs font-medium py-2 ${
                isMinimal ? "text-neutral-400 hover:text-neutral-200" : "text-pink-500 hover:text-pink-600"
              }`}
            >
              <RefreshCw className="w-3.5 h-3.5" /> Search again
            </button>
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  );
}
