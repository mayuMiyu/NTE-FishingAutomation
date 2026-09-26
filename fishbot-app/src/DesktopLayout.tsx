import { Outlet, useLocation } from "react-router";
import { motion } from "motion/react";
import { Minus, Square, X, Fish, Waves } from "lucide-react";
import { useTheme } from "./context/themeContext";

export function DesktopLayout() {
  const location = useLocation();
  const { theme } = useTheme();
  const isMinimal = theme === "minimal";

  return (
    <div className={`min-h-screen flex items-center justify-center p-4 transition-colors duration-500 ${
      isMinimal ? "bg-neutral-900 text-neutral-200" : "bg-[#fce7f3] text-purple-900"
    }`}>
      <div className={`w-[400px] h-[600px] rounded-xl shadow-2xl overflow-hidden flex flex-col relative ring-1 transition-all duration-500 ${
        isMinimal
          ? "bg-[#0A0A0A] border border-neutral-800 ring-white/5"
          : "bg-[#fff0f5] border-[3px] border-pink-200 ring-pink-300/30 shadow-[0_10px_50px_rgba(244,114,182,0.25)]"
      }`}>

        <div className={`h-10 flex items-center justify-between px-4 select-none z-50 ${
          isMinimal ? "bg-[#0A0A0A] border-b border-neutral-800/50" : "bg-white/80 backdrop-blur-md border-b-2 border-pink-100"
        }`}>
          <div className={`text-xs font-medium tracking-wide flex items-center gap-2 ${
            isMinimal ? "text-neutral-400" : "text-purple-600 font-bold"
          }`}>
            {!isMinimal && <Fish className="w-3.5 h-3.5 text-pink-400" />}
            Fishbot
          </div>
          <div className={`flex items-center gap-4 ${isMinimal ? "text-neutral-500" : "text-pink-300"}`}>
            <Minus className="w-4 h-4 cursor-pointer hover:text-neutral-200" />
            <Square className="w-3.5 h-3.5 cursor-pointer hover:text-neutral-200" />
            <X className="w-4 h-4 cursor-pointer hover:text-red-500" />
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
    </div>
  );
}
