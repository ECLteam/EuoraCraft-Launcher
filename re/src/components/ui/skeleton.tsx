/**
 * Skeleton Component
 *
 * Minecraft Block Brutalist design system.
 * Bg-stone, sharp corners, blocky pulse animation.
 */

import type { HTMLAttributes } from "react";
import { forwardRef } from "react";
import { cn } from "@/lib/utils";

const Skeleton = forwardRef<HTMLDivElement, HTMLAttributes<HTMLDivElement>>(
  ({ className, ...props }, ref) => (
    <div
      ref={ref}
      className={cn(
        "relative overflow-hidden rounded-[2px] bg-stone-800",
        "animate-progress-pulse",
        className,
      )}
      {...props}
    />
  ),
);
Skeleton.displayName = "Skeleton";

export { Skeleton };