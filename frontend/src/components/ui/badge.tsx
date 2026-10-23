import { cn } from "@/lib/utils";

type Tone =
  | "neutral"
  | "lime"
  | "success"
  | "warning"
  | "danger"
  | "sky"
  | "outline";

const tones: Record<Tone, string> = {
  neutral: "bg-white/[0.06] text-muted border-transparent",
  lime: "bg-lime/12 text-lime border-lime/20",
  success: "bg-[#93e06b]/10 text-[#b8ec9b] border-[#93e06b]/20",
  warning: "bg-warning/10 text-warning border-warning/20",
  danger: "bg-danger/10 text-danger border-danger/20",
  sky: "bg-sky/10 text-sky border-sky/20",
  outline: "bg-transparent text-muted border-line",
};

export function Badge({
  tone = "neutral",
  className,
  children,
  ...props
}: React.HTMLAttributes<HTMLSpanElement> & { tone?: Tone }) {
  return (
    <span
      className={cn(
        "inline-flex items-center gap-1.5 rounded-full border px-2.5 py-0.5 text-[11px] font-medium leading-5 tracking-[0.01em]",
        tones[tone],
        className,
      )}
      {...props}
    >
      {children}
    </span>
  );
}

export function Dot({ className }: { className?: string }) {
  return <span className={cn("size-1.5 rounded-full bg-current", className)} />;
}
