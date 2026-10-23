"use client";

import { forwardRef } from "react";
import { Loader2 } from "lucide-react";
import { cn } from "@/lib/utils";

type Variant = "primary" | "secondary" | "ghost" | "danger" | "outline" | "subtle";
type Size = "sm" | "md" | "lg" | "icon" | "icon-sm";

const variants: Record<Variant, string> = {
  primary:
    "bg-lime text-[#111507] hover:bg-[#e4ff8a] active:bg-lime-deep shadow-[0_10px_30px_-12px_rgba(216,255,99,0.55)]",
  secondary:
    "bg-raised text-mist border border-line hover:border-[#3a4135] hover:bg-elevated",
  ghost: "text-muted hover:text-mist hover:bg-white/[0.055]",
  danger:
    "bg-danger/10 text-danger border border-danger/25 hover:bg-danger/15 hover:border-danger/40",
  outline:
    "border border-line bg-transparent text-mist hover:border-[#3a4135] hover:bg-white/[0.035]",
  subtle: "bg-white/[0.055] text-mist hover:bg-white/[0.09]",
};

const sizes: Record<Size, string> = {
  sm: "h-8 px-3 text-[12.5px] gap-1.5 rounded-lg",
  md: "h-10 px-4 text-[13.5px] gap-2 rounded-xl",
  lg: "h-12 px-5 text-sm gap-2.5 rounded-xl",
  icon: "h-10 w-10 rounded-xl",
  "icon-sm": "h-8 w-8 rounded-lg",
};

export interface ButtonProps extends React.ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: Variant;
  size?: Size;
  loading?: boolean;
}

export const Button = forwardRef<HTMLButtonElement, ButtonProps>(function Button(
  { className, variant = "secondary", size = "md", loading = false, disabled, children, ...props },
  ref,
) {
  return (
    <button
      ref={ref}
      disabled={disabled || loading}
      className={cn(
        "inline-flex select-none items-center justify-center whitespace-nowrap font-medium tracking-[-0.01em] transition-all duration-150 disabled:pointer-events-none disabled:opacity-45",
        variants[variant],
        sizes[size],
        className,
      )}
      {...props}
    >
      {loading ? <Loader2 className="size-4 animate-spin" aria-hidden /> : null}
      {children}
    </button>
  );
});

export function IconButton({
  label,
  className,
  size = "icon",
  ...props
}: ButtonProps & { label: string }) {
  return (
    <Button aria-label={label} title={label} size={size} className={className} {...props} />
  );
}
