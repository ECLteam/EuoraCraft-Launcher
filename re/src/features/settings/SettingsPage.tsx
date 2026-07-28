/**
 * SettingsPage Component
 *
 * Settings page with sidebar navigation tabs:
 * - General (常规)
 * - Download (下载)
 * - Game (游戏)
 * - About (关于)
 *
 * Left sidebar tabs (font-mono), right content. bg-deepslate.
 * Minecraft Block Brutalist design system.
 * NO spring. NO glass. NO rounded corners.
 */

import { useState } from "react";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { GeneralTab } from "./GeneralTab";
import { DownloadTab } from "./DownloadTab";
import { GameTab } from "./GameTab";
import { AboutTab } from "./AboutTab";
import { cn } from "@/lib/utils";
import { Settings2, Download, Gamepad2, Info } from "lucide-react";

// ---------------------------------------------------------------------------
// Constants
// ---------------------------------------------------------------------------

const NAV_ITEMS = [
  { id: "general", label: "常规", icon: Settings2 },
  { id: "download", label: "下载", icon: Download },
  { id: "game", label: "游戏", icon: Gamepad2 },
  { id: "about", label: "关于", icon: Info },
] as const;

// ---------------------------------------------------------------------------
// SettingsPage Component
// ---------------------------------------------------------------------------

export function SettingsPage() {
  const [activeTab, setActiveTab] = useState("general");

  return (
    <div className="flex h-full w-full overflow-hidden bg-bg-deepslate">
      {/* ---- Left Sidebar Navigation ---- */}
      <aside className="flex w-48 shrink-0 flex-col border-r-2 border-border-secondary bg-bg-sidebar p-3">
        <div className="mb-3 px-2">
          <h2 className="font-mono text-xs font-semibold uppercase tracking-wider text-text-tertiary">
            设置
          </h2>
        </div>

        <nav className="flex flex-col gap-0.5">
          {NAV_ITEMS.map((item) => {
            const Icon = item.icon;
            const isActive = activeTab === item.id;

            return (
              <button
                key={item.id}
                onClick={() => setActiveTab(item.id)}
                className={cn(
                  "flex items-center gap-2.5 px-3 py-2 font-mono text-sm font-medium",
                  "transition-[color,background-color,border-color] duration-[150ms]",
                  "border-l-2",
                  isActive
                    ? "border-grass bg-bg-sidebar-active text-grass"
                    : "border-transparent text-text-secondary hover:bg-bg-sidebar-hover hover:text-text-primary"
                )}
              >
                <Icon
                  className={cn(
                    "h-4 w-4",
                    isActive ? "text-grass" : "text-text-tertiary"
                  )}
                />
                {item.label}
              </button>
            );
          })}
        </nav>
      </aside>

      {/* ---- Right Content Area ---- */}
      <div className="flex-1 overflow-hidden">
        <Tabs
          value={activeTab}
          onValueChange={setActiveTab}
          className="flex h-full flex-col"
        >
          <div className="hidden">
            <TabsList>
              <TabsTrigger value="general">常规</TabsTrigger>
              <TabsTrigger value="download">下载</TabsTrigger>
              <TabsTrigger value="game">游戏</TabsTrigger>
              <TabsTrigger value="about">关于</TabsTrigger>
            </TabsList>
          </div>

          <TabsContent
            value="general"
            className="h-full overflow-auto p-6 data-[state=inactive]:hidden"
          >
            <GeneralTab />
          </TabsContent>

          <TabsContent
            value="download"
            className="h-full overflow-auto p-6 data-[state=inactive]:hidden"
          >
            <DownloadTab />
          </TabsContent>

          <TabsContent
            value="game"
            className="h-full overflow-auto p-6 data-[state=inactive]:hidden"
          >
            <GameTab />
          </TabsContent>

          <TabsContent
            value="about"
            className="h-full overflow-auto p-6 data-[state=inactive]:hidden"
          >
            <AboutTab />
          </TabsContent>
        </Tabs>
      </div>
    </div>
  );
}