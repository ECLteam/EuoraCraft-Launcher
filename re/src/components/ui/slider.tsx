/**
 * Slider Component
 *
 * Minecraft Block Brutalist design system.
 * Grass track, block shadow thumb, sharp corners.
 */

import * as SliderPrimitive from "@radix-ui/react-slider";
import type { ComponentPropsWithoutRef } from "react";
import { forwardRef } from "react";
import { cn } from "@/lib/utils";

const Slider = forwardRef<
  React.ComponentRef<typeof SliderPrimitive.Root>,
  ComponentPropsWithoutRef<typeof SliderPrimitive.Root>
>(({ className, ...props }, ref) => (
  <SliderPrimitive.Root
    ref={ref}
    className={cn(
      "relative flex w-full touch-none select-none items-center",
      className,
    )}
    {...props}
  >
    <SliderPrimitive.Track className="relative h-2 w-full grow overflow-hidden rounded-[2px] bg-bg-input border-2 border-stone-700 shadow-[inset_1px_1px_0px_rgba(0,0,0,0.25)]">
      <SliderPrimitive.Range className="absolute h-full bg-grass border-r-2 border-grass-700" />
    </SliderPrimitive.Track>
    <SliderPrimitive.Thumb className="block size-5 rounded-[2px] border-2 border-grass-700 bg-white shadow-[2px_2px_0px_rgba(0,0,0,0.4)] transition-[transform,box-shadow] duration-[150ms] hover:-translate-y-[1px] hover:shadow-[3px_3px_0px_rgba(0,0,0,0.4)] active:translate-y-0 active:shadow-[inset_2px_2px_0px_rgba(0,0,0,0.3)] focus-visible:outline-none focus-visible:border-grass focus-visible:ring-2 focus-visible:ring-grass/40 focus-visible:ring-offset-2 focus-visible:ring-offset-bg-deepslate disabled:pointer-events-none disabled:opacity-50" />
  </SliderPrimitive.Root>
));
Slider.displayName = SliderPrimitive.Root.displayName;

export { Slider };