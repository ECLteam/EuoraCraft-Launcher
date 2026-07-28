/**
 * VersionsTab Component
 *
 * Version download/install tab with search, filter, and a scrollable grid
 * of version cards. Search input with border-2, bg-bg-input.
 * Filter tabs: border-b-2, active=grass. Version cards: border-2,
 * shadow-[4px_4px_0px], install button=grass.
 * Loading: skeleton cards with border-2.
 *
 * Minecraft Block Brutalist design system.
 * NO spring. NO glass. NO rounded corners.
 */

import { useState, useMemo, useCallback } from "react";
import { motion } from "framer-motion";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Badge } from "@/components/ui/badge";
import { Skeleton } from "@/components/ui/skeleton";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { cn } from "@/lib/utils";
import type { VersionType, LoaderType } from "@/config/version";
import { VERSION_TYPES, LOADER_TYPES } from "@/config/version";
import {
  Search,
  Download,
  CheckCircle,
  Loader2,
  Calendar,
} from "lucide-react";

// ---------------------------------------------------------------------------
// Mock Data Types
// ---------------------------------------------------------------------------

interface AvailableVersion {
  id: string;
  name: string;
  type: VersionType;
  releaseDate: string;
  loaders: LoaderType[];
}

// ---------------------------------------------------------------------------
// Mock Data
// ---------------------------------------------------------------------------

const MOCK_AVAILABLE_VERSIONS: AvailableVersion[] = [
  {
    id: "v-1",
    name: "1.21",
    type: "release",
    releaseDate: "2024-06-13",
    loaders: ["Vanilla", "Forge", "Fabric", "NeoForge"],
  },
  {
    id: "v-2",
    name: "1.20.6",
    type: "release",
    releaseDate: "2024-04-29",
    loaders: ["Vanilla", "Forge", "Fabric", "NeoForge"],
  },
  {
    id: "v-3",
    name: "1.20.4",
    type: "release",
    releaseDate: "2023-12-07",
    loaders: ["Vanilla", "Forge", "Fabric", "Quilt", "OptiFine"],
  },
  {
    id: "v-4",
    name: "1.19.4",
    type: "release",
    releaseDate: "2023-03-14",
    loaders: ["Vanilla", "Forge", "Fabric", "Quilt"],
  },
  {
    id: "v-5",
    name: "24w33a",
    type: "snapshot",
    releaseDate: "2024-08-14",
    loaders: ["Vanilla"],
  },
  {
    id: "v-6",
    name: "24w21b",
    type: "snapshot",
    releaseDate: "2024-05-22",
    loaders: ["Vanilla"],
  },
  {
    id: "v-7",
    name: "1.8.9",
    type: "release",
    releaseDate: "2015-12-09",
    loaders: ["Vanilla", "Forge", "LiteLoader"],
  },
  {
    id: "v-8",
    name: "1.16.5",
    type: "release",
    releaseDate: "2021-01-15",
    loaders: ["Vanilla", "Forge", "Fabric", "OptiFine"],
  },
];

// ---------------------------------------------------------------------------
// Filter Types
// ---------------------------------------------------------------------------

type VersionFilter = "all" | VersionType;

