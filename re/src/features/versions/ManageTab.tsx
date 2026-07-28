/**
 * ManageTab Component
 *
 * Displays installed Minecraft versions with blocky card styling.
 * Each card: border-2, bg-bg-surface, shadow-[4px_4px_0px].
 * Version name in font-mono text-grass. Badges with border-2.
 * Play/delete buttons with block shadows. Empty state: dashed border.
 *
 * Minecraft Block Brutalist design system.
 * NO spring. NO glass. NO rounded corners.
 */

import { useState, useCallback } from "react";
import { motion } from "framer-motion";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { cn } from "@/lib/utils";
import type { VersionType, LoaderType } from "@/config/version";
import { VERSION_TYPES, LOADER_TYPES } from "@/config/version";
import {
  Play,
  Trash2,
  Settings,
  Download,
  FolderOpen,
  RefreshCw,
  HardDrive,
  Clock,
} from "lucide-react";

// ---------------------------------------------------------------------------
// Mock Data Types
// ---------------------------------------------------------------------------

interface InstalledVersion {
  id: string;
  name: string;
  type: VersionType;
  loader: LoaderType;
  loaderVersion: string;
  lastPlayed: string;
  size: string;
  path: string;
}

// ---------------------------------------------------------------------------
// Mock Data
// ---------------------------------------------------------------------------

const MOCK_INSTALLED_VERSIONS: InstalledVersion[] = [
  {
    id: "1",
    name: "1.20.4",
    type: "release",
    loader: "Fabric",
    loaderVersion: "0.15.7",
    lastPlayed: "2026-07-27 14:30",
    size: "1.2 GB",
    path: "/games/1.20.4-fabric",
  },
  {
    id: "2",
    name: "1.21",
    type: "release",
    loader: "Forge",
    loaderVersion: "49.0.30",
    lastPlayed: "2026-07-26 09:15",
    size: "1.5 GB",
    path: "/games/1.21-forge",
  },
  {
    id: "3",
    name: "24w21b",
    type: "snapshot",
    loader: "Vanilla",
    loaderVersion: "-",
    lastPlayed: "2026-07-25 20:00",
    size: "980 MB",
    path: "/games/24w21b",
  },
  {
    id: "4",
    name: "1.19.2",
    type: "release",
    loader: "Quilt",
    loaderVersion: "0.22.0",
    lastPlayed: "2026-07-20 16:45",
    size: "1.1 GB",
    path: "/games/1.19.2-quilt",
  },
];

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function getTypeBadge(type: VersionType) {
  const config = VERSION_TYPES[type];
  return (
    <Badge
      variant="outline"
      className={cn(
        "border-2 px-1.5 py-0 text-[10px] font-medium",
        config.borderColor,
        config.bgColor,
        config.color
      )}
    >
      {config.label}
    </Badge>
  );
}

function getLoaderBadge(loader: LoaderType) {
  const config = LOADER_TYPES[loader];
  return (
    <Badge
      variant="secondary"
      className="border-2 border-border-stone px-1.5 py-0 text-[10px] font-medium"
    >
      {config.label}
    </Badge>
  );
}

// ---------------------------------------------------------------------------
// Empty State
// ---------------------------------------------------------------------------

interface EmptyStateProps {
  onGoDownload: () => void;
}

function EmptyState({ onGoDownload }: EmptyStateProps) {
  return (
    <motion.div
      className="flex flex-col items-center justify-center py-16"
      initial={{ opacity: 0, y: 4 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.15, ease: [0.8, 0, 0.2, 1] }}
    >
      <div className="mb-4 border-2 border-dashed border-border-stone bg-bg-surface p-4">
        <FolderOpen className="h-8 w-8 text-text-tertiary" />
      </div>
      <h3 className="mb-1 font-mono text-lg font-semibold text-text-primary">
        没有已安装的版本
      </h3>
      <p className="mb-6 text-sm text-text-secondary">
        你还没有安装任何 Minecraft 版本，前往下载页获取版本
      </p>
      <Button onClick={onGoDownload} className="gap-2">
        <Download className="h-4 w-4" />
        下载版本
      </Button>
    </motion.div>
  );
}

// ---------------------------------------------------------------------------
// Scanning State
// ---------------------------------------------------------------------------

function ScanningState() {
  return (
    <motion.div
      className="flex flex-col items-center justify-center py-16"
      initial={{ opacity: 0 }}
      animate={{ opacity: 1 }}
      transition={{ duration: 0.15, ease: [0.8, 0, 0.2, 1] }}
    >
      <div className="animate-block-spin mb-4 border-2 border-border-stone bg-bg-surface p-4">
        <RefreshCw className="h-8 w-8 text-grass" />
      </div>
      <h3 className="mb-1 font-mono text-lg font-semibold text-text-primary">
        正在扫描已安装版本...
      </h3>
      <p className="text-sm text-text-secondary">正在搜索游戏目录中的版本</p>
    </motion.div>
  );
}

