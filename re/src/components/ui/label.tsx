/**
 * Label Component
 *
 * Minecraft Block Brutalist design system.
 * Font-mono, text-text-primary.
 */

import * as LabelPrimitive from "@radix-ui/react-label";
import { cva, type VariantProps } from "class-variance-authority";
import type { ComponentPropsWithoutRef } from "react";
import { forwardRef } from "react";
import { cn } from "@/lib/utils";

const labelVariants = cva(
  [
    "font-mono text-sm font-semibold leading-none",
    "peer-disabled:cursor-not-allowed peer-disabled:opacity-50",
  ],
  {
    variants: {
      variant: {
        default: "text-text-primary",
        secondary: "text-text-secondary",
        error: "text-lava",
      },
    },
    defaultVariants: {
      variant: "default",
    },
  },
);

export interface LabelProps
  extends ComponentPropsWithoutRef<typeof LabelPrimitive.Root>,
    VariantProps<typeof labelVariants> {}

const Label = forwardRef<
  React.ComponentRef<typeof LabelPrimitive.Root>,
  LabelProps
>(({ className, variant, ...props }, ref) => (
  <LabelPrimitive.Root
    ref={ref}
    className={cn(labelVariants({ variant, className }))}
    {...props}
  />
));
Label.displayName = LabelPrimitive.Root.displayName;

export { Label, labelVariants };