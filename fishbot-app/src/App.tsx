import { HashRouter, Routes, Route, Navigate } from "react-router";
import { ThemeProvider } from "./context/themeContext";
import { FishbotProvider } from "./context/fishbotContext";
import { DesktopLayout } from "./DesktopLayout";
import { WindowSetupScreen } from "./screens/WindowSetupScreen";
import { DashboardScreen } from "./screens/DashboardScreen";
import { SettingsScreen } from "./screens/SettingsScreen";

export default function App() {
  return (
    <ThemeProvider>
      <FishbotProvider>
        <HashRouter>
          <Routes>
            <Route element={<DesktopLayout />}>
              <Route path="/" element={<Navigate to="/setup" replace />} />
              <Route path="/setup" element={<WindowSetupScreen />} />
              <Route path="/dashboard" element={<DashboardScreen />} />
              <Route path="/settings" element={<SettingsScreen />} />
            </Route>
          </Routes>
        </HashRouter>
      </FishbotProvider>
    </ThemeProvider>
  );
}
