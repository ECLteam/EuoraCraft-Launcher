/**
 * OnlineModsPage Component
 *
 * Online mods browser with search, category filters, and a grid of mod cards.
 * Search with border-2, bg-bg-input. Category filters as blocky buttons.
 * Mod cards: border-2, shadow-[4px_4px_0px], icon with border-2.
 * Install button: grass. Download count: font-mono text-text-secondary.
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
import { cn } from "@/lib/utils";
import {
  Search,
  Download,
  Loader2,
  PackageOpen,
  Globe,
  Box,
  Sword,
  Wrench,
  PaintBucket,
  Zap,
  Users,
  Star,
} from "lucide-react";

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

interface OnlineMod {
  id: string;
  name: string;
  description: string;
  author: string;
  category: string;
  downloads: number;
  rating: number;
  version: string;
  icon?: string;
}

// ---------------------------------------------------------------------------
// Mock Data
// ---------------------------------------------------------------------------

const MOCK_MODS: OnlineMod[] = [
  {
    id: "m-1",
    name: "Sodium",
    description: "现代化的渲染引擎优化模组，大幅提升 FPS 并修复图形问题",
    author: "jellysquid3",
    category: "优化",
    downloads: 48200000,
    rating: 4.9,
    version: "1.20.4",
  },
  {
    id: "m-2",
    name: "Iris Shaders",
    description: "兼容 Sodium 的光影加载器，支持 OptiFine 光影包格式",
    author: "coderbot",
    category: "光影",
    downloads: 31500000,
    rating: 4.8,
    version: "1.20.4",
  },
  {
    id: "m-3",
    name: "JEI",
    description: "物品和配方查看器，查看合成配方、熔炉配方和药水配方",
    author: "mezz",
    category: "工具",
    downloads: 86000000,
    rating: 4.7,
    version: "1.20.4",
  },
  {
    id: "m-4",
    name: "Create",
    description: "机械动力模组，提供旋转动力系统，自动化生产和精致装饰",
    author: "simibubi",
    category: "科技",
    downloads: 52000000,
    rating: 4.9,
    version: "1.20.1",
  },
  {
    id: "m-5",
    name: "Xaero's World Map",
    description: "世界地图模组，提供完整的世界地图和迷你地图功能",
    author: "xaero96",
    category: "地图",
    downloads: 28000000,
    rating: 4.5,
    version: "1.20.4",
  },
  {
    id: "m-6",
    name: "Farmer's Delight",
    description: "农业扩展模组，添加新的作物、烹饪系统和厨房装饰",
    author: "vectorwing",
    category: "农业",
    downloads: 19000000,
    rating: 4.8,
    version: "1.20.1",
  },
  {
    id: "m-7",
    name: "Distant Horizons",
    description: "远距离渲染模组，实现超高视距的 LOD 地形渲染",
    author: "James Seibel",
    category: "优化",
    downloads: 8500000,
    rating: 4.6,
    version: "1.20.4",
  },
  {
    id: "m-8",
    name: "Biomes O' Plenty",
    description: "添加大量全新的生物群系，丰富世界探索体验",
    author: "Forstride",
    category: "世界",
    downloads: 72000000,
    rating: 4.4,
    version: "1.20.1",
  },
];

const CATEGORIES = [
  { id: "all", label: "全部", icon: Box },
  { id: "优化", label: "优化", icon: Zap },
  { id: "光影", label: "光影", icon: PaintBucket },
  { id: "工具", label: "工具", icon: Wrench },
  { id: "科技", label: "科技", icon: Sword },
  { id: "地图", label: "地图", icon: Globe },
  { id: "农业", label: "农业", icon: Box },
  { id: "世界", label: "世界", icon: Globe },
];

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function formatDownloads(count: number): string {
  if (count >= 1000000) {
    return `${(count / 1000000).toFixed(1)}M`;
  }
  if (count >= 1000) {
    return `${(count / 1000).toFixed(1)}K`;
  }
  return count.toString();
}

function getCategoryIcon(category: string) {
  const cat = CATEGORIES.find((c) => c.id === category);
  return cat?.icon ?? Box;
}

// ---------------------------------------------------------------------------
// Skeleton Card
// ---------------------------------------------------------------------------

function SkeletonCard() {
  return (
    <div className="flex flex-col gap-3 border-2 border-border-stone bg-bg-surface p-4 shadow-[4px_4px_0px_rgba(0,0,0,0.3)]">
      <div className="flex items-center gap-3">
        <Skeleton className="h-12 w-12 rounded-[2px]" />
        <div className="flex flex-1 flex-col gap-1.5">
          <Skeleton className="h-4 w-24 rounded-[2px]" />
          <Skeleton className="h-3 w-16 rounded-[2px]" />
        </div>
      </div>
      <Skeleton className="h-3 w-full rounded-[2px]" />
      <Skeleton className="h-3 w-3/4 rounded-[2px]" />
      <div className="flex items-center justify-between">
        <Skeleton className="h-4 w-16 rounded-[2px]" />
        <Skeleton className="h-8 w-20 rounded-[2px]" />
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Mod Card
// ---------------------------------------------------------------------------

interface ModCardProps {
  mod: OnlineMod;
  index: number;
  installing: string | null;
  onInstall: (id: string) => void;
}

function ModCard({ mod, index, installing, onInstall }: ModCardProps) {
  const isInstalling = installing === mod.id;
  const CategoryIcon = getCategoryIcon(mod.category);

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
      <div className="flex items-center gap-3">
        <div className="flex h-12 w-12 shrink-0 items-center justify-center border-2 border-border-stone bg-bg-elevated">
          <CategoryIcon className="h-6 w-6 text-grass/70" />
        </div>
        <div className="min-w-0 flex-1">
          <h4 className="truncate font-mono text-sm font-semibold text-grass">
            {mod.name}
          </h4>
          <div className="flex items-center gap-1.5 text-xs text-text-tertiary">
            <Users className="h-3 w-3" />
            <span>{mod.author}</span>
            <span className="text-text-tertiary/50">|</span>
            <span>v{mod.version}</span>
          </div>
        </div>
      </div>

      {/* Description */}
      <p className="line-clamp-2 text-xs leading-relaxed text-text-secondary">
        {mod.description}
      </p>

      {/* Bottom */}
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-3">
          <span className="flex items-center gap-1 font-mono text-xs text-text-secondary">
            <Download className="h-3 w-3" />
            {formatDownloads(mod.downloads)}
          </span>
          <span className="flex items-center gap-1 text-xs text-text-tertiary">
            <Star className="h-3 w-3 text-gold" />
            {mod.rating}
          </span>
          <Badge
            variant="secondary"
            className="border-2 border-border-stone px-1.5 py-0 text-[10px]"
          >
            {mod.category}
          </Badge>
        </div>

        <Button
          size="sm"
          className="h-8 gap-1.5"
          disabled={isInstalling}
          onClick={() => onInstall(mod.id)}
        >
          {isInstalling ? (
            <>
              <Loader2 className="h-3.5 w-3.5 animate-spin" />
              安装中
            </>
          ) : (
            <>
              <Download className="h-3.5 w-3.5" />
              安装
            </>
          )}
        </Button>
      </div>
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
        <PackageOpen className="h-8 w-8 text-text-tertiary" />
      </div>
      <h3 className="mb-1 font-mono text-lg font-semibold text-text-primary">
        没有找到模组
      </h3>
      <p className="text-sm text-text-secondary">
        尝试调整筛选条件或搜索关键词
      </p>
    </motion.div>
  );
}

