import { useNavigate } from "react-router";
import { useEffect, useState } from "react";
import { motion, AnimatePresence } from "motion/react";
import { Settings, Play, Square, Activity, Sparkles, Heart, Palette, Fish, AlertTriangle } from "lucide-react";
import { useTheme } from "../context/themeContext";
import { useFishbot } from "../context/fishbotContext";
import type { BotState } from "../lib/fishbotBridge";

const STATE_LABEL: Record<BotState, string> = {
  NONE: "No target",
  IDLE: "Idle (ready to cast)",
  HOOKED: "Fish on hook!",
  RESULT: "Catch result",
  MINIGAME: "Reeling in...",
};

export function DashboardScreen() {
  const navigate = useNavigate();
  const { theme, toggleTheme } = useTheme();
  const isMinimal = theme === "minimal";
  const { config, status, gameWindow, start, stop } = useFishbot();

  const [events, setEvents] = useState<{ id: number; time: string; text: string }[]>([]);
  const lastState = useState<{ current: BotState | null }>({ current: null })[0];

  // Build a small local event log from state transitions in the status stream.
  useEffect(() => {
    if (status.state !== lastState.current && status.armed) {
      lastState.current = status.state;
      if (status.state === "HOOKED" || status.state === "RESULT" || status.state === "MINIGAME") {
        setEvents((prev) =>
          [
            {
              id: Date.now(),
              time: new Date().toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" }),
              text:
                status.state === "MINIGAME"
                  ? "Started reeling"
                  : status.state === "HOOKED"
                  ? "Fish hooked"
                  : "Catch resolved",
            },
            ...prev,
          ].slice(0, 6)
        );
      }
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [status.state, status.armed]);

  const isRunning = status.armed;

  return (
    <div className="flex-1 flex flex-col p-6 h-full max-h-full overflow-hidden relative z-10">
      <div className="flex items-center justify-between mb-4">
        <h1 className={`text-xl font-semibold tracking-tight flex items-center gap-2 ${isMinimal ? "text-white" : "text-purple-800 font-bold"}`}>
          Fishbot {!isMinimal && <Sparkles className="w-5 h-5 text-pink-400" />}
        </h1>
        <div className="flex items-center gap-2">
          <motion.button
            whileHover={{ scale: 1.1, rotate: 15 }}
            whileTap={{ scale: 0.9 }}
            onClick={toggleTheme}
            className={`w-8 h-8 rounded-lg flex items-center justify-center transition-colors ${
              isMinimal ? "hover:bg-neutral-800 text-neutral-400" : "bg-white shadow-sm shadow-pink-200 text-pink-500 hover:bg-pink-50"
            }`}
          >
            {isMinimal ? <Palette className="w-4 h-4" /> : <Heart className="w-4 h-4 fill-pink-500" />}
          </motion.button>
          <motion.button
            whileHover={{ rotate: 90 }}
            whileTap={{ scale: 0.9 }}
            onClick={() => navigate("/settings")}
            className={`w-8 h-8 rounded-lg flex items-center justify-center transition-colors ${
              isMinimal ? "hover:bg-neutral-800 text-neutral-400" : "bg-white shadow-sm shadow-pink-200 text-purple-500 hover:bg-purple-50"
            }`}
          >
            <Settings className="w-4 h-4" />
          </motion.button>
        </div>
      </div>

      <button
        onClick={() => navigate("/setup")}
        className={`flex items-center gap-2 mb-4 px-3 py-1.5 rounded-lg text-xs font-medium self-start transition-colors ${
          isMinimal ? "bg-neutral-900/50 border border-neutral-800 text-neutral-400 hover:border-neutral-600" : "bg-white/80 border border-pink-100 text-purple-500 hover:border-pink-300"
        }`}
        title="Change game window"
      >
        <Fish className="w-3.5 h-3.5" />
        {gameWindow?.title ?? "No window selected"}
      </button>

      <div className="flex flex-col items-center justify-center py-2">
        <div className={`flex items-center gap-2 mb-4 px-4 py-1.5 rounded-full ${isMinimal ? "" : isRunning ? "bg-green-100" : "bg-pink-100"}`}>
          <div
            className={`w-2 h-2 rounded-full ${
              isRunning ? (isMinimal ? "bg-emerald-500 animate-pulse" : "bg-green-500 animate-pulse") : isMinimal ? "bg-red-500" : "bg-pink-500"
            }`}
          />
          <span className={`text-sm font-medium ${isRunning ? (isMinimal ? "text-emerald-500" : "text-green-600") : isMinimal ? "text-red-500" : "text-pink-600"}`}>
            {isRunning ? STATE_LABEL[status.state] : "Stopped"}
          </span>
        </div>

        <motion.button
          whileHover={{ scale: 1.05 }}
          whileTap={{ scale: 0.95 }}
          onClick={() => (isRunning ? stop() : start())}
          disabled={!gameWindow}
          className={`w-32 h-32 flex flex-col items-center justify-center gap-2 transition-all duration-300 relative overflow-hidden disabled:opacity-40 ${
            isMinimal
              ? `rounded-full border ${isRunning ? "bg-neutral-900/50 border-emerald-500/30 text-emerald-500 shadow-[0_0_30px_rgba(16,185,129,0.1)]" : "bg-neutral-900 border-neutral-800 text-neutral-300"}`
              : `rounded-full border-1 border-purple-500 shadow-xl ${isRunning ? "bg-gradient-to-br from-green-100 to-emerald-100 text-green-700 shadow-green-200/50" : "bg-gradient-to-br from-pink-100 to-purple-100 text-purple-700 shadow-pink-200/50"}`
          }`}
        >
          <AnimatePresence mode="wait">
            <motion.div
              key={isRunning ? "running" : "stopped"}
              initial={{ scale: 0.8, opacity: 0 }}
              animate={{ scale: 1, opacity: 1 }}
              exit={{ scale: 0.8, opacity: 0 }}
              transition={{ duration: 0.15 }}
              className="flex flex-col items-center gap-2"
            >
              {isRunning ? (
                <Square className={`w-8 h-8 ${isMinimal ? "fill-emerald-500/20" : "fill-green-600/20"}`} />
              ) : (
                <Play className={`w-8 h-8 ml-1 ${isMinimal ? "fill-neutral-300/20" : "fill-purple-600/20"}`} />
              )}
              <span className="font-bold text-xs tracking-wider uppercase">{isRunning ? "Stop" : "Start"}</span>
            </motion.div>
          </AnimatePresence>
        </motion.button>
        <p className={`text-[10px] mt-2 font-medium ${isMinimal ? "text-neutral-600" : "text-purple-400"}`}>Hotkey: F8</p>
      </div>

      {/* Live diagnostics */}
      <div className={`px-3 py-2.5 mb-3 text-xs space-y-1 ${isMinimal ? "bg-neutral-900/40 border border-neutral-800/50 rounded-lg" : "bg-white/80 border border-pink-100 rounded-2xl shadow-sm"}`}>
        <div className="flex justify-between">
          <span className={isMinimal ? "text-neutral-500" : "text-purple-400"}>Bar</span>
          <span className={isMinimal ? "text-neutral-300" : "text-purple-700"}>
            fish {status.barFound.fish ? "found" : "-"} &nbsp; rod {status.barFound.rod ? "found" : "-"}
          </span>
        </div>
        <div className="flex justify-between">
          <span className={isMinimal ? "text-neutral-500" : "text-purple-400"}>err / key</span>
          <span className={isMinimal ? "text-neutral-300" : "text-purple-700"}>
            {status.err !== null ? `${status.err > 0 ? "+" : ""}${status.err}px` : "-"} &nbsp; {status.heldKey ? `key ${status.heldKey}` : "none"}
          </span>
        </div>
        <div className="flex justify-between">
          <span className={isMinimal ? "text-neutral-500" : "text-purple-400"}>loops/s</span>
          <span className={isMinimal ? "text-neutral-300" : "text-purple-700"}>{status.loopsPerSec}</span>
        </div>
        {status.ratios && (
          <div className="flex justify-between">
            <span className={isMinimal ? "text-neutral-500" : "text-purple-400"}>F ratios</span>
            <span className={isMinimal ? "text-neutral-300" : "text-purple-700"}>
              blue {status.ratios.blue.toFixed(3)} &nbsp; grey {status.ratios.grey.toFixed(3)} &nbsp; white {status.ratios.white.toFixed(3)}
            </span>
          </div>
        )}
        {status.message && (
          <div className={`flex items-center gap-1.5 pt-1 ${isMinimal ? "text-amber-500" : "text-pink-500"}`}>
            <AlertTriangle className="w-3 h-3" /> {status.message}
          </div>
        )}
      </div>

      <div className="mt-1 flex-1 min-h-0">
        <div className="flex items-center gap-2 mb-3">
          <Activity className={`w-4 h-4 ${isMinimal ? "text-neutral-500" : "text-purple-400"}`} />
          <h2 className={`text-xs font-semibold uppercase tracking-wider ${isMinimal ? "text-neutral-400" : "text-purple-500"}`}>Recent Events</h2>
        </div>
        <div className="space-y-2 overflow-y-auto max-h-40">
          {events.length === 0 && <p className={`text-xs ${isMinimal ? "text-neutral-600" : "text-pink-300"}`}>Nothing yet - start the bot to see activity.</p>}
          {events.map((log, i) => (
            <motion.div
              key={log.id}
              initial={{ opacity: 0, x: -5 }}
              animate={{ opacity: 1, x: 0 }}
              transition={{ delay: 0.03 * i }}
              className={`px-4 py-2.5 flex items-center justify-between ${
                isMinimal ? "bg-neutral-900/40 border border-neutral-800/50 rounded-lg" : "bg-white/80 backdrop-blur-sm shadow-sm border border-pink-100 rounded-2xl"
              }`}
            >
              <span className={`text-sm font-medium ${isMinimal ? "text-neutral-300" : "text-purple-800"}`}>{log.text}</span>
              <span className={`text-xs font-medium ${isMinimal ? "text-neutral-500" : "text-pink-400"}`}>{log.time}</span>
            </motion.div>
          ))}
        </div>
      </div>

      <div className="text-center pt-2 mt-auto">
        <p className={`text-xs font-medium ${isMinimal ? "text-neutral-600" : "text-purple-400"}`}>
          Deadzone {config.deadzone.toFixed(2)} &middot; Lead {config.lead.toFixed(2)}s
        </p>
      </div>
    </div>
  );
}
