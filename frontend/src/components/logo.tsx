import { cn } from "@/lib/utils";

export function LogoMark({ className }: { className?: string }) {
  return (
    <span
      className={cn(
        "relative inline-flex size-8 shrink-0 items-center justify-center overflow-hidden rounded-[10px] bg-lime text-[#111507] shadow-[0_0_24px_-6px_rgba(216,255,99,0.5)]",
        className,
      )}
    >
      <svg viewBox="0 0 24 24" className="size-5" fill="none" aria-hidden>
        <path d="M7.2 4.8v14.4" stroke="currentColor" strokeWidth="2" strokeLinecap="round" />
        <path d="M17.6 5.4 8.8 9.6l8.8 4.2" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" />
        <circle cx="17.6" cy="5.4" r="1.9" fill="currentColor" />
        <circle cx="17.6" cy="13.8" r="1.9" fill="currentColor" />
      </svg>
    </span>
  );
}

export function Logo({ compact = false }: { compact?: boolean }) {
  return (
    <span className="inline-flex items-center gap-2.5">
      <LogoMark />
      {!compact ? (
        <span className="flex flex-col leading-none">
          <span className="text-[15px] font-semibold tracking-[-0.03em] text-mist">ClipMind</span>
          <span className="mt-1 font-mono text-[9px] uppercase tracking-[0.22em] text-faint">
            content studio
          </span>
        </span>
      ) : null}
    </span>
  );
}
