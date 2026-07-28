/**
 * GamePage Component
 *
 * Minecraft Block Brutalist design system.
 * Asymmetric layout: 60% hero left, 40% card stack right.
 * Block shadows, sharp corners, font-mono typography.
 * NO glass, NO blur, NO rounded corners, NO scale animations.
 */

import { useState, useCallback } from "react";
import { motion } from "framer-motion";
import { Pickaxe } from "lucide-react";
import { GameAccountCard, MOCK_ACCOUNT } from "./GameAccountCard";
import { GameInfoCard } from "./GameInfoCard";
import { GameLaunchBar } from "./GameLaunchBar";
import { LaunchProgressCard, useDemoLaunchProgress } from "./LaunchProgressCard";

// ---------------------------------------------------------------------------
// Animation Variants (snappy, no spring, no scale)
// ---------------------------------------------------------------------------

const snappyEase: [number, number, number, number] = [0.8, 0, 0.2, 1];

const staggerContainer = {
  hidden: { opacity: 0 },
  visible: {
    opacity: 1,
    transition: {
      staggerChildren: 0.08,
      delayChildren: 0.05,
    },
  },
};

const fadeUp = {
  hidden: { opacity: 0, y: 12 },
  visible: {
    opacity: 1,
    y: 0,
    transition: { duration: 0.15, ease: snappyEase },
  },
};

// ---------------------------------------------------------------------------
// Block Grid (decorative 4x4 Minecraft-style block grid)
// ---------------------------------------------------------------------------

const BLOCK_COLORS = [
  "#5B8731", "#5B8731", "#7F7F7F", "#3B6BD4",
  "#7F7F7F", "#3B6BD4", "#5B8731", "#7F7F7F",
  "#3B6BD4", "#5B8731", "#7F7F7F", "#5B8731",
  "#7F7F7F", "#7F7F7F", "#3B6BD4", "#5B8731",
];

