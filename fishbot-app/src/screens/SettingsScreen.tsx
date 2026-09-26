import { useNavigate } from "react-router";
import { useState } from "react";
import { motion } from "motion/react";
import { ArrowLeft, ShieldAlert, Crosshair, Target, RotateCcw } from "lucide-react";
import { useTheme } from "../context/themeContext";
import { useFishbot } from "../context/fishbotContext";
import type { FButtonState } from "../lib/fishbotBridge";
import { DEFAULT_CONFIG } from "../lib/fishbotBridge";

const STATE_ROWS: { key: FButtonState; label: string }[] = [
  { key: "IDLE", label: "Idle (before fishing)" },
  { key: "HOOKED", label: "Hooked (blue ring)" },
  { key: "RESULT", label: "Result (grey disc)" },
];

export function SettingsScreen() {
  const navigate = useNavigate();
  const { theme } = useTheme();
  const isMinimal = theme === "minimal";
  const { config, updateConfig, calibrateBar, calibrateFButton, isAdmin, relaunchAsAdmin } = useFishbot();

  const [calibratingBar, setCalibratingBar] = useState(false);
  const [calibratingFbtn, setCalibratingFbtn] = useState(false);

  const cardCls = isMinimal ? "bg-neutral-900/50 border border-neutral-800 rounded-xl" : "bg-white/80 border border-pink-100 rounded-2xl shadow-sm";
  const sectionLabel = isMinimal ? "text-neutral-400" : "text-purple-500";
  const valueCls = isMinimal ? "text-neutral-200" : "text-purple-700";

  const runCalibrateBar = async () => {
    setCalibratingBar(true);
    await calibrateBar();
    setCalibratingBar(false);
  };
  const runCalibrateFbtn = async () => {
    setCalibratingFbtn(true);
    await calibrateFButton();
    setCalibratingFbtn(false);
  };

  return (
    <div className="flex-1 flex flex-col p-6 h-full max-h-full overflow-hidden relative z-10">
      <div className="flex items-center gap-3 mb-4">
        <motion.button
          whileHover={{ x: -2 }}
          whileTap={{ scale: 0.95 }}
          onClick={() => navigate("/dashboard")}
          className={`w-8 h-8 rounded-lg flex items-center justify-center transition-colors ${
            isMinimal ? "hover:bg-neutral-800 text-neutral-400" : "bg-white shadow-sm shadow-pink-200 text-pink-500 hover:bg-pink-50"
          }`}
        >
          <ArrowLeft className="w-4 h-4" />
        </motion.button>
        <h1 className={`text-xl font-semibold tracking-tight ${isMinimal ? "text-white" : "text-purple-800 font-bold"}`}>Settings</h1>
      </div>

      <div className="flex-1 overflow-y-auto space-y-4 pb-2 pr-1">
        {/* UIPI / admin warning - see handoff §5.4 and §7 */}
        {!isAdmin && (
          <div className={`px-4 py-3 flex items-start gap-3 ${isMinimal ? "bg-amber-500/10 border border-amber-500/30 rounded-xl" : "bg-amber-50 border border-amber-200 rounded-2xl"}`}>
            <ShieldAlert className="w-4 h-4 text-amber-500 shrink-0 mt-0.5" />
            <div className="flex-1">
              <p className={`text-xs font-medium ${isMinimal ? "text-amber-400" : "text-amber-700"}`}>Not running as administrator</p>
              <p className={`text-[11px] mt-0.5 ${isMinimal ? "text-neutral-400" : "text-amber-600/80"}`}>
                If the game runs elevated, Windows will silently drop injected keys. Relaunch elevated if the rod doesn't respond.
              </p>
              <button
                onClick={relaunchAsAdmin}
                className={`mt-2 text-xs font-semibold px-3 py-1.5 rounded-lg ${isMinimal ? "bg-amber-500/20 text-amber-300 hover:bg-amber-500/30" : "bg-amber-200 text-amber-800 hover:bg-amber-300"}`}
              >
                Relaunch as Administrator
              </button>
            </div>
          </div>
        )}

        {/* Calibration */}
        <div className={`p-4 ${cardCls}`}>
          <p className={`text-xs font-semibold uppercase tracking-wider mb-3 ${sectionLabel}`}>Calibration</p>
          <div className="space-y-2">
            <button
              onClick={runCalibrateBar}
              disabled={calibratingBar}
              className={`w-full flex items-center gap-2 justify-center px-3 py-2.5 text-sm font-medium rounded-lg transition-colors disabled:opacity-50 ${
                isMinimal ? "bg-neutral-800 text-neutral-100 hover:bg-neutral-700" : "bg-pink-100 text-purple-700 hover:bg-pink-200"
              }`}
            >
              <Target className="w-4 h-4" /> {calibratingBar ? "Waiting for selection..." : "Calibrate Fish Bar & Colors"}
            </button>
            <button
              onClick={runCalibrateFbtn}
              disabled={calibratingFbtn}
              className={`w-full flex items-center gap-2 justify-center px-3 py-2.5 text-sm font-medium rounded-lg transition-colors disabled:opacity-50 ${
                isMinimal ? "bg-neutral-800 text-neutral-100 hover:bg-neutral-700" : "bg-pink-100 text-purple-700 hover:bg-pink-200"
              }`}
            >
              <Crosshair className="w-4 h-4" /> {calibratingFbtn ? "Waiting for selection..." : "Calibrate F Button"}
            </button>
          </div>
          <div className="flex gap-3 mt-3 text-[11px]">
            <span className={config.fish ? valueCls : isMinimal ? "text-neutral-600" : "text-pink-300"}>
              fish {config.fish ? config.fish.hex : "not set"}
            </span>
            <span className={config.rod ? valueCls : isMinimal ? "text-neutral-600" : "text-pink-300"}>
              rod {config.rod ? config.rod.hex : "not set"}
            </span>
            <span className={config.fbtn ? valueCls : isMinimal ? "text-neutral-600" : "text-pink-300"}>
              F-button {config.fbtn ? "set" : "not set"}
            </span>
          </div>
        </div>

        {/* Steering */}
        <div className={`p-4 ${cardCls}`}>
          <p className={`text-xs font-semibold uppercase tracking-wider mb-3 ${sectionLabel}`}>Steering</p>

          <SliderRow
            label="Deadzone"
            value={config.deadzone}
            min={0.1}
            max={0.4}
            step={0.01}
            format={(v) => v.toFixed(2)}
            isMinimal={isMinimal}
            onChange={(v) => updateConfig({ deadzone: v })}
          />
          <SliderRow
            label="Lead (overshoot prediction)"
            value={config.lead}
            min={0}
            max={0.3}
            step={0.01}
            format={(v) => `${v.toFixed(2)}s`}
            isMinimal={isMinimal}
            onChange={(v) => updateConfig({ lead: v })}
          />

          <div className="flex items-center justify-between mt-3">
            <span className={`text-sm font-medium ${valueCls}`}>Invert A / D</span>
            <ToggleSwitch checked={config.invert_ad} isMinimal={isMinimal} onChange={(v) => updateConfig({ invert_ad: v })} />
          </div>
        </div>

        {/* F-button thresholds */}
        <div className={`p-4 ${cardCls}`}>
          <p className={`text-xs font-semibold uppercase tracking-wider mb-3 ${sectionLabel}`}>F-Button</p>

          {STATE_ROWS.map((row) => (
            <div key={row.key} className="flex items-center justify-between py-1.5">
              <span className={`text-sm font-medium ${valueCls}`}>{row.label}</span>
              <ToggleSwitch
                checked={config.act[row.key]}
                isMinimal={isMinimal}
                onChange={(v) => updateConfig({ act: { ...config.act, [row.key]: v } })}
              />
            </div>
          ))}

          <div className="mt-2 space-y-2">
            <SliderRow label="Blue min" value={config.blue_min} min={0} max={0.15} step={0.005} format={(v) => v.toFixed(3)} isMinimal={isMinimal} onChange={(v) => updateConfig({ blue_min: v })} />
            <SliderRow label="Grey min" value={config.grey_min} min={0} max={0.2} step={0.005} format={(v) => v.toFixed(3)} isMinimal={isMinimal} onChange={(v) => updateConfig({ grey_min: v })} />
            <SliderRow label="White min" value={config.white_min} min={0} max={0.05} step={0.001} format={(v) => v.toFixed(3)} isMinimal={isMinimal} onChange={(v) => updateConfig({ white_min: v })} />
            <SliderRow label="Min gap between presses" value={config.f_min_gap} min={0.1} max={2} step={0.1} format={(v) => `${v.toFixed(1)}s`} isMinimal={isMinimal} onChange={(v) => updateConfig({ f_min_gap: v })} />
            <SliderRow label="Repeat while held (0 = once)" value={config.f_repeat} min={0} max={3} step={0.1} format={(v) => (v === 0 ? "off" : `${v.toFixed(1)}s`)} isMinimal={isMinimal} onChange={(v) => updateConfig({ f_repeat: v })} />
          </div>
        </div>

        {/* Debug */}
        <div className={`p-4 flex items-center justify-between ${cardCls}`}>
          <span className={`text-sm font-medium ${valueCls}`}>Debug preview window</span>
          <ToggleSwitch checked={config.debug_preview} isMinimal={isMinimal} onChange={(v) => updateConfig({ debug_preview: v })} />
        </div>

        <motion.button
          whileHover={{ scale: 1.01 }}
          whileTap={{ scale: 0.98 }}
          onClick={() => updateConfig(DEFAULT_CONFIG)}
          className={`w-full font-medium text-sm py-3 flex items-center justify-center gap-2 transition-colors ${
            isMinimal ? "border border-red-500/30 text-red-500/90 hover:text-red-500 rounded-xl" : "border-2 border-pink-300 text-pink-500 bg-white rounded-full shadow-sm hover:shadow-md"
          }`}
        >
          <RotateCcw className="w-4 h-4" /> Reset to Defaults
        </motion.button>
      </div>
    </div>
  );
}

