/**
 * GameInfoCard Component
 *
 * Minecraft Block Brutalist tips carousel.
 * Square dots, fade transitions, font-mono labels.
 * NO glass, NO blur, NO rounded corners, NO scale.
 */

import { useState, useEffect, useCallback } from "react";
import { motion, AnimatePresence } from "framer-motion";
import {
  Lightbulb,
  Sword,
  Trees,
  Users,
  BookOpen,
  Compass,
} from "lucide-react";
import type { LucideIcon } from "lucide-react";
import { cn } from "@/lib/utils";

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

export interface TipItem {
  id: string;
  icon: LucideIcon;
  title: string;
  description: string;
  color: string;
}

interface GameInfoCardProps {
  tips?: TipItem[];
  interval?: number;
  className?: string;
}

// ---------------------------------------------------------------------------
// Default Tips
// ---------------------------------------------------------------------------

const DEFAULT_TIPS: TipItem[] = [
  {
    id: "tip-1",
    icon: Lightbulb,
    title: "Pro Tip",
    description:
      "Press F3 in-game to open the debug screen and see your coordinates, biome, and FPS.",
    color: "#FFAA00",
  },
  {
    id: "tip-2",
    icon: Sword,
    title: "Did You Know?",
    description:
      "Enchanting your tools with Efficiency V can mine stone blocks almost instantly. Combine with Haste II for maximum speed!",
    color: "#FF5500",
  },
  {
    id: "tip-3",
    icon: Trees,
    title: "Survival Guide",
    description:
      "Always carry a water bucket. It can save you from fall damage, extinguish fires, and create temporary bridges.",
    color: "#50C878",
  },
  {
    id: "tip-4",
    icon: Users,
    title: "Community Update",
    description:
      "EuoraCraft Season 5 is now live! Join the community server to play with friends and explore new biomes together.",
    color: "#3B6BD4",
  },
  {
    id: "tip-5",
    icon: BookOpen,
    title: "Modding 101",
    description:
      "Use the Plugins tab to install OptiFine for shader support and performance improvements. Fabric mods are also supported.",
    color: "#7F7F7F",
  },
  {
    id: "tip-6",
    icon: Compass,
    title: "Exploration",
    description:
      "Netherite tools can be found in Bastion Remnants. Upgrade your diamond gear at a Smithing Table for the best durability.",
    color: "#5B8731",
  },
];

// ---------------------------------------------------------------------------
// Fade transition (NO scale, NO spring)
// ---------------------------------------------------------------------------

const bounceEase: [number, number, number, number] = [0.34, 1.56, 0.64, 1];

const fadeVariants = {
  enter: {
    opacity: 0,
    y: 8,
    scale: 0.95,
  },
  center: {
    opacity: 1,
    y: 0,
    scale: 1,
    transition: { duration: 0.25, ease: bounceEase },
  },
  exit: {
    opacity: 0,
    y: -8,
    scale: 0.95,
    transition: { duration: 0.15, ease: [0.8, 0, 0.2, 1] as [number, number, number, number] },
  },
};

// ---------------------------------------------------------------------------
// Component
// ---------------------------------------------------------------------------

export function GameInfoCard({
  tips = DEFAULT_TIPS,
  interval = 5000,
  className,
}: GameInfoCardProps) {
  const [currentIndex, setCurrentIndex] = useState(0);
  const [isPaused, setIsPaused] = useState(false);

  const totalTips = tips.length;

  const goToNext = useCallback(() => {
    setCurrentIndex((prev) => (prev + 1) % totalTips);
  }, [totalTips]);

  useEffect(() => {
    if (isPaused || totalTips <= 1) return;
    const timer = setInterval(goToNext, interval);
    return () => clearInterval(timer);
  }, [goToNext, interval, isPaused, totalTips]);

  const currentTip = tips[currentIndex];
  const Icon = currentTip.icon;

  return (
    <motion.div
      initial={{ opacity: 0, scale: 0.7, y: 12 }}
      animate={{ opacity: 1, scale: 1, y: 0 }}
      transition={{ duration: 0.35, ease: bounceEase, delay: 0.1 }}
    >
      <div
        className={cn(
          "border-2 border-[#7F7F7F26] bg-[#1A1A1A]",
          "shadow-[4px_4px_0px_rgba(0,0,0,0.3)]",
          "overflow-hidden",
          className
        )}
        onMouseEnter={() => setIsPaused(true)}
        onMouseLeave={() => setIsPaused(false)}
      >
        {/* Header */}
        <div className="px-4 pt-3 pb-2">
          <div className="flex items-center gap-2">
            <span className="font-mono text-[10px] tracking-[0.15em] text-[#999999]">
              TIPS
            </span>
            <Lightbulb className="size-3 text-[#FFAA00]" />
          </div>
        </div>

        {/* Content */}
        <div className="px-4 pb-4">
          <div className="relative min-h-[72px]">
            <AnimatePresence mode="wait">
              <motion.div
                key={currentTip.id}
                variants={fadeVariants}
                initial="enter"
                animate="center"
                exit="exit"
                className="absolute inset-0"
              >
                <div className="flex items-start gap-3">
                  {/* Icon */}
                  <div
                    className="flex size-9 shrink-0 items-center justify-center border-2 border-[#7F7F7F26] bg-[#0D0D0D]"
                    style={{ color: currentTip.color }}
                  >
                    <Icon className="size-4" />
                  </div>

                  {/* Text */}
                  <div className="flex-1 min-w-0">
                    <h4 className="font-mono text-sm font-semibold text-[#E8E8E8]">
                      {currentTip.title}
                    </h4>
                    <p className="mt-1 text-xs text-[#999999] leading-relaxed line-clamp-3">
                      {currentTip.description}
                    </p>
                  </div>
                </div>
              </motion.div>
            </AnimatePresence>
          </div>

          {/* Square Navigation Dots */}
          {totalTips > 1 && (
            <div className="flex items-center justify-center gap-2 mt-3">
              {tips.map((tip, index) => (
                <button
                  key={tip.id}
                  type="button"
                  onClick={() => setCurrentIndex(index)}
                  className={cn(
                    "w-2 h-2 transition-[background-color,box-shadow] duration-[150ms]",
                    index === currentIndex
                      ? "bg-[#5B8731] shadow-[2px_2px_0px_rgba(0,0,0,0.3)]"
                      : "bg-[#7F7F7F26] hover:bg-[#7F7F7F40]"
                  )}
                  aria-label={`Go to tip ${index + 1}`}
                />
              ))}
            </div>
          )}
        </div>
      </div>
    </motion.div>
  );
}

export default GameInfoCard;