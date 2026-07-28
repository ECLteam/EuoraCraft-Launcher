/**
 * GeneralTab Component
 *
 * General settings for the launcher:
 * - Theme mode: System / Dark / Light (border-2, active=grass)
 * - Primary color: 6 swatch squares (border-2, active=border-grass)
 * - Background image URL input (border-2)
 * - Background blur slider (grass track)
 * - Transparent background toggle (Switch: grass active)
 * - Sidebar style: Expanded / Collapsed (border-2, active=grass)
 * - Navigation mode: Sidebar / Top (border-2, active=grass)
 *
 * All in card containers with border-2, shadow-[4px_4px_0px].
 * Minecraft Block Brutalist design system.
 * NO spring. NO glass. NO rounded corners.
 */

import { useState, useCallback } from "react";
import { motion } from "framer-motion";
import { Input } from "@/components/ui/input";
import { Switch } from "@/components/ui/switch";
import { Slider } from "@/components/ui/slider";
import { Label } from "@/components/ui/label";
import { cn } from "@/lib/utils";
import type { ThemeMode, ThemeColor } from "@/config/theme";
import { THEME_COLORS } from "@/config/theme";
import {
  Sun,
  Moon,
  Monitor,
  Image,
  Sidebar,
  PanelTop,
  Check,
} from "lucide-react";

// ---------------------------------------------------------------------------
// Color Swatch Data
// ---------------------------------------------------------------------------

