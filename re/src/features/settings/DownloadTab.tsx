/**
 * DownloadTab Component
 *
 * Download settings for the launcher:
 * - Download source: Official / BMCLAPI / MCBBS (radio cards, border-2, selected=border-grass)
 * - Download thread count slider (grass track)
 *
 * All in card containers with border-2, shadow-[4px_4px_0px].
 * Minecraft Block Brutalist design system.
 * NO spring. NO glass. NO rounded corners.
 */

import { useState } from "react";
import { motion } from "framer-motion";
import { Slider } from "@/components/ui/slider";
import { Label } from "@/components/ui/label";
import { cn } from "@/lib/utils";
import type { DownloadSource } from "@/config/version";
import { DOWNLOAD_SOURCES } from "@/config/version";
import { Globe, Server, Zap } from "lucide-react";

// ---------------------------------------------------------------------------
// Setting Group Card
// ---------------------------------------------------------------------------

interface SettingGroupProps {
  title: string;
  description?: string;
  children: React.ReactNode;
  delay?: number;
}

function SettingGroup({ title, description, children, delay = 0 }: SettingGroupProps) {
  return (
    <motion.div
      className="border-2 border-border-stone bg-bg-surface p-4 shadow-[4px_4px_0px_rgba(0,0,0,0.3)]"
      initial={{ opacity: 0, scale: 0.7, y: 8 }}
      animate={{ opacity: 1, scale: 1, y: 0 }}
      transition={{
        delay,
        duration: 0.35,
        ease: [0.34, 1.56, 0.64, 1],
      }}
    >
      <div className="mb-3">
        <h3 className="font-mono text-sm font-semibold text-text-primary">
          {title}
        </h3>
        {description && (
          <p className="mt-0.5 text-xs text-text-tertiary">{description}</p>
        )}
      </div>
      {children}
    </motion.div>
  );
}

// ---------------------------------------------------------------------------
// Source Config
// ---------------------------------------------------------------------------

const SOURCE_OPTIONS: { value: DownloadSource; icon: typeof Globe; description: string }[] = [
  {
    value: "mojang",
    icon: Globe,
    description: "从 Mojang 官方服务器下载，速度可能较慢但最可靠",
  },
  {
    value: "bmclapi",
    icon: Zap,
    description: "国内镜像加速，下载速度更快，推荐中国大陆用户使用",
  },
  {
    value: "mcbbs",
    icon: Server,
    description: "MCBBS 社区提供的镜像源，稳定性良好",
  },
];

// ---------------------------------------------------------------------------
// DownloadTab Component
// ---------------------------------------------------------------------------

export function DownloadTab() {
  const [downloadSource, setDownloadSource] = useState<DownloadSource>("bmclapi");
  const [threadCount, setThreadCount] = useState(16);

  return (
    <div className="flex flex-col gap-4">
      {/* ---- Download Source ---- */}
      <SettingGroup title="下载源" description="选择游戏文件下载来源" delay={0}>
        <div className="flex flex-col gap-2">
          {SOURCE_OPTIONS.map(({ value, icon: Icon, description }) => {
            const sourceConfig = DOWNLOAD_SOURCES[value];
            const isActive = downloadSource === value;

            return (
              <button
                key={value}
                onClick={() => setDownloadSource(value)}
                className={cn(
                  "flex items-start gap-3 border-2 p-3 text-left",
                  "transition-[border-color,background-color,transform,box-shadow] duration-[150ms]",
                  isActive
                    ? "border-grass bg-grass/5"
                    : "border-border-stone bg-transparent hover:border-border-primary hover:bg-bg-elevated hover:-translate-y-[1px] hover:shadow-[2px_2px_0px_rgba(0,0,0,0.3)]"
                )}
              >
                <div
                  className={cn(
                    "mt-0.5 flex h-8 w-8 shrink-0 items-center justify-center border-2",
                    isActive
                      ? "border-grass bg-grass/10 text-grass"
                      : "border-border-stone bg-bg-elevated text-text-tertiary"
                  )}
                >
                  <Icon className="h-4 w-4" />
                </div>
                <div className="min-w-0 flex-1">
                  <div className="flex items-center gap-2">
                    <span
                      className={cn(
                        "font-mono text-sm font-medium",
                        isActive ? "text-grass" : "text-text-primary"
                      )}
                    >
                      {sourceConfig.label}
                    </span>
                    {isActive && (
                      <span className="border-2 border-grass bg-grass px-1.5 py-0 font-mono text-[10px] font-medium text-white">
                        当前
                      </span>
                    )}
                  </div>
                  <p className="mt-0.5 text-xs text-text-tertiary">
                    {description}
                  </p>
                </div>
                <div
                  className={cn(
                    "mt-0.5 flex h-5 w-5 shrink-0 items-center justify-center border-2 transition-all duration-[150ms]",
                    isActive
                      ? "border-grass bg-grass"
                      : "border-border-stone bg-transparent"
                  )}
                >
                  {isActive && (
                    <div className="h-2 w-2 bg-white" />
                  )}
                </div>
              </button>
            );
          })}
        </div>
      </SettingGroup>

      {/* ---- Thread Count ---- */}
      <SettingGroup
        title="下载线程数"
        description="同时下载的文件数量，数值越大下载越快但占用更多资源"
        delay={0.03}
      >
        <div className="flex items-center gap-4">
          <Label className="w-20 shrink-0 font-mono text-xs text-text-secondary">
            线程数
          </Label>
          <Slider
            value={[threadCount]}
            onValueChange={([v]) => setThreadCount(v)}
            min={1}
            max={64}
            step={1}
            className="flex-1"
          />
          <span className="w-10 text-right font-mono text-sm tabular-nums font-medium text-text-primary">
            {threadCount}
          </span>
        </div>
        <div className="mt-2 flex justify-between">
          <span className="font-mono text-[10px] text-text-tertiary">
            1 (慢)
          </span>
          <span className="font-mono text-[10px] text-text-tertiary">
            64 (快)
          </span>
        </div>
      </SettingGroup>
    </div>
  );
}