function SliderRow({
  label,
  value,
  min,
  max,
  step,
  format,
  isMinimal,
  onChange,
}: {
  label: string;
  value: number;
  min: number;
  max: number;
  step: number;
  format: (v: number) => string;
  isMinimal: boolean;
  onChange: (v: number) => void;
}) {
  return (
    <div className="py-1.5">
      <div className="flex items-center justify-between mb-1.5">
        <span className={`text-xs font-medium ${isMinimal ? "text-neutral-300" : "text-purple-700"}`}>{label}</span>
        <span className={`text-[11px] font-medium px-1.5 py-0.5 rounded ${isMinimal ? "bg-neutral-800 text-neutral-400" : "bg-pink-50 text-pink-500"}`}>
          {format(value)}
        </span>
      </div>
      <input
        type="range"
        min={min}
        max={max}
        step={step}
        value={value}
        onChange={(e) => onChange(parseFloat(e.target.value))}
        className={`w-full h-1.5 rounded-full appearance-none cursor-pointer ${isMinimal ? "accent-neutral-300 bg-neutral-800" : "accent-pink-400 bg-pink-100"}`}
      />
    </div>
  );
}

function ToggleSwitch({ checked, isMinimal, onChange }: { checked: boolean; isMinimal: boolean; onChange: (v: boolean) => void }) {
  return (
    <button
      onClick={() => onChange(!checked)}
      className={`w-12 h-7 rounded-full p-1 transition-colors duration-300 shadow-inner ${
        isMinimal ? (checked ? "bg-white" : "bg-neutral-800 border border-neutral-700") : checked ? "bg-pink-400" : "bg-pink-100"
      }`}
    >
      <motion.div
        layout
        animate={{ x: checked ? 20 : 0 }}
        transition={{ type: "spring", stiffness: 500, damping: 30 }}
        className={`w-5 h-5 rounded-full shadow-sm ${isMinimal ? (checked ? "bg-black" : "bg-neutral-400") : "bg-white"}`}
      />
    </button>
  );
}