const FILTER_OPTIONS: { value: VersionFilter; label: string }[] = [
  { value: "all", label: "全部" },
  { value: "release", label: "正式版" },
  { value: "snapshot", label: "快照版" },
  { value: "old_beta", label: "旧版 Beta" },
  { value: "old_alpha", label: "旧版 Alpha" },
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

// ---------------------------------------------------------------------------
// Skeleton Card
// ---------------------------------------------------------------------------

function SkeletonCard() {
  return (
    <div className="flex flex-col gap-3 border-2 border-border-stone bg-bg-surface p-4 shadow-[4px_4px_0px_rgba(0,0,0,0.3)]">
      <div className="flex items-center justify-between">
        <Skeleton className="h-5 w-20 rounded-[2px]" />
        <Skeleton className="h-4 w-14 rounded-[2px]" />
      </div>
      <Skeleton className="h-3 w-32 rounded-[2px]" />
      <div className="flex items-center justify-between">
        <Skeleton className="h-4 w-16 rounded-[2px]" />
        <Skeleton className="h-8 w-20 rounded-[2px]" />
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Version Card
// ---------------------------------------------------------------------------

interface VersionCardProps {
  version: AvailableVersion;
  selectedLoader: LoaderType;
  index: number;
  installing: string | null;
  onInstall: (id: string, loader: LoaderType) => void;
}

function VersionCard({
  version,
  selectedLoader,
  index,
  installing,
  onInstall,
}: VersionCardProps) {
  const isInstalling = installing === version.id;
  const hasLoader = version.loaders.includes(selectedLoader);

  return (
    <motion.div
      className="flex flex-col gap-3 border-2 border-border-stone bg-bg-surface p-4 shadow-[4px_4px_0px_rgba(0,0,0,0.3)] transition-[transform,box-shadow,border-color] duration-[150ms] hover:border-border-primary hover:-translate-y-[1px] hover:shadow-[5px_5px_0px_rgba(0,0,0,0.35)]"
      initial={{ opacity: 0, y: 8 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{
        delay: index * 0.04,
        duration: 0.15,
        ease: [0.8, 0, 0.2, 1],
      }}
    >
      {/* Header */}
      <div className="flex items-center justify-between">
        <h4 className="font-mono text-base font-semibold text-grass">
          {version.name}
        </h4>
        {getTypeBadge(version.type)}
      </div>

      {/* Release Date */}
      <div className="flex items-center gap-1.5 text-xs text-text-tertiary">
        <Calendar className="h-3 w-3" />
        <span>发布日期: {version.releaseDate}</span>
      </div>

      {/* Bottom */}
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-1.5">
          {version.loaders.map((loader) => {
            const config = LOADER_TYPES[loader];
            const isSelected = selectedLoader === loader;
            return (
              <Badge
                key={loader}
                variant="outline"
                className={cn(
                  "border-2 px-1.5 py-0 text-[10px] font-medium transition-[border-color,background-color] duration-[150ms]",
                  isSelected
                    ? "border-grass/40 bg-grass/10 text-grass"
                    : "border-border-stone bg-transparent text-text-tertiary"
                )}
              >
                {config.label}
              </Badge>
            );
          })}
        </div>

        <Button
          size="sm"
          className="h-8 gap-1.5"
          disabled={!hasLoader || isInstalling}
          onClick={() => onInstall(version.id, selectedLoader)}
        >
          {isInstalling ? (
            <>
              <Loader2 className="h-3.5 w-3.5 animate-spin" />
              安装中
            </>
          ) : hasLoader ? (
            <>
              <Download className="h-3.5 w-3.5" />
              安装
            </>
          ) : (
            <>
              <CheckCircle className="h-3.5 w-3.5" />
              不兼容
            </>
          )}
        </Button>
      </div>
    </motion.div>
  );
}

// ---------------------------------------------------------------------------
// Loading State
// ---------------------------------------------------------------------------

function LoadingState() {
  return (
    <motion.div
      className="grid grid-cols-1 gap-3 sm:grid-cols-2 xl:grid-cols-3"
      initial={{ opacity: 0 }}
      animate={{ opacity: 1 }}
      transition={{ duration: 0.15, ease: [0.8, 0, 0.2, 1] }}
    >
      {Array.from({ length: 6 }).map((_, i) => (
        <SkeletonCard key={i} />
      ))}
    </motion.div>
  );
}

// ---------------------------------------------------------------------------
// Empty State
// ---------------------------------------------------------------------------

function EmptyState() {
  return (
    <motion.div
      className="flex flex-col items-center justify-center py-16"
      initial={{ opacity: 0, y: 4 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.15, ease: [0.8, 0, 0.2, 1] }}
    >
      <div className="mb-4 border-2 border-dashed border-border-stone bg-bg-surface p-4">
        <Search className="h-8 w-8 text-text-tertiary" />
      </div>
      <h3 className="mb-1 font-mono text-lg font-semibold text-text-primary">
        没有找到版本
      </h3>
      <p className="text-sm text-text-secondary">
        尝试调整筛选条件或搜索关键词
      </p>
    </motion.div>
  );
}

// ---------------------------------------------------------------------------
// VersionsTab Component
// ---------------------------------------------------------------------------

export function VersionsTab() {
  const [search, setSearch] = useState("");
  const [versionFilter, setVersionFilter] = useState<VersionFilter>("all");
  const [selectedLoader, setSelectedLoader] = useState<LoaderType>("Vanilla");
  const [installing, setInstalling] = useState<string | null>(null);
  const [isLoading] = useState(false);

  const filteredVersions = useMemo(() => {
    let result = MOCK_AVAILABLE_VERSIONS;

    if (versionFilter !== "all") {
      result = result.filter((v) => v.type === versionFilter);
    }

    if (search.trim()) {
      const q = search.toLowerCase();
      result = result.filter((v) => v.name.toLowerCase().includes(q));
    }

    return result;
  }, [search, versionFilter]);

  const handleInstall = useCallback(
    (id: string, _loader: LoaderType) => {
      setInstalling(id);
      setTimeout(() => {
        setInstalling(null);
      }, 2000);
    },
    []
  );

  return (
    <div className="flex flex-col gap-4">
      {/* ---- Search / Filter Bar ---- */}
      <motion.div
        className="flex flex-wrap items-center gap-3"
        initial={{ opacity: 0, y: -4 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ duration: 0.15, ease: [0.8, 0, 0.2, 1] }}
      >
        {/* Search Input */}
        <div className="relative min-w-[200px] flex-1">
          <Search className="absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-text-tertiary" />
          <Input
            placeholder="搜索版本号..."
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            className="h-9 border-2 border-border-stone bg-bg-input pl-9 font-mono text-sm"
          />
        </div>

        {/* Version Type Filter Tabs */}
        <div className="flex items-center gap-0">
          {FILTER_OPTIONS.map((opt) => (
            <button
              key={opt.value}
              onClick={() => setVersionFilter(opt.value)}
              className={cn(
                "border-b-2 px-3 py-1.5 font-mono text-xs font-medium",
                "transition-[color,border-color] duration-[150ms]",
                versionFilter === opt.value
                  ? "border-grass text-grass"
                  : "border-transparent text-text-secondary hover:text-text-primary"
              )}
            >
              {opt.label}
            </button>
          ))}
        </div>

        {/* Loader Selection */}
        <Select
          value={selectedLoader}
          onValueChange={(v) => setSelectedLoader(v as LoaderType)}
        >
          <SelectTrigger className="h-9 w-36">
            <SelectValue placeholder="选择加载器" />
          </SelectTrigger>
          <SelectContent>
            {Object.entries(LOADER_TYPES).map(([key, config]) => (
              <SelectItem key={key} value={key}>
                {config.label}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
      </motion.div>

      {/* ---- Version Grid ---- */}
      {isLoading ? (
        <LoadingState />
      ) : filteredVersions.length === 0 ? (
        <EmptyState />
      ) : (
        <motion.div
          className="grid grid-cols-1 gap-3 sm:grid-cols-2 xl:grid-cols-3"
          initial="hidden"
          animate="visible"
          variants={{
            hidden: { opacity: 0 },
            visible: {
              opacity: 1,
              transition: { staggerChildren: 0.03 },
            },
          }}
        >
          {filteredVersions.map((version, index) => (
            <VersionCard
              key={version.id}
              version={version}
              selectedLoader={selectedLoader}
              index={index}
              installing={installing}
              onInstall={handleInstall}
            />
          ))}
        </motion.div>
      )}
    </div>
  );
}