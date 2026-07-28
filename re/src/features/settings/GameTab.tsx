/**
 * GameTab Component
 *
 * Game settings for the launcher:
 * - Game directory path input with border-2, browse button=secondary
 * - Java path input with border-2, browse button=secondary
 * - Memory allocation: min/max sliders (grass track)
 * - Memory bar visualization: segments for system(stone), allocated(grass), free(gravel) with border-2
 * - Window size select
 * - JVM arguments textarea: border-2, bg-bg-input, font-mono
 *
 * All in card containers with border-2, shadow-[4px_4px_0px].
 * Minecraft Block Brutalist design system.
 * NO spring. NO glass. NO rounded corners.
 */

import { useState, useCallback } from "react";
import { motion } from "framer-motion";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Slider } from "@/components/ui/slider";
import { Label } from "@/components/ui/label";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { MEMORY_CONFIG, DEFAULT_JVM_ARGS, WINDOW_SIZE_OPTIONS } from "@/config/game";
import { FolderOpen, Coffee, HardDrive, Monitor, Terminal } from "lucide-react";

// ---------------------------------------------------------------------------
// Setting Group Card
// ---------------------------------------------------------------------------

interface SettingGroupProps {
  title: string;
  description?: string;
  children: React.ReactNode;
  delay?: number;
  icon?: React.ReactNode;
}

