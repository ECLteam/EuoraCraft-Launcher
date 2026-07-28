/**
 * Progress Component
 *
 * Minecraft Block Brutalist design system.
 * Grass fill, block shadow, sharp corners.
 */

import * as ProgressPrimitive from "@radix-ui/react-progress";
import type { ComponentPropsWithoutRef } from "react";
import { forwardRef } from "react";
import { cn } from "@/lib/utils";

const Progress = forwardRef<
  React.ComponentRef<typeof ProgressPrimitive.Root>,
  ComponentPropsWithoutRef<typeof ProgressPrimitive.Root>
>(({ className, value, ...props }, ref) => (
  <ProgressPrimitive.Root
    ref={ref}
    className={cn(
      "relative h-3 w-full overflow-hidden rounded-[2px]",
      "bg-bg-input border-2 border-stone-700",
      "shadow-[inset_1px_1px_0px_rgba(0,0,0,0.25)]",
      className,
    )}
    {...props}
  >
    <ProgressPrimitive.Indicator
      className="size-full flex-1 rounded-[1px] bg-grass border-r-2 border-grass-700 shadow-[2px_0px_0px_rgba(0,0,0,0.2)] transition-all duration-[300ms]"
      style={{ transform: `translateX(-${100 - (value ?? 0)}%)` }}
    />
  </ProgressPrimitive.Root>
));
Progress.displayName = ProgressPrimitive.Root.displayName;

export { Progress };