/**
 * Button Component
 *
 * Minecraft Block Brutalist design system.
 * Variants: default (grass), destructive (lava), secondary (stone), ghost, link.
 * Block shadows, sharp corners, font-mono, snappy transitions.
 */

import * as React from "react";
import { Slot } from "@radix-ui/react-slot";
import { cva, type VariantProps } from "class-variance-authority";
import { cn } from "@/lib/utils";

// ---------------------------------------------------------------------------
// Variants
// ---------------------------------------------------------------------------

const buttonVariants = cva(
  [
    "inline-flex items-center justify-center gap-2 whitespace-nowrap",
    "font-mono text-sm font-semibold",
    "rounded-[2px] border-2",
    "transition-[transform,box-shadow] duration-[150ms]",
    "select-none cursor-pointer",
    "focus-visible:outline-none focus-visible:border-grass focus-visible:ring-2 focus-visible:ring-grass/40 focus-visible:ring-offset-2 focus-visible:ring-offset-bg-deepslate",
    "disabled:pointer-events-none disabled:cursor-not-allowed disabled:opacity-50 disabled:shadow-none disabled:translate-y-0",
    "[&_svg]:pointer-events-none [&_svg]:size-4 [&_svg]:shrink-0",
  ],
  {
    variants: {
      variant: {
        default: [
          "bg-grass text-white border-grass-700",
          "shadow-[2px_2px_0px_rgba(0,0,0,0.4)]",
          "hover:bg-grass-400 hover:border-grass-600 hover:-translate-y-[1px] hover:shadow-[3px_3px_0px_rgba(0,0,0,0.4)]",
          "active:bg-grass-700 active:border-grass-800 active:translate-y-0 active:shadow-[inset_3px_3px_0px_rgba(0,0,0,0.4)]",
        ],
        destructive: [
          "bg-lava text-white border-lava-700",
          "shadow-[2px_2px_0px_rgba(0,0,0,0.4)]",
          "hover:bg-lava-400 hover:border-lava-600 hover:-translate-y-[1px] hover:shadow-[3px_3px_0px_rgba(0,0,0,0.4)]",
          "active:bg-lava-700 active:border-lava-800 active:translate-y-0 active:shadow-[inset_3px_3px_0px_rgba(0,0,0,0.4)]",
        ],
        secondary: [
          "bg-stone-800 text-text-primary border-stone-600",
          "shadow-[2px_2px_0px_rgba(0,0,0,0.4)]",
          "hover:bg-stone-700 hover:border-stone-500 hover:-translate-y-[1px] hover:shadow-[3px_3px_0px_rgba(0,0,0,0.4)]",
          "active:bg-stone-900 active:border-stone-700 active:translate-y-0 active:shadow-[inset_3px_3px_0px_rgba(0,0,0,0.4)]",
        ],
        ghost: [
          "bg-transparent text-text-secondary border-transparent",
          "hover:text-text-primary hover:bg-bg-elevated hover:border-border-stone hover:shadow-[2px_2px_0px_rgba(0,0,0,0.4)]",
          "active:bg-bg-overlay active:shadow-[inset_2px_2px_0px_rgba(0,0,0,0.3)]",
        ],
        link: [
          "bg-transparent text-water border-transparent",
          "underline-offset-[3px] hover:underline hover:text-water-300",
          "shadow-none",
        ],
      },
      size: {
        default: "h-9 px-4 py-2",
        sm: "h-8 px-3 text-xs",
        lg: "h-10 px-6 text-base",
        icon: "h-9 w-9",
      },
    },
    defaultVariants: {
      variant: "default",
      size: "default",
    },
  }
);

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

export interface ButtonProps
  extends React.ButtonHTMLAttributes<HTMLButtonElement>,
    VariantProps<typeof buttonVariants> {
  asChild?: boolean;
  loading?: boolean;
}

// ---------------------------------------------------------------------------
// Component
// ---------------------------------------------------------------------------

const Button = React.forwardRef<HTMLButtonElement, ButtonProps>(
  ({ className, variant, size, asChild = false, loading, disabled, children, ...props }, ref) => {
    const Comp = asChild ? Slot : "button";

    return (
      <Comp
        className={cn(buttonVariants({ variant, size, className }))}
        ref={ref}
        disabled={disabled || loading}
        {...props}
      >
        {loading && (
          <svg
            className="animate-block-spin -ml-1 size-4"
            xmlns="http://www.w3.org/2000/svg"
            fill="none"
            viewBox="0 0 24 24"
          >
            <circle
              className="opacity-25"
              cx="12"
              cy="12"
              r="10"
              stroke="currentColor"
              strokeWidth="4"
            />
            <path
              className="opacity-75"
              fill="currentColor"
              d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z"
            />
          </svg>
        )}
        {children}
      </Comp>
    );
  }
);

Button.displayName = "Button";

// ---------------------------------------------------------------------------
// Exports
// ---------------------------------------------------------------------------

export { Button, buttonVariants };