function SettingGroup({ title, description, children, delay = 0, icon }: SettingGroupProps) {
  return (
    <motion.div
      className="border-2 border-border-stone bg-bg-surface p-4 shadow-[4px_4px_0px_rgba(0,0,0,0.3)]"
      initial={{ opacity: 0, y: 8 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{
        delay,
        duration: 0.15,
        ease: [0.8, 0, 0.2, 1],
      }}
    >
      <div className="mb-3 flex items-center gap-2">
        {icon}
        <div>
          <h3 className="font-mono text-sm font-semibold text-text-primary">
            {title}
          </h3>
          {description && (
            <p className="mt-0.5 text-xs text-text-tertiary">{description}</p>
          )}
        </div>
      </div>
      {children}
    </motion.div>
  );
}

// ---------------------------------------------------------------------------
// Memory Bar
// ---------------------------------------------------------------------------

interface MemoryBarProps {
  maxMemory: number;
  totalSystemMB: number;
  usedSystemMB: number;
}

function MemoryBar({ maxMemory, totalSystemMB, usedSystemMB }: MemoryBarProps) {
  const totalGB = totalSystemMB / 1024;
  const usedGB = usedSystemMB / 1024;
  const allocatedGB = maxMemory / 1024;
  const freeGB = Math.max(0, totalGB - usedGB - allocatedGB);

  const usedPercent = (usedSystemMB / totalSystemMB) * 100;
  const allocatedPercent = (maxMemory / totalSystemMB) * 100;
  const freePercent = Math.max(0, 100 - usedPercent - allocatedPercent);

  return (
    <div className="flex flex-col gap-2">
      <div className="flex items-center justify-between font-mono text-xs text-text-tertiary">
        <span>系统内存: {totalGB.toFixed(1)} GB</span>
        <span>已分配: {allocatedGB.toFixed(1)} GB</span>
      </div>
      <div className="flex h-3 w-full overflow-hidden border-2 border-border-stone">
        {/* System used (stone) */}
        <div
          className="h-full bg-stone-700 transition-all duration-[150ms]"
          style={{ width: `${usedPercent}%` }}
          title={`系统已用: ${usedGB.toFixed(1)} GB`}
        />
        {/* Allocated (grass) */}
        <div
          className="h-full bg-grass transition-all duration-[150ms]"
          style={{ width: `${allocatedPercent}%` }}
          title={`已分配给游戏: ${allocatedGB.toFixed(1)} GB`}
        />
        {/* Free (gravel/bg-input) */}
        <div
          className="h-full flex-1 bg-bg-input transition-all duration-[150ms]"
          title={`可用: ${freePercent > 0 ? freeGB.toFixed(1) + " GB" : "0 GB"}`}
        />
      </div>
      <div className="flex items-center gap-4 font-mono text-[10px]">
        <span className="flex items-center gap-1">
          <span className="inline-block h-2 w-2 bg-stone-700" />
          系统已用
        </span>
        <span className="flex items-center gap-1">
          <span className="inline-block h-2 w-2 bg-grass" />
          游戏分配
        </span>
        <span className="flex items-center gap-1">
          <span className="inline-block h-2 w-2 bg-bg-input" />
          可用
        </span>
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// GameTab Component
// ---------------------------------------------------------------------------

export function GameTab() {
  const [gameDir, setGameDir] = useState("C:\\Users\\User\\.minecraft");
  const [javaPath, setJavaPath] = useState("C:\\Program Files\\Java\\jdk-21\\bin\\javaw.exe");
  const [minMemory, setMinMemory] = useState<number>(MEMORY_CONFIG.DEFAULT_MIN);
  const [maxMemory, setMaxMemory] = useState<number>(MEMORY_CONFIG.DEFAULT_MAX);
  const [windowSize, setWindowSize] = useState("1280x720");
  const [jvmArgs, setJvmArgs] = useState(DEFAULT_JVM_ARGS.join("\n"));

  // Simulated system memory (16 GB)
  const totalSystemMB = 16384;
  const usedSystemMB = 6144;

  const handleBrowseGameDir = useCallback(() => {
    console.log("Browse game directory");
  }, []);

  const handleBrowseJava = useCallback(() => {
    console.log("Browse Java path");
  }, []);

  const handleMinMemoryChange = useCallback(
    ([v]: number[]) => {
      const newMin = Math.min(v, maxMemory - MEMORY_CONFIG.STEP);
      setMinMemory(newMin);
    },
    [maxMemory]
  );

  const handleMaxMemoryChange = useCallback(
    ([v]: number[]) => {
      const newMax = Math.max(v, minMemory + MEMORY_CONFIG.STEP);
      setMaxMemory(newMax);
    },
    [minMemory]
  );

  const handleResetJvmArgs = useCallback(() => {
    setJvmArgs(DEFAULT_JVM_ARGS.join("\n"));
  }, []);

  return (
    <div className="flex flex-col gap-4">
      {/* ---- Game Directory ---- */}
      <SettingGroup
        title="游戏目录"
        description="Minecraft 游戏文件的存储位置"
        delay={0}
        icon={<HardDrive className="h-4 w-4 text-grass/70" />}
      >
        <div className="flex items-center gap-2">
          <Input
            value={gameDir}
            onChange={(e) => setGameDir(e.target.value)}
            className="h-9 flex-1 border-2 border-border-stone bg-bg-input font-mono text-xs"
            placeholder="选择游戏目录..."
          />
          <Button
            variant="secondary"
            size="sm"
            className="h-9 gap-1.5 shrink-0"
            onClick={handleBrowseGameDir}
          >
            <FolderOpen className="h-3.5 w-3.5" />
            浏览
          </Button>
        </div>
      </SettingGroup>

      {/* ---- Java Path ---- */}
      <SettingGroup
        title="Java 路径"
        description="Java 运行时的安装路径，推荐使用 Java 17 或更高版本"
        delay={0.03}
        icon={<Coffee className="h-4 w-4 text-grass/70" />}
      >
        <div className="flex items-center gap-2">
          <Input
            value={javaPath}
            onChange={(e) => setJavaPath(e.target.value)}
            className="h-9 flex-1 border-2 border-border-stone bg-bg-input font-mono text-xs"
            placeholder="选择 Java 路径..."
          />
          <Button
            variant="secondary"
            size="sm"
            className="h-9 gap-1.5 shrink-0"
            onClick={handleBrowseJava}
          >
            <FolderOpen className="h-3.5 w-3.5" />
            浏览
          </Button>
        </div>
      </SettingGroup>

      {/* ---- Memory Allocation ---- */}
      <SettingGroup
        title="内存分配"
        description="设置 Minecraft 游戏可用的内存大小"
        delay={0.06}
        icon={<Monitor className="h-4 w-4 text-grass/70" />}
      >
        <div className="flex flex-col gap-4">
          {/* Memory Bar */}
          <MemoryBar
            maxMemory={maxMemory}
            totalSystemMB={totalSystemMB}
            usedSystemMB={usedSystemMB}
          />

          {/* Min Memory Slider */}
          <div className="flex items-center gap-4">
            <Label className="w-16 shrink-0 font-mono text-xs text-text-secondary">
              最小内存
            </Label>
            <Slider
              value={[minMemory]}
              onValueChange={handleMinMemoryChange}
              min={MEMORY_CONFIG.MIN}
              max={MEMORY_CONFIG.MAX}
              step={MEMORY_CONFIG.STEP}
              className="flex-1"
            />
            <span className="w-20 text-right font-mono text-xs tabular-nums font-medium text-text-primary">
              {minMemory >= 1024
                ? `${(minMemory / 1024).toFixed(1)} GB`
                : `${minMemory} MB`}
            </span>
          </div>

          {/* Max Memory Slider */}
          <div className="flex items-center gap-4">
            <Label className="w-16 shrink-0 font-mono text-xs text-text-secondary">
              最大内存
            </Label>
            <Slider
              value={[maxMemory]}
              onValueChange={handleMaxMemoryChange}
              min={MEMORY_CONFIG.MIN}
              max={MEMORY_CONFIG.MAX}
              step={MEMORY_CONFIG.STEP}
              className="flex-1"
            />
            <span className="w-20 text-right font-mono text-xs tabular-nums font-medium text-text-primary">
              {maxMemory >= 1024
                ? `${(maxMemory / 1024).toFixed(1)} GB`
                : `${maxMemory} MB`}
            </span>
          </div>
        </div>
      </SettingGroup>

      {/* ---- Window Size ---- */}
      <SettingGroup
        title="窗口大小"
        description="设置游戏启动时的默认窗口分辨率"
        delay={0.09}
      >
        <Select value={windowSize} onValueChange={setWindowSize}>
          <SelectTrigger className="h-9 w-full">
            <SelectValue placeholder="选择窗口大小" />
          </SelectTrigger>
          <SelectContent>
            {WINDOW_SIZE_OPTIONS.map((opt) => (
              <SelectItem key={opt.label} value={opt.label}>
                {opt.label}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
      </SettingGroup>

      {/* ---- JVM Arguments ---- */}
      <SettingGroup
        title="JVM 参数"
        description="自定义 Java 虚拟机启动参数，请谨慎修改"
        delay={0.12}
        icon={<Terminal className="h-4 w-4 text-grass/70" />}
      >
        <div className="flex flex-col gap-2">
          <textarea
            value={jvmArgs}
            onChange={(e) => setJvmArgs(e.target.value)}
            className="min-h-[120px] w-full resize-y border-2 border-border-stone bg-bg-input px-3 py-2 font-mono text-xs leading-relaxed text-text-primary placeholder:text-text-tertiary transition-colors duration-[150ms] focus:border-grass focus:outline-none focus:ring-0"
            placeholder="-Xmx4G -Xms2G ..."
            spellCheck={false}
          />
          <div className="flex items-center justify-between">
            <span className="font-mono text-[10px] text-text-tertiary">
              每行一个参数，修改后立即生效
            </span>
            <Button
              variant="ghost"
              size="sm"
              className="h-7 text-xs"
              onClick={handleResetJvmArgs}
            >
              重置为默认
            </Button>
          </div>
        </div>
      </SettingGroup>
    </div>
  );
}