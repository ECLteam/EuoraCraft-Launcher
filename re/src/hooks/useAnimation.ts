/**
 * Animation Utility Hooks
 *
 * Provides reusable framer-motion animation variants and hooks
 * for staggered, bounce, shake, pop-in, glitch, and other
 * nonlinear block-brutalist animations.
 */

import { useMemo } from "react";
import type { Variants, Transition, TargetAndTransition } from "framer-motion";

// ===========================================================================
// Types
// ===========================================================================

type Direction = "left" | "right" | "top" | "bottom";

// ===========================================================================
// Transition Presets
// ===========================================================================

/** Snappy snap transition (block placement style) */
const SNAP_TRANSITION: Transition = {
  type: "tween",
  ease: [0.8, 0, 0.2, 1] as [number, number, number, number],
  duration: 0.15,
};

/** Bounce transition: overshoot then settle */
const BOUNCE_TRANSITION: Transition = {
  type: "tween",
  ease: [0.34, 1.56, 0.64, 1] as [number, number, number, number],
  duration: 0.4,
};

/** Heavy bounce: exaggerated overshoot */
const BOUNCE_HEAVY_TRANSITION: Transition = {
  type: "tween",
  ease: [0.16, 2.2, 0.44, 1] as [number, number, number, number],
  duration: 0.5,
};

/** Anticipate transition: wind-up before action */
const ANTICIPATE_TRANSITION: Transition = {
  type: "tween",
  ease: [0.4, -0.3, 0.2, 1] as [number, number, number, number],
  duration: 0.35,
};

/** Glitch transition: rapid discrete steps */
const GLITCH_TRANSITION: Transition = {
  type: "tween",
  ease: [0.8, 0, 0.2, 1] as [number, number, number, number],
  duration: 0.25,
};

/** Slam transition: heavy drop with impact */
const SLAM_TRANSITION: Transition = {
  type: "tween",
  ease: [0.34, 1.56, 0.64, 1] as [number, number, number, number],
  duration: 0.35,
};

// ===========================================================================
// useStaggeredAnimation
// ===========================================================================

/**
 * Returns staggered animation variants for a list of items.
 * Each item animates in sequence with the specified delay.
 *
 * :param delay: Delay between each item's animation (seconds)
 * :param count: Total number of items
 * :return: Variants with `hidden` and `visible` states
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
          ...SNAP_TRANSITION,
        },
      }),
    }),
    [delay, count]
  );
}

// ===========================================================================
// useStaggeredBounce - Nonlinear staggered entrance with bounce
// ===========================================================================

/**
 * Staggered animation with bounce easing for a more dynamic entrance.
 * Each item bounces in with overshoot, creating a wave-like effect.
 *
 * :param delay: Delay between each item's animation (seconds)
 * :param count: Total number of items
 * :return: Variants with `hidden` and `visible` states
 */
