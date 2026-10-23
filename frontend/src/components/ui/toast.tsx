"use client";

import { createContext, useCallback, useContext, useEffect, useMemo, useState } from "react";
import { AlertTriangle, CheckCircle2, Info, X } from "lucide-react";
import { cn } from "@/lib/utils";

type ToastTone = "success" | "error" | "info";

interface ToastItem {
  id: number;
  title: string;
  description?: string;
  tone: ToastTone;
}

interface ToastContextValue {
  toast: (input: { title: string; description?: string; tone?: ToastTone }) => void;
}

const ToastContext = createContext<ToastContextValue | null>(null);

const icons = {
  success: CheckCircle2,
  error: AlertTriangle,
  info: Info,
};

const accents: Record<ToastTone, string> = {
  success: "text-lime",
  error: "text-danger",
  info: "text-sky",
};

export function ToastProvider({ children }: { children: React.ReactNode }) {
  const [items, setItems] = useState<ToastItem[]>([]);

  const toast = useCallback(
    ({
      title,
      description,
      tone = "info",
    }: {
      title: string;
      description?: string;
      tone?: ToastTone;
    }) => {
      const id = Date.now() + Math.random();
      setItems((current) => [...current.slice(-2), { id, title, description, tone }]);
      window.setTimeout(() => {
        setItems((current) => current.filter((item) => item.id !== id));
      }, 5200);
    },
    [],
  );

  const value = useMemo(() => ({ toast }), [toast]);

  return (
    <ToastContext.Provider value={value}>
      {children}
      <div
        aria-live="polite"
        className="pointer-events-none fixed inset-x-0 bottom-4 z-[100] flex flex-col items-center gap-2 px-4 sm:bottom-6 sm:left-auto sm:right-6 sm:items-end"
      >
        {items.map((item) => {
          const Icon = icons[item.tone];
          return (
            <div
              key={item.id}
              className="animate-in pointer-events-auto flex w-full max-w-sm items-start gap-3 rounded-xl border border-line bg-[#121512]/95 p-3.5 shadow-[0_20px_60px_-20px_rgba(0,0,0,0.9)] backdrop-blur-xl"
            >
              <Icon className={cn("mt-0.5 size-4 shrink-0", accents[item.tone])} />
              <div className="min-w-0 flex-1">
                <p className="text-[13px] font-medium text-mist">{item.title}</p>
                {item.description ? (
                  <p className="mt-0.5 text-[12px] leading-relaxed text-muted">{item.description}</p>
                ) : null}
              </div>
              <button
                type="button"
                aria-label="Dismiss notification"
                onClick={() => setItems((current) => current.filter((entry) => entry.id !== item.id))}
                className="rounded-md p-1 text-faint transition-colors hover:bg-white/5 hover:text-mist"
              >
                <X className="size-3.5" />
              </button>
            </div>
          );
        })}
      </div>
    </ToastContext.Provider>
  );
}

export function useToast() {
  const context = useContext(ToastContext);
  if (!context) throw new Error("useToast must be used inside ToastProvider");
  return context;
}

export function useCopyToClipboard() {
  const { toast } = useToast();
  return useCallback(
    async (value: string, label = "Copied to clipboard") => {
      try {
        await navigator.clipboard.writeText(value);
        toast({ title: label, tone: "success" });
      } catch {
        toast({ title: "Could not copy", description: "Your browser blocked clipboard access.", tone: "error" });
      }
    },
    [toast],
  );
}

/** Reset the app document title when navigating between client pages. */
export function useDocumentTitle(title: string) {
  useEffect(() => {
    document.title = title ? `${title} · ClipMind` : "ClipMind";
  }, [title]);
}
