/**
 * Popover Component
 *
 * Minecraft Block Brutalist design system.
 * Border-2, bg-surface, block shadow, sharp corners. No glass.
 */

import * as PopoverPrimitive from "@radix-ui/react-popover";
import type { ComponentPropsWithoutRef } from "react";
import { forwardRef } from "react";
import { cn } from "@/lib/utils";

const Popover = PopoverPrimitive.Root;
const PopoverTrigger = PopoverPrimitive.Trigger;

const PopoverContent = forwardRef<
  React.ComponentRef<typeof PopoverPrimitive.Content>,
  ComponentPropsWithoutRef<typeof PopoverPrimitive.Content>
>(({ className, align = "center", sideOffset = 4, ...props }, ref) => (
  <PopoverPrimitive.Portal>
    <PopoverPrimitive.Content
      ref={ref}
      align={align}
      sideOffset={sideOffset}
      className={cn(
        "z-popover w-72 rounded-[2px]",
        "border-2 border-stone-600 bg-bg-surface",
        "p-4 shadow-[4px_4px_0px_rgba(0,0,0,0.3)]",
        "text-text-primary outline-none",
        "data-[state=open]:animate-block-place",
        "data-[state=closed]:animate-block-break",
        "data-[side=bottom]:animate-block-slide-in-top",
        "data-[side=left]:animate-block-slide-in-right",
        "data-[side=right]:animate-block-slide-in-left",
        "data-[side=top]:animate-block-slide-in-bottom",
        className,
      )}
      {...props}
    />
  </PopoverPrimitive.Portal>
));
PopoverContent.displayName = PopoverPrimitive.Content.displayName;

export { Popover, PopoverTrigger, PopoverContent };