import { Suspense, lazy } from "react";
import { HashRouter, Routes, Route } from "react-router-dom";
import { TooltipProvider } from "@/components/ui/tooltip";

// ---------------------------------------------------------------------------
// i18n initialization
// ---------------------------------------------------------------------------
import "./i18n/config";

// ---------------------------------------------------------------------------
// Layout
// ---------------------------------------------------------------------------
import { AppLayout } from "@/components/layout/AppLayout";

// ---------------------------------------------------------------------------
// Lazy-loaded route components
// ---------------------------------------------------------------------------
const GameHome = lazy(() =>
  import("./features/game-home").then((m) => ({ default: m.GameHome }))
);
const Versions = lazy(() =>
  import("./features/versions").then((m) => ({ default: m.Versions }))
);
const Plugins = lazy(() =>
  import("./features/plugins").then((m) => ({ default: m.Plugins }))
);
const OnlineMods = lazy(() =>
  import("./features/online-mods").then((m) => ({ default: m.OnlineMods }))
);
const Settings = lazy(() =>
  import("./features/settings").then((m) => ({ default: m.Settings }))
);

// ---------------------------------------------------------------------------
// Route loading fallback
// ---------------------------------------------------------------------------
function RouteLoadingFallback() {
  return (
    <div className="flex h-full w-full items-center justify-center">
      <div className="flex flex-col items-center gap-4">
        <div className="h-8 w-8 animate-spin rounded-full border-2 border-primary/30 border-t-primary" />
        <span className="text-sm text-text-secondary">Loading...</span>
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Routes
// ---------------------------------------------------------------------------
function AppRoutes() {
  return (
    <Routes>
      <Route element={<AppLayout />}>
        <Route
          index
          element={
            <Suspense fallback={<RouteLoadingFallback />}>
              <GameHome />
            </Suspense>
          }
        />
        <Route
          path="versions"
          element={
            <Suspense fallback={<RouteLoadingFallback />}>
              <Versions />
            </Suspense>
          }
        />
        <Route
          path="plugins"
          element={
            <Suspense fallback={<RouteLoadingFallback />}>
              <Plugins />
            </Suspense>
          }
        />
        <Route
          path="online-mods"
          element={
            <Suspense fallback={<RouteLoadingFallback />}>
              <OnlineMods />
            </Suspense>
          }
        />
        <Route
          path="settings"
          element={
            <Suspense fallback={<RouteLoadingFallback />}>
              <Settings />
            </Suspense>
          }
        />
      </Route>
    </Routes>
  );
}

// ---------------------------------------------------------------------------
// App root
// ---------------------------------------------------------------------------
export function App() {
  return (
    <TooltipProvider delayDuration={300}>
      <HashRouter>
        <AppRoutes />
      </HashRouter>
    </TooltipProvider>
  );
}