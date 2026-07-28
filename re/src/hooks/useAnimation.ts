/**
 * Animation Utility Hooks
 *
 * Provides reusable framer-motion animation variants and hooks
 * for staggered animations, page transitions, scale-in, and
 * slide-in effects.
 */

import { useMemo } from "react";
import type { Variants, Transition, TargetAndTransition } from "framer-motion";

// ===========================================================================
// Types
// ===========================================================================

type Direction = "left" | "right" | "top" | "bottom";

// ===========================================================================
// Default Transition Presets
// ===========================================================================

const SPRING_TRANSITION: Transition = {
  type: "spring",
  stiffness: 300,
  damping: 30,
  mass: 1,
};

const EASE_TRANSITION: Transition = {
  type: "tween",
  ease: [0.4, 0, 0.2, 1] as [number, number, number, number],
  duration: 0.3,
};

const STAGGER_TRANSITION: Transition = {
  type: "spring",
  stiffness: 260,
  damping: 20,
};

// ===========================================================================
// useStaggeredAnimation
// ===========================================================================

/**
 * Returns staggered animation variants for a list of items.
 * Each item animates in sequence with the specified delay.
 *
 * @param delay - Delay between each item's animation (seconds)
 * @param count - Total number of items
 * @returns Variants with `hidden` and `visible` states
 */
export function useStaggeredAnimation(
  delay: number = 0.05,
  count: number = 10
): Variants {
  return useMemo(
    () => ({
      hidden: {
        opacity: 0,
        y: 12,
      },
      visible: (i: number = 0) => ({
        opacity: 1,
        y: 0,
        transition: {
          delay: Math.min(i, count - 1) * delay,
          ...STAGGER_TRANSITION,
        },
      }),
    }),
    [delay, count]
  );
}

// ===========================================================================
// usePageTransition
// ===========================================================================

/**
 * Returns page transition variants for enter/exit animations.
 * Use with AnimatePresence for route transitions.
 *
 * @returns Object with `enter` and `exit` variants
 */
export function usePageTransition(): {
  enter: TargetAndTransition;
  exit: TargetAndTransition;
} {
  return useMemo(
    () => ({
      enter: {
        opacity: 1,
        x: 0,
        transition: {
          duration: 0.25,
          ease: [0.4, 0, 0.2, 1] as [number, number, number, number],
        },
      },
      exit: {
        opacity: 0,
        x: -20,
        transition: {
          duration: 0.2,
          ease: [0.4, 0, 1, 1] as [number, number, number, number],
        },
      },
    }),
    []
  );
}

// ===========================================================================
// useScaleIn
// ===========================================================================

/**
 * Returns scale + fade in animation variants.
 * Element scales from 0.95 to 1 while fading in.
 *
 * @param duration - Animation duration in seconds (default: 0.3)
 * @returns Variants with `hidden` and `visible` states
 */
export function useScaleIn(duration: number = 0.3): Variants {
  return useMemo(
    () => ({
      hidden: {
        opacity: 0,
        scale: 0.95,
      },
      visible: {
        opacity: 1,
        scale: 1,
        transition: {
          duration,
          ease: [0.34, 1.56, 0.64, 1],
        },
      },
    }),
    [duration]
  );
}

// ===========================================================================
// useSlideIn
// ===========================================================================

/**
 * Returns slide-in animation variants from a given direction.
 * Element slides in from the specified direction while fading in.
 *
 * @param direction - Direction to slide in from
 * @param distance - Slide distance in pixels (default: 24)
 * @param duration - Animation duration in seconds (default: 0.3)
 * @returns Variants with `hidden` and `visible` states
 */
export function useSlideIn(
  direction: Direction = "left",
  distance: number = 24,
  duration: number = 0.3
): Variants {
  return useMemo(() => {
    const offsetMap: Record<Direction, { x?: number; y?: number }> = {
      left: { x: -distance },
      right: { x: distance },
      top: { y: -distance },
      bottom: { y: distance },
    };

    const offset = offsetMap[direction];

    return {
      hidden: {
        opacity: 0,
        ...offset,
      },
      visible: {
        opacity: 1,
        x: 0,
        y: 0,
        transition: {
          duration,
          ease: [0.4, 0, 0.2, 1],
        },
      },
    };
  }, [direction, distance, duration]);
}

// ===========================================================================
// useFadeIn
// ===========================================================================

/**
 * Simple fade-in animation variants.
 *
 * @param duration - Animation duration in seconds (default: 0.3)
 * @param delay - Delay before animation starts (default: 0)
 * @returns Variants with `hidden` and `visible` states
 */
export function useFadeIn(
  duration: number = 0.3,
  delay: number = 0
): Variants {
  return useMemo(
    () => ({
      hidden: {
        opacity: 0,
      },
      visible: {
        opacity: 1,
        transition: {
          duration,
          delay,
          ease: [0.4, 0, 0.2, 1],
        },
      },
    }),
    [duration, delay]
  );
}

// ===========================================================================
// useExpandCollapse
// ===========================================================================

/**
 * Returns expand/collapse animation variants for accordion-like content.
 *
 * @param duration - Animation duration in seconds (default: 0.3)
 * @returns Variants with `collapsed` and `expanded` states
 */
export function useExpandCollapse(duration: number = 0.3): Variants {
  return useMemo(
    () => ({
      collapsed: {
        height: 0,
        opacity: 0,
        overflow: "hidden",
        transition: {
          height: { duration, ease: [0.4, 0, 0.2, 1] },
          opacity: { duration: duration * 0.5, ease: "easeOut" },
        },
      },
      expanded: {
        height: "auto",
        opacity: 1,
        overflow: "hidden",
        transition: {
          height: { duration, ease: [0.4, 0, 0.2, 1] },
          opacity: { duration: duration * 0.5, delay: duration * 0.5, ease: "easeOut" },
        },
      },
    }),
    [duration]
  );
}

// ===========================================================================
// Hover/Tap Animation Presets
// ===========================================================================

/** Standard hover scale animation */
export const hoverScale = {
  whileHover: { scale: 1.05 },
  whileTap: { scale: 0.95 },
  transition: { type: "spring" as const, stiffness: 400, damping: 17 },
};

/** Subtle hover animation (for cards) */
export const hoverSubtle = {
  whileHover: { y: -2, transition: { duration: 0.2 } },
};

/** Hover animation for interactive icon buttons */
export const hoverIcon = {
  whileHover: { scale: 1.1, transition: { type: "spring" as const, stiffness: 400, damping: 17 } },
  whileTap: { scale: 0.9 },
};

// ===========================================================================
// Shared Transition Constants
// ===========================================================================

export { SPRING_TRANSITION, EASE_TRANSITION };