// ---------------------------------------------------------------------------
// Version Card
// ---------------------------------------------------------------------------

interface VersionCardProps {
  version: InstalledVersion;
  index: number;
  onPlay: (id: string) => void;
  onDelete: (id: string) => void;
  onSettings: (id: string) => void;
}

function VersionCard({
  version,
  index,
  onPlay,
  onDelete,
  onSettings,
}: VersionCardProps) {
  return (
    <motion.div
      className="group flex items-center gap-4 border-2 border-border-stone bg-bg-surface p-4 shadow-[4px_4px_0px_rgba(0,0,0,0.3)] transition-[transform,box-shadow,border-color] duration-[150ms] hover:border-border-primary hover:-translate-y-[1px] hover:shadow-[5px_5px_0px_rgba(0,0,0,0.35)]"
      initial={{ opacity: 0, scale: 0.6, y: 8 }}
      animate={{ opacity: 1, scale: 1, y: 0 }}
      transition={{
        delay: index * 0.05,
        duration: 0.35,
        ease: [0.34, 1.56, 0.64, 1],
      }}
    >
      {/* Version Icon */}
      <div className="flex h-12 w-12 shrink-0 items-center justify-center border-2 border-border-stone bg-bg-elevated">
        <HardDrive className="h-6 w-6 text-grass/70" />
      </div>

      {/* Version Info */}
      <div className="min-w-0 flex-1">
        <div className="flex items-center gap-2">
          <h4 className="truncate font-mono text-base font-semibold text-grass">
            {version.name}
          </h4>
          {getTypeBadge(version.type)}
          {getLoaderBadge(version.loader)}
          {version.loader !== "Vanilla" && (
            <span className="font-mono text-[10px] text-text-tertiary">
              {version.loaderVersion}
            </span>
          )}
        </div>
        <div className="mt-1 flex items-center gap-3 text-xs text-text-tertiary">
          <span className="flex items-center gap-1">
            <Clock className="h-3 w-3" />
            最后游玩: {version.lastPlayed}
          </span>
          <span className="flex items-center gap-1">
            <HardDrive className="h-3 w-3" />
            {version.size}
          </span>
        </div>
      </div>

      {/* Action Buttons */}
      <div className="flex shrink-0 items-center gap-1.5 opacity-0 transition-opacity duration-[150ms] group-hover:opacity-100">
        <Button
          size="icon"
          variant="ghost"
          className="h-8 w-8"
          onClick={() => onSettings(version.id)}
          title="设置"
        >
          <Settings className="h-4 w-4" />
        </Button>
        <Button
          size="icon"
          variant="destructive"
          className="h-8 w-8"
          onClick={() => onDelete(version.id)}
          title="删除"
        >
          <Trash2 className="h-4 w-4" />
        </Button>
        <Button
          size="sm"
          className="h-8 gap-1.5"
          onClick={() => onPlay(version.id)}
        >
          <Play className="h-3.5 w-3.5" />
          启动
        </Button>
      </div>
    </motion.div>
  );
}

// ---------------------------------------------------------------------------
// ManageTab Component
// ---------------------------------------------------------------------------

interface ManageTabProps {
  onGoDownload?: () => void;
}

export function ManageTab({ onGoDownload }: ManageTabProps) {
  const [scanning] = useState(false);
  const [versions] = useState<InstalledVersion[]>(MOCK_INSTALLED_VERSIONS);

  const handlePlay = useCallback((id: string) => {
    console.log("Launching version:", id);
  }, []);

  const handleDelete = useCallback((id: string) => {
    console.log("Deleting version:", id);
  }, []);

  const handleSettings = useCallback((id: string) => {
    console.log("Opening settings for version:", id);
  }, []);

  const handleGoDownload = useCallback(() => {
    onGoDownload?.();
  }, [onGoDownload]);

  if (scanning) {
    return <ScanningState />;
  }

  if (versions.length === 0) {
    return <EmptyState onGoDownload={handleGoDownload} />;
  }

  return (
    <div className="flex flex-col gap-3">
      {versions.map((version, index) => (
        <VersionCard
          key={version.id}
          version={version}
          index={index}
          onPlay={handlePlay}
          onDelete={handleDelete}
          onSettings={handleSettings}
        />
      ))}
    </div>
  );
}