// ---------------------------------------------------------------------------
// Loading State
// ---------------------------------------------------------------------------

function LoadingState() {
  return (
    <motion.div
      className="grid grid-cols-1 gap-3 sm:grid-cols-2 xl:grid-cols-3 2xl:grid-cols-4"
      initial={{ opacity: 0 }}
      animate={{ opacity: 1 }}
      transition={{ duration: 0.15, ease: [0.8, 0, 0.2, 1] }}
    >
      {Array.from({ length: 8 }).map((_, i) => (
        <SkeletonCard key={i} />
      ))}
    </motion.div>
  );
}

// ---------------------------------------------------------------------------
// OnlineModsPage Component
// ---------------------------------------------------------------------------

export function OnlineModsPage() {
  const [search, setSearch] = useState("");
  const [categoryFilter, setCategoryFilter] = useState("all");
  const [installing, setInstalling] = useState<string | null>(null);
  const [isLoading] = useState(false);

  const filteredMods = useMemo(() => {
    let result = MOCK_MODS;

    if (categoryFilter !== "all") {
      result = result.filter((m) => m.category === categoryFilter);
    }

    if (search.trim()) {
      const q = search.toLowerCase();
      result = result.filter(
        (m) =>
          m.name.toLowerCase().includes(q) ||
          m.description.toLowerCase().includes(q) ||
          m.author.toLowerCase().includes(q)
      );
    }

    return result;
  }, [search, categoryFilter]);

  const handleInstall = useCallback((id: string) => {
    setInstalling(id);
    setTimeout(() => {
      setInstalling(null);
    }, 2000);
  }, []);

  return (
    <motion.div
      className="flex h-full flex-col gap-4 bg-bg-deepslate p-6"
      initial={{ opacity: 0 }}
      animate={{ opacity: 1 }}
      transition={{ duration: 0.15, ease: [0.8, 0, 0.2, 1] }}
    >
      {/* ---- Search Bar ---- */}
      <motion.div
        initial={{ opacity: 0, y: -4 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ duration: 0.15, ease: [0.8, 0, 0.2, 1] }}
      >
        <div className="relative">
          <Search className="absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-text-tertiary" />
          <Input
            placeholder="搜索模组名称、描述或作者..."
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            className="h-10 border-2 border-border-stone bg-bg-input pl-9 font-mono text-sm"
          />
        </div>
      </motion.div>

      {/* ---- Category Filters ---- */}
      <motion.div
        className="flex flex-wrap items-center gap-1.5"
        initial={{ opacity: 0, y: -4 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ duration: 0.15, ease: [0.8, 0, 0.2, 1], delay: 0.03 }}
      >
        {CATEGORIES.map((cat) => {
          const Icon = cat.icon;
          const isActive = categoryFilter === cat.id;
          return (
            <button
              key={cat.id}
              onClick={() => setCategoryFilter(cat.id)}
              className={cn(
                "flex items-center gap-1.5 border-2 px-3 py-1.5 font-mono text-xs font-medium",
                "transition-[transform,box-shadow,color,background-color,border-color] duration-[150ms]",
                isActive
                  ? "border-grass bg-grass text-white shadow-[2px_2px_0px_rgba(0,0,0,0.4)]"
                  : "border-border-stone bg-bg-surface text-text-secondary hover:border-border-primary hover:text-text-primary hover:-translate-y-[1px] hover:shadow-[2px_2px_0px_rgba(0,0,0,0.3)]"
              )}
            >
              <Icon className="h-3.5 w-3.5" />
              {cat.label}
            </button>
          );
        })}
      </motion.div>

      {/* ---- Mod Grid ---- */}
      {isLoading ? (
        <LoadingState />
      ) : filteredMods.length === 0 ? (
        <EmptyState />
      ) : (
        <motion.div
          className="grid grid-cols-1 gap-3 overflow-auto sm:grid-cols-2 xl:grid-cols-3 2xl:grid-cols-4"
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
          {filteredMods.map((mod, index) => (
            <ModCard
              key={mod.id}
              mod={mod}
              index={index}
              installing={installing}
              onInstall={handleInstall}
            />
          ))}
        </motion.div>
      )}
    </motion.div>
  );
}