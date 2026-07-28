/**
 * LaunchProgressCard Component
 *
 * Minecraft Block Brutalist launch progress card.
 * Block shadows, sharp corners, font-mono, square stage dots.
 * Snappy animations, NO glass, NO blur, NO scale.
 */

import { useState, useEffect, useCallback } from "react";
import { motion, AnimatePresence } from "framer-motion";
import {
  X,
  Loader2,
  CheckCircle2,
  AlertTriangle,
} from "lucide-react";
import { cn } from "@/lib/utils";
import { LAUNCH_STAGES } from "@/config/game";
import type { LaunchStage } from "@/config/game";

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

type LaunchStatus = "idle" | "launching" | "success" | "error" | "cancelled";

interface LaunchProgressCardProps {
  isVisible: boolean;
  status?: LaunchStatus;
  currentStage?: LaunchStage;
  progress?: number;
  message?: string;
  onCancel?: () => void;
  onDismiss?: () => void;
  className?: string;
}

// ---------------------------------------------------------------------------
// Animation Variants (snappy, no spring, no scale)
// ---------------------------------------------------------------------------

const snappyEase: [number, number, number, number] = [0.8, 0, 0.2, 1];

const cardVariants = {
  hidden: {
    opacity: 0,
    y: 16,
  },
  visible: {
    opacity: 1,
    y: 0,
    transition: { duration: 0.15, ease: snappyEase },
  },
  exit: {
    opacity: 0,
    y: 16,
    transition: { duration: 0.12, ease: snappyEase },
  },
};

const stageTextVariants = {
  enter: { opacity: 0, x: 8 },
  center: {
    opacity: 1,
    x: 0,
    transition: { duration: 0.15, ease: snappyEase },
  },
  exit: {
    opacity: 0,
    x: -8,
    transition: { duration: 0.1, ease: snappyEase },
  },
};

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function getStageLabel(stage: LaunchStage): string {
  const found = LAUNCH_STAGES.find((s) => s.stage === stage);
  return found?.label ?? "Processing...";
}

// ---------------------------------------------------------------------------
// Component
// ---------------------------------------------------------------------------