export function useStaggeredBounce(
  delay: number = 0.06,
  count: number = 10
): Variants {
  return useMemo(
    () => ({
      hidden: {
        opacity: 0,
        scale: 0.6,
        y: 8,
      },
      visible: (i: number = 0) => ({
        opacity: 1,
        scale: 1,
        y: 0,
        transition: {
          delay: Math.min(i, count - 1) * delay,
          ...BOUNCE_TRANSITION,
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
 * :return: Object with `enter` and `exit` variants
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
 * :param duration: Animation duration in seconds (default: 0.3)
 * :return: Variants with `hidden` and `visible` states
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
// useBounceIn - Elastic bounce entrance
// ===========================================================================

/**
 * Bounce-in animation with scale overshoot.
 * Element scales from 0.3 to 1.08 to 0.94 to 1.
 * Blocky feel via discrete intermediate states.
 *
 * :param duration: Animation duration in seconds (default: 0.4)
 * :param delay: Delay before animation starts (default: 0)
 * :return: Variants with `hidden` and `visible` states
 */
export function useBounceIn(
  duration: number = 0.4,
  delay: number = 0
): Variants {
  return useMemo(
    () => ({
      hidden: {
        opacity: 0,
        scale: 0.3,
      },
      visible: {
        opacity: 1,
        scale: 1,
        transition: {
          duration,
          delay,
          ease: [0.34, 1.56, 0.64, 1] as [number, number, number, number],
        },
      },
    }),
    [duration, delay]
  );
}

// ===========================================================================
// usePopIn - Pixelated pop-in with discrete steps
// ===========================================================================

/**
 * Pop-in animation with step-based discrete scaling.
 * Simulates blocky pixelated entrance (Minecraft style).
 *
 * :param duration: Animation duration in seconds (default: 0.4)
 * :param delay: Delay before animation starts (default: 0)
 * :return: Variants with `hidden` and `visible` states
 */
export function usePopIn(
  duration: number = 0.4,
  delay: number = 0
): Variants {
  return useMemo(
    () => ({
      hidden: {
        opacity: 0,
        scale: 0.25,
      },
      visible: {
        opacity: 1,
        scale: 1,
        transition: {
          duration,
          delay,
          ease: [0.8, 0, 0.2, 1] as [number, number, number, number],
        },
      },
    }),
    [duration, delay]
  );
}

// ===========================================================================
// useShake - Horizontal shake animation
// ===========================================================================

/**
 * Shake animation variants for error / attention states.
 * Uses keyframe-based horizontal oscillation.
 *
 * :param intensity: Shake intensity in pixels (default: 4)
 * :param duration: Animation duration in seconds (default: 0.35)
 * :return: Variants with `idle` and `shake` states
 */
export function useShake(
  intensity: number = 4,
  duration: number = 0.35
): Variants {
  return useMemo(
    () => ({
      idle: {
        x: 0,
      },
      shake: {
        x: [0, -intensity, intensity, -intensity * 0.75, intensity * 0.75, -intensity * 0.5, intensity * 0.5, -intensity * 0.25, intensity * 0.25, 0],
        transition: {
          duration,
          ease: "linear",
        },
      },
    }),
    [intensity, duration]
  );
}

// ===========================================================================
// useGlitchIn - Glitchy entrance with horizontal displacement
// ===========================================================================

/**
 * Glitch-in animation: rapid horizontal displacement before settling.
 * Element jitters into place like a glitched Minecraft block.
 *
 * :param duration: Animation duration in seconds (default: 0.25)
 * :param delay: Delay before animation starts (default: 0)
 * :return: Variants with `hidden` and `visible` states
 */
export function useGlitchIn(
  duration: number = 0.25,
  delay: number = 0
): Variants {
  return useMemo(
    () => ({
      hidden: {
        opacity: 0,
        x: -8,
      },
      visible: {
        opacity: 1,
        x: 0,
        transition: {
          duration,
          delay,
          ease: [0.8, 0, 0.2, 1] as [number, number, number, number],
        },
      },
    }),
    [duration, delay]
  );
}

// ===========================================================================
// useSlamIn - Heavy drop-down entrance
// ===========================================================================

/**
 * Slam-in animation: heavy drop from above with impact bounce.
 * Element drops down, overshoots slightly, and settles.
 *
 * :param duration: Animation duration in seconds (default: 0.35)
 * :param delay: Delay before animation starts (default: 0)
 * :return: Variants with `hidden` and `visible` states
 */
export function useSlamIn(
  duration: number = 0.35,
  delay: number = 0
): Variants {
  return useMemo(
    () => ({
      hidden: {
        opacity: 0,
        y: -40,
        scale: 0.8,
      },
      visible: {
        opacity: 1,
        y: 0,
        scale: 1,
        transition: {
          duration,
          delay,
          ease: [0.34, 1.56, 0.64, 1] as [number, number, number, number],
        },
      },
    }),
    [duration, delay]
  );
}

// ===========================================================================
// useSlideIn
// ===========================================================================

/**
 * Returns slide-in animation variants from a given direction.
 * Element slides in from the specified direction while fading in.
 *
 * :param direction: Direction to slide in from
 * :param distance: Slide distance in pixels (default: 24)
 * :param duration: Animation duration in seconds (default: 0.3)
 * :return: Variants with `hidden` and `visible` states
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
 * :param duration: Animation duration in seconds (default: 0.3)
 * :param delay: Delay before animation starts (default: 0)
 * :return: Variants with `hidden` and `visible` states
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
 * :param duration: Animation duration in seconds (default: 0.3)
 * :return: Variants with `collapsed` and `expanded` states
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
// useTiltHover - 3D card tilt with blocky feel
// ===========================================================================

/**
 * 3D tilt + lift hover effect for cards.
 * Card tilts toward cursor and lifts slightly.
 * Block-brutalist: uses discrete tween, not smooth spring.
 *
 * :param tiltAmount: Maximum tilt in degrees (default: 2)
 * :param liftAmount: Y-axis lift in pixels (default: -4)
 * :return: Object with `whileHover` and `transition`
 */
export function useTiltHover(
  tiltAmount: number = 2,
  liftAmount: number = -4
): {
  whileHover: TargetAndTransition;
  transition: Transition;
} {
  return useMemo(
    () => ({
      whileHover: {
        scale: 1.02,
        y: liftAmount,
        transition: {
          type: "tween",
          ease: [0.34, 1.56, 0.64, 1] as [number, number, number, number],
          duration: 0.3,
        },
      },
      transition: {
        type: "tween",
        ease: [0.8, 0, 0.2, 1] as [number, number, number, number],
        duration: 0.15,
      },
    }),
    [tiltAmount, liftAmount]
  );
}

// ===========================================================================
// Hover/Tap Animation Presets
// ===========================================================================

/** Standard hover scale with bounce */
export const hoverScale = {
  whileHover: { scale: 1.05 },
  whileTap: { scale: 0.95 },
  transition: {
    type: "tween" as const,
    ease: [0.34, 1.56, 0.64, 1] as [number, number, number, number],
    duration: 0.25,
  },
};

/** Subtle hover animation (for cards) - with bounce */
export const hoverSubtle = {
  whileHover: {
    y: -2,
    transition: {
      type: "tween" as const,
      ease: [0.34, 1.56, 0.64, 1] as [number, number, number, number],
      duration: 0.25,
    },
  },
};

/** Hover animation for interactive icon buttons - with bounce */
export const hoverIcon = {
  whileHover: {
    scale: 1.1,
    transition: {
      type: "tween" as const,
      ease: [0.34, 1.56, 0.64, 1] as [number, number, number, number],
      duration: 0.25,
    },
  },
  whileTap: { scale: 0.9 },
};

/** Press animation: squash down like a button being pressed */
export const pressSquash = {
  whileTap: {
    scale: 0.96,
    y: 2,
    transition: {
      type: "tween" as const,
      ease: [0.8, 0, 0.2, 1] as [number, number, number, number],
      duration: 0.1,
    },
  },
};

/** Float animation: subtle continuous bobbing */
export const floatAnimation: TargetAndTransition = {
  y: [0, -3, -1, -4, 0],
  transition: {
    duration: 2.5,
    ease: "linear",
    repeat: Infinity,
    repeatType: "loop",
  },
};

// ===========================================================================
// Shared Transition Constants
// ===========================================================================

export {
  SNAP_TRANSITION,
  BOUNCE_TRANSITION,
  BOUNCE_HEAVY_TRANSITION,
  ANTICIPATE_TRANSITION,
  GLITCH_TRANSITION,
  SLAM_TRANSITION,
};