/**
 * Badge Component
 *
 * Minecraft Block Brutalist design system.
 * Sharp corners, font-mono, block shadow.
 * Variants: default (grass), secondary (stone), destructive (lava),
 *   success (emerald), warning (gold), info (water).
 */

import { cva, type VariantProps } from "class-variance-authority";
import type { HTMLAttributes } from "react";
import { forwardRef } from "react";
import { cn } from "@/lib/utils";

const badgeVariants = cva(
  [
    "inline-flex items-center gap-1.5 rounded-[2px] border-2 px-2.5 py-0.5",
    "font-mono text-xs font-semibold",
    "transition-[transform,box-shadow] duration-[150ms]",
    "shadow-[2px_2px_0px_rgba(0,0,0,0.3)]",
    "focus-visible:outline-none focus-visible:border-grass focus-visible:ring-2 focus-visible:ring-grass/40 focus-visible:ring-offset-2 focus-visible:ring-offset-bg-deepslate",
  ],
  {
    variants: {
      variant: {
        default:
          "border-grass-700 bg-grass-800 text-grass-100",
        secondary:
          "border-stone-600 bg-stone-800 text-text-secondary",
        destructive:
          "border-lava-700 bg-lava-800 text-lava-100",
        outline:
          "border-border-primary bg-transparent text-text-primary",
        success:
          "border-emerald-700 bg-emerald-800 text-emerald-100",
        warning:
          "border-gold-700 bg-gold-800 text-gold-100",
        info:
          "border-water-700 bg-water-800 text-water-100",
      },
    },
    defaultVariants: {
      variant: "default",
    },
  },
);

export interface BadgeProps
  extends HTMLAttributes<HTMLDivElement>,
    VariantProps<typeof badgeVariants> {}

const Badge = forwardRef<HTMLDivElement, BadgeProps>(
  ({ className, variant, ...props }, ref) => (
    <div
      ref={ref}
      className={cn(badgeVariants({ variant }), className)}
      {...props}
    />
  ),
);
Badge.displayName = "Badge";

export { Badge, badgeVariants };