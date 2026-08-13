import { cva, type VariantProps } from "class-variance-authority";
import clsx, { type ClassValue } from "clsx";

export function cx(...inputs: ClassValue[]) {
  return clsx(inputs);
}

export const buttonVariants = cva(
  "press inline-flex items-center justify-center gap-2 rounded-xl font-semibold transition-colors disabled:cursor-not-allowed disabled:opacity-40",
  {
    variants: {
      intent: {
        primary: "bg-foreground text-background hover:opacity-90",
        ghost:
          "border border-border-strong bg-surface text-foreground-muted hover:border-foreground-subtle hover:text-foreground",
        icon: "border border-border bg-surface text-foreground-muted hover:text-foreground",
      },
      size: {
        default: "h-10 px-4 text-[13.5px]",
        compact: "h-8 px-3 text-xs",
        icon: "size-8 p-0",
      },
    },
    defaultVariants: {
      intent: "primary",
      size: "default",
    },
  },
);

export type ButtonVariantProps = VariantProps<typeof buttonVariants>;