export function LaunchProgressCard({
  isVisible,
  status = "launching",
  currentStage = "checking_java",
  progress = 0,
  message,
  onCancel,
  onDismiss,
  className,
}: LaunchProgressCardProps) {
  const stageLabel = message ?? getStageLabel(currentStage);

  const statusColor = {
    launching: "#5B8731",
    success: "#50C878",
    error: "#FF5500",
    cancelled: "#999999",
    idle: "#555555",
  }[status];

  const StatusIcon = {
    launching: Loader2,
    success: CheckCircle2,
    error: AlertTriangle,
    cancelled: X,
    idle: Loader2,
  }[status];

  return (
    <AnimatePresence>
      {isVisible && (
        <motion.div
          variants={cardVariants}
          initial="hidden"
          animate="visible"
          exit="exit"
          className={cn("w-full", className)}
        >
          <div
            className={cn(
              "border-2 border-[#7F7F7F26] bg-[#1A1A1A]",
              "shadow-[4px_4px_0px_rgba(0,0,0,0.3)]",
              "overflow-hidden"
            )}
          >
            {/* ---- Header ---- */}
            <div className="px-4 pt-3 pb-2">
              <div className="flex items-center justify-between">
                <div className="flex items-center gap-2">
                  <span className="font-mono text-[10px] tracking-[0.15em] text-[#999999]">
                    PROGRESS
                  </span>
                  <StatusIcon
                    className={cn(
                      "size-3.5",
                      status === "launching" && "animate-spin"
                    )}
                    style={{ color: statusColor }}
                  />
                </div>

                {/* Cancel / Dismiss */}
                {status === "launching" ? (
                  <button
                    type="button"
                    className={cn(
                      "flex size-6 items-center justify-center",
                      "border-2 border-[#7F7F7F26] bg-transparent",
                      "text-[#555555] hover:text-[#FF5500] hover:border-[#FF5500]",
                      "transition-[color,border-color] duration-[150ms]"
                    )}
                    onClick={onCancel}
                  >
                    <X className="size-3" />
                  </button>
                ) : (
                  <button
                    type="button"
                    className={cn(
                      "flex size-6 items-center justify-center",
                      "border-2 border-[#7F7F7F26] bg-transparent",
                      "text-[#555555] hover:text-[#E8E8E8]",
                      "transition-[color] duration-[150ms]"
                    )}
                    onClick={onDismiss}
                  >
                    <X className="size-3" />
                  </button>
                )}
              </div>
            </div>

            {/* ---- Content ---- */}
            <div className="px-4 pb-4 space-y-3">
              {/* Progress Bar */}
              <div className="space-y-1.5">
                {/* Custom progress bar: border-2 border-stone, bg-gravel-input, fill=grass */}
                <div className="h-2 w-full border-2 border-[#7F7F7F26] bg-[#1E1E1E] overflow-hidden">
                  <motion.div
                    className="h-full bg-[#5B8731]"
                    initial={{ width: 0 }}
                    animate={{ width: `${Math.min(progress, 100)}%` }}
                    transition={{ duration: 0.15, ease: snappyEase }}
                    style={{
                      boxShadow: "2px 2px 0px rgba(0,0,0,0.3)",
                    }}
                  />
                </div>

                <div className="flex items-center justify-between">
                  <AnimatePresence mode="wait">
                    <motion.p
                      key={currentStage}
                      variants={stageTextVariants}
                      initial="enter"
                      animate="center"
                      exit="exit"
                      className="font-mono text-xs text-[#999999]"
                    >
                      {stageLabel}
                    </motion.p>
                  </AnimatePresence>
                  <span className="font-mono text-xs text-[#555555] tabular-nums">
                    {Math.round(progress)}%
                  </span>
                </div>
              </div>

              {/* Stage Indicator Dots (square) */}
              <div className="flex items-center gap-1.5">
                {LAUNCH_STAGES.map((stage) => {
                  const stageIndex = LAUNCH_STAGES.findIndex(
                    (s) => s.stage === stage.stage
                  );
                  const currentIndex = LAUNCH_STAGES.findIndex(
                    (s) => s.stage === currentStage
                  );
                  const isCompleted = stageIndex < currentIndex;
                  const isCurrent = stageIndex === currentIndex;
                  const isPending = stageIndex > currentIndex;

                  return (
                    <div
                      key={stage.stage}
                      className={cn(
                        "flex-1 h-1.5 transition-[background-color,box-shadow] duration-[150ms]",
                        isCompleted && "bg-[#5B8731] shadow-[1px_1px_0px_rgba(0,0,0,0.3)]",
                        isCurrent && status === "launching" && "bg-[#3B6BD4] animate-pulse",
                        isCurrent && status === "success" && "bg-[#50C878]",
                        isCurrent && status === "error" && "bg-[#FF5500]",
                        isCurrent && status === "cancelled" && "bg-[#999999]",
                        isPending && "bg-[#7F7F7F26]"
                      )}
                      title={stage.label}
                    />
                  );
                })}
              </div>

              {/* Loading indicator */}
              {status === "launching" && (
                <div className="flex items-center gap-2 font-mono text-xs text-[#555555]">
                  <Loader2 className="size-3 animate-spin" />
                  <span>Please wait, do not close the launcher...</span>
                </div>
              )}
            </div>
          </div>
        </motion.div>
      )}
    </AnimatePresence>
  );
}

// ---------------------------------------------------------------------------
// Demo Hook
// ---------------------------------------------------------------------------

export function useDemoLaunchProgress() {
  const [isVisible, setIsVisible] = useState(false);
  const [status, setStatus] = useState<LaunchStatus>("idle");
  const [currentStage, setCurrentStage] = useState<LaunchStage>("checking_java");
  const [progress, setProgress] = useState(0);

  const startLaunch = useCallback(() => {
    setIsVisible(true);
    setStatus("launching");
    setCurrentStage("checking_java");
    setProgress(0);
  }, []);

  const cancel = useCallback(() => {
    setStatus("cancelled");
  }, []);

  const dismiss = useCallback(() => {
    setIsVisible(false);
    setStatus("idle");
    setCurrentStage("checking_java");
    setProgress(0);
  }, []);

  useEffect(() => {
    if (status !== "launching") return;

    const stageIndex = LAUNCH_STAGES.findIndex((s) => s.stage === currentStage);
    const currentStageData = LAUNCH_STAGES[stageIndex];

    if (!currentStageData) return;

    const timer = setTimeout(() => {
      if (stageIndex < LAUNCH_STAGES.length - 1) {
        const nextStage = LAUNCH_STAGES[stageIndex + 1];
        setCurrentStage(nextStage.stage as LaunchStage);
        setProgress(nextStage.progress);
      } else {
        setStatus("success");
        setProgress(100);
      }
    }, 1500);

    return () => clearTimeout(timer);
  }, [status, currentStage]);

  return {
    isVisible,
    status,
    currentStage,
    progress,
    startLaunch,
    cancel,
    dismiss,
  };
}

export default LaunchProgressCard;