const COLOR_SWATCHES: { key: ThemeColor; hex: string }[] = [
  { key: "blue", hex: "#5c7cfa" },
  { key: "purple", hex: "#a040ff" },
  { key: "green", hex: "#22c55e" },
  { key: "orange", hex: "#f97316" },
  { key: "pink", hex: "#ec4899" },
  { key: "teal", hex: "#14b8a6" },
];

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
      initial={{ opacity: 0, y: 8 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{
        delay,
        duration: 0.15,
        ease: [0.8, 0, 0.2, 1],
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
// GeneralTab Component
// ---------------------------------------------------------------------------

export function GeneralTab() {
  const [themeMode, setThemeMode] = useState<ThemeMode>("dark");
  const [primaryColor, setPrimaryColor] = useState<ThemeColor>("blue");
  const [bgImageUrl, setBgImageUrl] = useState("");
  const [bgBlur, setBgBlur] = useState(8);
  const [transparentBg, setTransparentBg] = useState(false);
  const [sidebarExpanded, setSidebarExpanded] = useState(true);
  const [navMode, setNavMode] = useState<"sidebar" | "top">("sidebar");

  const handleBgImageClear = useCallback(() => {
    setBgImageUrl("");
  }, []);

  return (
    <div className="flex flex-col gap-4">
      {/* ---- Theme Mode ---- */}
      <SettingGroup title="主题模式" description="选择应用程序的主题外观" delay={0}>
        <div className="flex items-center gap-2">
          {([
            { value: "system" as ThemeMode, label: "跟随系统", icon: Monitor },
            { value: "dark" as ThemeMode, label: "深色", icon: Moon },
            { value: "light" as ThemeMode, label: "浅色", icon: Sun },
          ]).map(({ value, label, icon: Icon }) => (
            <button
              key={value}
              onClick={() => setThemeMode(value)}
              className={cn(
                "flex flex-1 items-center justify-center gap-2 border-2 px-3 py-2.5 font-mono text-sm font-medium",
                "transition-[color,background-color,border-color,transform,box-shadow] duration-[150ms]",
                themeMode === value
                  ? "border-grass bg-grass/10 text-grass"
                  : "border-border-stone bg-transparent text-text-secondary hover:border-border-primary hover:text-text-primary hover:-translate-y-[1px] hover:shadow-[2px_2px_0px_rgba(0,0,0,0.3)]"
              )}
            >
              <Icon className="h-4 w-4" />
              {label}
            </button>
          ))}
        </div>
      </SettingGroup>

      {/* ---- Primary Color ---- */}
      <SettingGroup title="主题色" description="选择应用程序的主色调" delay={0.03}>
        <div className="flex items-center gap-2">
          {COLOR_SWATCHES.map((swatch) => (
            <button
              key={swatch.key}
              onClick={() => setPrimaryColor(swatch.key)}
              className={cn(
                "flex h-9 w-9 items-center justify-center border-2 transition-[border-color,transform,box-shadow] duration-[150ms]",
                primaryColor === swatch.key
                  ? "border-grass shadow-[0_0_0px_2px_rgba(91,135,49,0.4)]"
                  : "border-transparent hover:border-border-stone hover:-translate-y-[1px] hover:shadow-[2px_2px_0px_rgba(0,0,0,0.3)]"
              )}
              style={{ backgroundColor: swatch.hex }}
              title={THEME_COLORS[swatch.key].name}
            >
              {primaryColor === swatch.key && (
                <Check className="h-4 w-4 text-white" strokeWidth={3} />
              )}
            </button>
          ))}
        </div>
      </SettingGroup>

      {/* ---- Background Image ---- */}
      <SettingGroup title="背景图片" description="设置启动器背景图片 URL" delay={0.06}>
        <div className="flex items-center gap-2">
          <div className="relative flex-1">
            <Image className="absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-text-tertiary" />
            <Input
              placeholder="输入背景图片 URL..."
              value={bgImageUrl}
              onChange={(e) => setBgImageUrl(e.target.value)}
              className="h-9 border-2 border-border-stone bg-bg-input pl-9 font-mono text-sm"
            />
          </div>
          {bgImageUrl && (
            <button
              onClick={handleBgImageClear}
              className="shrink-0 font-mono text-xs text-text-tertiary transition-colors duration-[150ms] hover:text-lava"
            >
              清除
            </button>
          )}
        </div>
      </SettingGroup>

      {/* ---- Background Blur + Transparent ---- */}
      <SettingGroup title="背景效果" description="调整背景模糊程度和透明度" delay={0.09}>
        <div className="flex flex-col gap-4">
          <div className="flex items-center gap-4">
            <Label className="w-20 shrink-0 font-mono text-xs text-text-secondary">
              背景模糊
            </Label>
            <Slider
              value={[bgBlur]}
              onValueChange={([v]) => setBgBlur(v)}
              min={0}
              max={24}
              step={1}
              className="flex-1"
            />
            <span className="w-8 text-right font-mono text-xs tabular-nums text-text-tertiary">
              {bgBlur}px
            </span>
          </div>

          <div className="flex items-center justify-between">
            <Label className="font-mono text-xs text-text-secondary">
              启用透明背景
            </Label>
            <Switch
              checked={transparentBg}
              onCheckedChange={setTransparentBg}
            />
          </div>
        </div>
      </SettingGroup>

      {/* ---- Sidebar Style ---- */}
      <SettingGroup title="侧边栏样式" description="选择侧边栏的展开/折叠状态" delay={0.12}>
        <div className="flex items-center gap-2">
          {([
            { value: true, label: "展开", icon: Sidebar },
            { value: false, label: "折叠", icon: PanelTop },
          ]).map(({ value, label, icon: Icon }) => (
            <button
              key={String(value)}
              onClick={() => setSidebarExpanded(value)}
              className={cn(
                "flex flex-1 items-center justify-center gap-2 border-2 px-3 py-2.5 font-mono text-sm font-medium",
                "transition-[color,background-color,border-color,transform,box-shadow] duration-[150ms]",
                sidebarExpanded === value
                  ? "border-grass bg-grass/10 text-grass"
                  : "border-border-stone bg-transparent text-text-secondary hover:border-border-primary hover:text-text-primary hover:-translate-y-[1px] hover:shadow-[2px_2px_0px_rgba(0,0,0,0.3)]"
              )}
            >
              <Icon className="h-4 w-4" />
              {label}
            </button>
          ))}
        </div>
      </SettingGroup>

      {/* ---- Navigation Mode ---- */}
      <SettingGroup title="导航模式" description="选择侧边栏导航或顶部导航" delay={0.15}>
        <div className="flex items-center gap-2">
          {([
            { value: "sidebar" as const, label: "侧边栏", icon: Sidebar },
            { value: "top" as const, label: "顶部栏", icon: PanelTop },
          ]).map(({ value, label, icon: Icon }) => (
            <button
              key={value}
              onClick={() => setNavMode(value)}
              className={cn(
                "flex flex-1 items-center justify-center gap-2 border-2 px-3 py-2.5 font-mono text-sm font-medium",
                "transition-[color,background-color,border-color,transform,box-shadow] duration-[150ms]",
                navMode === value
                  ? "border-grass bg-grass/10 text-grass"
                  : "border-border-stone bg-transparent text-text-secondary hover:border-border-primary hover:text-text-primary hover:-translate-y-[1px] hover:shadow-[2px_2px_0px_rgba(0,0,0,0.3)]"
              )}
            >
              <Icon className="h-4 w-4" />
              {label}
            </button>
          ))}
        </div>
      </SettingGroup>
    </div>
  );
}