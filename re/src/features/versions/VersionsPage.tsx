/**
 * VersionsPage Component
 *
 * Main versions management page with sidebar navigation:
 * - "已安装" (Installed) - ManageTab
 * - "版本下载" (Download) - VersionsTab
 *
 * Minecraft Block Brutalist design system.
 * Left sidebar tabs with border-l-2 active indicator, bg-deepslate.
 */

import { useState } from "react";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { ManageTab } from "./ManageTab";
import { VersionsTab } from "./VersionsTab";
import { cn } from "@/lib/utils";
import { Package, Download } from "lucide-react";

// ---------------------------------------------------------------------------
// Constants
// ---------------------------------------------------------------------------

const NAV_ITEMS = [
  { id: "manage", label: "已安装", icon: Package },
  { id: "download", label: "版本下载", icon: Download },
] as const;

// ---------------------------------------------------------------------------
// VersionsPage Component
// ---------------------------------------------------------------------------

export function VersionsPage() {
  const [activeTab, setActiveTab] = useState("manage");

  return (
    <div className="flex h-full w-full overflow-hidden bg-bg-deepslate">
      {/* ---- Left Sidebar Navigation ---- */}
      <aside className="flex w-48 shrink-0 flex-col border-r-2 border-border-secondary bg-bg-sidebar p-3">
        <div className="mb-3 px-2">
          <h2 className="font-mono text-xs font-semibold uppercase tracking-wider text-text-tertiary">
            版本管理
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
              <TabsTrigger value="manage">已安装</TabsTrigger>
              <TabsTrigger value="download">版本下载</TabsTrigger>
            </TabsList>
          </div>

          <TabsContent
            value="manage"
            className="h-full overflow-auto p-6 data-[state=inactive]:hidden"
          >
            <ManageTab />
          </TabsContent>

          <TabsContent
            value="download"
            className="h-full overflow-auto p-6 data-[state=inactive]:hidden"
          >
            <VersionsTab />
          </TabsContent>
        </Tabs>
      </div>
    </div>
  );
}