function BlockGrid() {
  return (
    <div className="grid grid-cols-4 gap-[2px]" style={{ width: 56, height: 56 }}>
      {BLOCK_COLORS.map((color, i) => (
        <div
          key={i}
          className="w-3 h-3"
          style={{
            backgroundColor: color,
            boxShadow: `inset 1px 1px 0px rgba(255,255,255,0.15), inset -1px -1px 0px rgba(0,0,0,0.25)`,
          }}
        />
      ))}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Subtle Grid Pattern (CSS background-image)
// ---------------------------------------------------------------------------

function GridPattern() {
  return (
    <div
      className="absolute inset-0 pointer-events-none"
      style={{
        backgroundImage: `
          linear-gradient(rgba(127,127,127,0.04) 1px, transparent 1px),
          linear-gradient(90deg, rgba(127,127,127,0.04) 1px, transparent 1px)
        `,
        backgroundSize: "32px 32px",
      }}
    />
  );
}

// ---------------------------------------------------------------------------
// Hero Section (Left Side - 60%)
// ---------------------------------------------------------------------------

function HeroSection() {
  return (
    <motion.div
      className="flex flex-col items-start justify-center pl-6"
      variants={staggerContainer}
      initial="hidden"
      animate="visible"
    >
      {/* Block grid decoration */}
      <motion.div variants={fadeUp} className="mb-6">
        <BlockGrid />
      </motion.div>

      {/* Title */}
      <motion.h1
        variants={fadeUp}
        className="font-mono text-4xl font-bold text-[#5B8731]"
        style={{ textShadow: "3px 3px 0px rgba(0,0,0,0.3)" }}
      >
        EuoraCraft
      </motion.h1>

      {/* Subtitle */}
      <motion.p
        variants={fadeUp}
        className="mt-2 font-mono text-sm text-[#999999] tracking-[0.25em]"
      >
        BLOCK BY BLOCK
      </motion.p>

      {/* Description */}
      <motion.p
        variants={fadeUp}
        className="mt-4 text-sm text-[#999999] max-w-sm leading-relaxed"
      >
        Select a version and start your adventure.
        Explore infinite worlds, build amazing creations,
        and play with friends.
      </motion.p>

      {/* Decorative divider */}
      <motion.div
        variants={fadeUp}
        className="mt-6 flex items-center gap-3"
      >
        <div className="h-[2px] w-10 bg-[#7F7F7F26]" />
        <Pickaxe className="size-3.5 text-[#555555]" />
        <div className="h-[2px] w-10 bg-[#7F7F7F26]" />
      </motion.div>

      {/* Version info tags */}
      <motion.div
        variants={fadeUp}
        className="mt-6 flex items-center gap-3"
      >
        {[
          { label: "1.21", sub: "Multi-Version" },
          { label: "Forge / Fabric", sub: "Mods Support" },
          { label: "Microsoft", sub: "Account" },
        ].map((item) => (
          <div
            key={item.label}
            className="flex flex-col items-center gap-1 px-3 py-2 border-2 border-[#7F7F7F26] bg-[#1A1A1A]"
          >
            <span className="font-mono text-xs text-[#E8E8E8] font-semibold">
              {item.label}
            </span>
            <span className="text-[10px] text-[#555555]">
              {item.sub}
            </span>
          </div>
        ))}
      </motion.div>
    </motion.div>
  );
}

// ---------------------------------------------------------------------------
// Main GamePage Component
// ---------------------------------------------------------------------------

export function GamePage() {
  const [isLaunching, setIsLaunching] = useState(false);
  const [selectedVersion, setSelectedVersion] = useState<string | undefined>();

  const launchProgress = useDemoLaunchProgress();

  const handleAccountClick = useCallback(() => {
    console.log("[GamePage] Account card clicked");
  }, []);

  const handleVersionSelect = useCallback((versionId: string) => {
    setSelectedVersion(versionId);
  }, []);

  const handleSettingsClick = useCallback(() => {
    console.log("[GamePage] Settings clicked");
  }, []);

  const handleLaunch = useCallback(() => {
    if (!selectedVersion) return;
    setIsLaunching(true);
    launchProgress.startLaunch();
    console.log("[GamePage] Launching version:", selectedVersion);
  }, [selectedVersion, launchProgress]);

  const handleCancelLaunch = useCallback(() => {
    launchProgress.cancel();
    setIsLaunching(false);
  }, [launchProgress]);

  const handleDismissProgress = useCallback(() => {
    launchProgress.dismiss();
    setIsLaunching(false);
  }, [launchProgress]);

  return (
    <div className="relative h-full w-full bg-[#0D0D0D] overflow-hidden">
      {/* Grid Pattern Overlay */}
      <GridPattern />

      {/* Main Layout: Asymmetric (60/40) */}
      <div className="relative z-10 flex h-full">
        {/* ---- Left: Hero (60%) ---- */}
        <div className="w-[60%] flex items-center">
          <HeroSection />
        </div>

        {/* ---- Right: Card Stack (40%) ---- */}
        <div className="w-[40%] flex flex-col gap-4 justify-center pr-6">
          <GameAccountCard
            account={MOCK_ACCOUNT}
            onClick={handleAccountClick}
          />

          <GameInfoCard />

          <GameLaunchBar
            selectedVersionId={selectedVersion}
            onVersionSelect={handleVersionSelect}
            onSettingsClick={handleSettingsClick}
            onLaunch={handleLaunch}
            isLaunching={isLaunching}
          />

          <LaunchProgressCard
            isVisible={launchProgress.isVisible}
            status={launchProgress.status}
            currentStage={launchProgress.currentStage}
            progress={launchProgress.progress}
            onCancel={handleCancelLaunch}
            onDismiss={handleDismissProgress}
          />
        </div>
      </div>
    </div>
  );
}

export default GamePage;