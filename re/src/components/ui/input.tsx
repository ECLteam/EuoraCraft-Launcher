/**
 * Input Component
 *
 * Minecraft Block Brutalist design system.
 * Border-2, bg-input, focus:border-grass, font-mono, sharp corners.
 */

import type { InputHTMLAttributes } from "react";
import { forwardRef } from "react";
import { cn } from "@/lib/utils";

export interface InputProps extends InputHTMLAttributes<HTMLInputElement> {
  error?: boolean;
}

const Input = forwardRef<HTMLInputElement, InputProps>(
  ({ className, type, error, ...props }, ref) => {
    return (
      <input
        type={type}
        className={cn(
          "flex h-10 w-full rounded-[2px] border-2 border-border-stone",
          "bg-bg-input px-3 py-2 font-mono text-sm",
          "text-text-primary placeholder:text-text-tertiary",
          "shadow-[inset_1px_1px_0px_rgba(0,0,0,0.25)]",
          "transition-[border-color,box-shadow] duration-[150ms]",
          "file:border-0 file:bg-transparent file:font-mono file:text-sm file:font-medium file:text-text-primary",
          "hover:border-stone-600",
          "focus:border-grass focus:outline-none focus:shadow-[inset_1px_1px_0px_rgba(0,0,0,0.25),0_0_0px_2px_rgba(91,135,49,0.4)]",
          "disabled:cursor-not-allowed disabled:opacity-50 disabled:bg-bg-base disabled:border-border-secondary",
          error &&
            "border-lava focus:border-lava focus:shadow-[inset_1px_1px_0px_rgba(0,0,0,0.25),0_0_0px_2px_rgba(255,85,0,0.4)]",
          className,
        )}
        ref={ref}
        {...props}
      />
    );
  },
);
Input.displayName = "Input";

export { Input };