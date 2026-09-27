import { Outlet, useLocation } from "react-router";
import { motion } from "motion/react";
import { Minus, Square, X, Fish, Waves } from "lucide-react";
import { useTheme } from "./context/themeContext";
import { getFishbotBridge } from "./lib/fishbotBridge";

export function DesktopLayout() {
  const location = useLocation();
  const { theme } = useTheme();
  const isMinimal = theme === "minimal";
  const nativeWindow = getFishbotBridge();

  return (
    <div className={`h-screen w-screen overflow-hidden flex flex-col transition-colors duration-500 ${
      isMinimal ? "bg-neutral-900 text-neutral-200" : "bg-[#fce7f3] text-purple-900"
    }`}>
        <div className={`pywebview-drag-region h-10 shrink-0 flex items-center justify-between px-4 select-none z-50 ${
          isMinimal ? "bg-[#0A0A0A] border-b border-neutral-800/50" : "bg-white/80 backdrop-blur-md border-b-2 border-pink-100"
        }`}>
          <div className={`text-xs font-medium tracking-wide flex items-center gap-2 ${
            isMinimal ? "text-neutral-400" : "text-purple-600 font-bold"
          }`}>
            {!isMinimal && <Fish className="w-3.5 h-3.5 text-pink-400" />}
            Fishbot
          </div>
          <div className={`flex items-center gap-4 ${isMinimal ? "text-neutral-500" : "text-pink-300"}`}>
            <button type="button" aria-label="Minimize" className="cursor-pointer hover:text-neutral-200" onClick={() => void nativeWindow.minimizeWindow()}><Minus className="w-4 h-4" /></button>
            <button type="button" aria-label="Maximize or restore" className="cursor-pointer hover:text-neutral-200" onClick={() => void nativeWindow.toggleMaximizeWindow()}><Square className="w-3.5 h-3.5" /></button>
            <button type="button" aria-label="Close" className="cursor-pointer hover:text-red-500" onClick={() => void nativeWindow.closeWindow()}><X className="w-4 h-4" /></button>
          </div>
        </div>

        <div className={`flex-1 relative overflow-hidden transition-colors duration-500 ${
          isMinimal ? "bg-[#0A0A0A]" : "bg-[#fff0f5]"
        }`}>
          {!isMinimal && (
            <div className="absolute inset-0 pointer-events-none overflow-hidden opacity-40 z-0">
              <Waves className="absolute top-12 -left-6 w-24 h-24 text-pink-200 rotate-12" />
              <Waves className="absolute bottom-32 -right-10 w-32 h-32 text-purple-200 -rotate-12" />
              <Fish className="absolute top-40 right-12 w-12 h-12 text-pink-200/60 rotate-45" />
              <Fish className="absolute bottom-20 left-16 w-10 h-10 text-purple-200/60 -rotate-12" />
            </div>
          )}

          <motion.div
            key={location.pathname}
            initial={{ opacity: 0, y: 5 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.2, ease: "easeOut" }}
            className="absolute inset-0 overflow-y-auto overflow-x-hidden flex flex-col z-10"
          >
            <Outlet />
          </motion.div>
        </div>
    </div>
  );
}
