/**
 * Switch Component
 *
 * Minecraft Block Brutalist design system.
 * Grass active color, block shadow, sharp corners.
 */

import * as SwitchPrimitive from "@radix-ui/react-switch";
import type { ComponentPropsWithoutRef } from "react";
import { forwardRef } from "react";
import { cn } from "@/lib/utils";

const Switch = forwardRef<
  React.ComponentRef<typeof SwitchPrimitive.Root>,
  ComponentPropsWithoutRef<typeof SwitchPrimitive.Root>
>(({ className, ...props }, ref) => (
  <SwitchPrimitive.Root
    className={cn(
      "peer inline-flex h-[24px] w-[44px] shrink-0 cursor-pointer items-center",
      "rounded-[2px] border-2 border-stone-600",
      "bg-bg-input shadow-[inset_1px_1px_0px_rgba(0,0,0,0.25)]",
      "transition-[background-color,border-color,box-shadow] duration-[150ms]",
      "focus-visible:outline-none focus-visible:border-grass focus-visible:ring-2 focus-visible:ring-grass/40 focus-visible:ring-offset-2 focus-visible:ring-offset-bg-deepslate",
      "disabled:cursor-not-allowed disabled:opacity-50",
      "data-[state=checked]:bg-grass data-[state=checked]:border-grass-700 data-[state=checked]:shadow-[0_0_0px_2px_rgba(91,135,49,0.4)]",
      className,
    )}
    {...props}
    ref={ref}
  >
    <SwitchPrimitive.Thumb
      className={cn(
        "pointer-events-none block size-[18px] rounded-[2px]",
        "bg-white shadow-[2px_2px_0px_rgba(0,0,0,0.3)]",
        "transition-transform duration-[150ms]",
        "translate-x-0",
        "data-[state=checked]:translate-x-[20px]",
      )}
    />
  </SwitchPrimitive.Root>
));
Switch.displayName = SwitchPrimitive.Root.displayName;

export { Switch };