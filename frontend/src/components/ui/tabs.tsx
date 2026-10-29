"use client";

import { useRef } from "react";
import { cn } from "@/lib/utils";

export interface TabItem {
  value: string;
  label: string;
  count?: number;
  icon?: React.ReactNode;
}

export function Tabs({
  items,
  value,
  onValueChange,
  className,
  size = "md",
}: {
  items: TabItem[];
  value: string;
  onValueChange: (value: string) => void;
  className?: string;
  size?: "sm" | "md";
}) {
  const tabRefs = useRef<Array<HTMLButtonElement | null>>([]);

  return (
    <div
      role="tablist"
      className={cn(
        "inline-flex items-center gap-1 rounded-xl border border-line bg-void/70 p-1",
        className,
      )}
    >
      {items.map((item, index) => {
        const active = item.value === value;
        return (
          <button
            key={item.value}
            ref={(node) => {
              tabRefs.current[index] = node;
            }}
            type="button"
            role="tab"
            aria-selected={active}
            tabIndex={active ? 0 : -1}
            onClick={() => onValueChange(item.value)}
            onKeyDown={(event) => {
              let nextIndex: number | null = null;
              if (event.key === "ArrowRight") nextIndex = (index + 1) % items.length;
              if (event.key === "ArrowLeft") nextIndex = (index - 1 + items.length) % items.length;
              if (event.key === "Home") nextIndex = 0;
              if (event.key === "End") nextIndex = items.length - 1;
              if (nextIndex === null) return;
              event.preventDefault();
              tabRefs.current[nextIndex]?.focus();
              onValueChange(items[nextIndex].value);
            }}
            className={cn(
              "inline-flex min-h-11 items-center gap-1.5 whitespace-nowrap rounded-lg font-medium transition-all",
              size === "sm" ? "px-2.5 text-[11.5px]" : "px-3 text-[12.5px]",
              active
                ? "bg-raised text-mist shadow-sm"
                : "text-muted hover:bg-white/[0.04] hover:text-mist",
            )}
          >
            {item.icon}
            {item.label}
            {typeof item.count === "number" ? (
              <span
                className={cn(
                  "rounded-md px-1.5 py-0.5 text-[10px] tabular-nums",
                  active ? "bg-white/[0.08] text-muted" : "bg-white/[0.04] text-faint",
                )}
              >
                {item.count}
              </span>
            ) : null}
          </button>
        );
      })}
    </div>
  );
}
