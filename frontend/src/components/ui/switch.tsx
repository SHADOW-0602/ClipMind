"use client";

import { cn } from "@/lib/utils";

export function Switch({
  checked,
  onCheckedChange,
  disabled,
  label,
  description,
  id,
}: {
  checked: boolean;
  onCheckedChange: (checked: boolean) => void;
  disabled?: boolean;
  label?: string;
  description?: string;
  id?: string;
}) {
  const button = (
    <button
      id={id}
      type="button"
      role="switch"
      aria-checked={checked}
      disabled={disabled}
      onClick={() => onCheckedChange(!checked)}
      className={cn(
        "relative inline-flex h-6 w-10 shrink-0 items-center rounded-full border transition-colors duration-200 disabled:opacity-40",
        checked ? "border-lime/40 bg-lime/90" : "border-line bg-raised",
      )}
    >
      <span
        className={cn(
          "pointer-events-none block size-4 rounded-full shadow-sm transition-transform duration-200",
          checked ? "translate-x-[19px] bg-[#111507]" : "translate-x-[3px] bg-muted",
        )}
      />
    </button>
  );

  if (!label) return button;

  return (
    <div className="flex items-start justify-between gap-4">
      <div className="space-y-0.5">
        <label htmlFor={id} className="text-[13px] font-medium text-mist">
          {label}
        </label>
        {description ? <p className="text-[12px] leading-relaxed text-muted">{description}</p> : null}
      </div>
      {button}
    </div>
  );
}
