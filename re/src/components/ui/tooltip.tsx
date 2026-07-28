/**
 * Tooltip Component
 *
 * Minecraft Block Brutalist design system.
 * Border-2, bg-surface, block shadow, font-mono, sharp corners. No glass.
 */

import * as React from "react";
import * as TooltipPrimitive from "@radix-ui/react-tooltip";
import { cn } from "@/lib/utils";

const TooltipProvider = TooltipPrimitive.Provider;

const Tooltip = TooltipPrimitive.Root;

const TooltipTrigger = TooltipPrimitive.Trigger;

const TooltipContent = React.forwardRef<
  React.ComponentRef<typeof TooltipPrimitive.Content>,
  React.ComponentPropsWithoutRef<typeof TooltipPrimitive.Content>
>(({ className, sideOffset = 4, ...props }, ref) => (
  <TooltipPrimitive.Portal>
    <TooltipPrimitive.Content
      ref={ref}
      sideOffset={sideOffset}
      className={cn(
        "z-tooltip overflow-hidden rounded-[2px]",
        "border-2 border-stone-600 bg-bg-surface",
        "px-3 py-1.5 font-mono text-xs text-text-primary",
        "shadow-[4px_4px_0px_rgba(0,0,0,0.3)]",
        "animate-block-fade-in",
        "data-[state=closed]:animate-block-fade-out",
        "data-[side=bottom]:animate-block-slide-in-top",
        "data-[side=left]:animate-block-slide-in-right",
        "data-[side=right]:animate-block-slide-in-left",
        "data-[side=top]:animate-block-slide-in-bottom",
        className
      )}
      {...props}
    />
  </TooltipPrimitive.Portal>
));

TooltipContent.displayName = TooltipPrimitive.Content.displayName;

export { Tooltip, TooltipTrigger, TooltipContent, TooltipProvider };