"use client";

import { useEffect, useRef, useState } from "react";
import Link from "next/link";
import { usePathname } from "next/navigation";
import {
  Boxes,
  ChevronRight,
  Fingerprint,
  Gauge,
  Menu,
  Plus,
  Settings2,
  Sparkles,
  X,
} from "lucide-react";
import { api } from "@/lib/api";
import type { Health } from "@/lib/types";
import { cn, formatUsd } from "@/lib/utils";
import { Logo, LogoMark } from "./logo";
import { Badge, Dot } from "./ui/badge";

const navigation = [
  { href: "/", label: "Projects", icon: Boxes, exact: true },
  { href: "/new", label: "New project", icon: Plus },
  { href: "/brands", label: "Brand profiles", icon: Fingerprint },
  { href: "/usage", label: "Usage", icon: Gauge },
  { href: "/settings", label: "Settings", icon: Settings2 },
];

export function AppShell({ children }: { children: React.ReactNode }) {
  const pathname = usePathname();
  const [mobileOpen, setMobileOpen] = useState(false);
  const [health, setHealth] = useState<Health | null>(null);
  const [monthlyCost, setMonthlyCost] = useState<number | null>(null);
  const menuButtonRef = useRef<HTMLButtonElement>(null);
  const drawerRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    let cancelled = false;
    api
      .health()
      .then((data) => {
        if (!cancelled) setHealth(data);
      })
      .catch(() => {
        if (!cancelled) setHealth(null);
      });
    api
      .getUsage()
      .then((usage) => {
        if (!cancelled) setMonthlyCost(usage.total_cost_usd);
      })
      .catch(() => undefined);
    return () => {
      cancelled = true;
    };
  }, [pathname]);

  useEffect(() => {
    setMobileOpen(false);
  }, [pathname]);

  useEffect(() => {
    if (!mobileOpen) return;
    const drawer = drawerRef.current;
    const menuButton = menuButtonRef.current;
    const focusable = () =>
      drawer?.querySelectorAll<HTMLElement>(
        'a[href], button:not(:disabled), [tabindex]:not([tabindex="-1"])',
      );
    requestAnimationFrame(() => (focusable()?.[0] ?? drawer)?.focus());
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key === "Escape") {
        setMobileOpen(false);
        return;
      }
      if (event.key !== "Tab") return;
      const items = Array.from(focusable() ?? []);
      if (!items.length) {
        event.preventDefault();
        drawer?.focus();
        return;
      }
      const first = items[0];
      const last = items[items.length - 1];
      if (event.shiftKey && (document.activeElement === first || !drawer?.contains(document.activeElement))) {
        event.preventDefault();
        last.focus();
      } else if (!event.shiftKey && (document.activeElement === last || !drawer?.contains(document.activeElement))) {
        event.preventDefault();
        first.focus();
      }
    };
    document.addEventListener("keydown", onKeyDown);
    return () => {
      document.removeEventListener("keydown", onKeyDown);
      menuButton?.focus();
    };
  }, [mobileOpen]);

  const isActive = (href: string, exact?: boolean) =>
    exact ? pathname === href : pathname === href || pathname.startsWith(`${href}/`);

  const sidebar = (
    <div className="flex h-full flex-col">
      <div className="flex h-16 items-center px-5">
        <Link href="/" aria-label="ClipMind home" className="rounded-lg">
          <Logo />
        </Link>
      </div>

      <nav className="flex-1 space-y-1 px-3 pt-2" aria-label="Main navigation">
        <p className="px-3 pb-2 font-mono text-[9.5px] uppercase tracking-[0.2em] text-faint">
          Studio
        </p>
        {navigation.map((item) => {
          const active = isActive(item.href, item.exact);
          const Icon = item.icon;
          return (
            <Link
              key={item.href}
              href={item.href}
              aria-current={active ? "page" : undefined}
              className={cn(
                "group flex h-10 items-center gap-3 rounded-xl px-3 text-[13px] font-medium transition-colors",
                active
                  ? "bg-white/[0.065] text-mist"
                  : "text-muted hover:bg-white/[0.035] hover:text-mist",
              )}
            >
              <Icon
                className={cn(
                  "size-4 transition-colors",
                  active ? "text-lime" : "text-faint group-hover:text-muted",
                )}
                strokeWidth={1.8}
              />
              <span className="flex-1">{item.label}</span>
              {active ? <ChevronRight className="size-3.5 text-faint" /> : null}
            </Link>
          );
        })}
      </nav>

      <div className="p-3">
        <div className="rounded-xl border border-line bg-void/60 p-3.5">
          <div className="flex items-center justify-between">
            <span className="font-mono text-[9.5px] uppercase tracking-[0.18em] text-faint">
              Engine
            </span>
            {health ? (
              <Badge tone="sky" className="px-2 py-0 text-[10px] capitalize">
                <Dot className="text-sky" />
                {health.provider} live
              </Badge>
            ) : (
              <Badge tone="warning" className="px-2 py-0 text-[10px]">
                <Dot /> Offline
              </Badge>
            )}
          </div>
          <p className="mt-2.5 line-clamp-1 text-[12.5px] font-medium text-mist">
            {health?.model ?? "—"}
          </p>
          <p className="mt-0.5 text-[11px] text-faint">
            {health
              ? `Budget ${formatUsd(health.max_budget_usd, { precise: false })}`
              : "Start the API to connect"}
          </p>
          <div className="mt-3 flex items-center justify-between border-t border-line-soft pt-2.5">
            <span className="text-[11px] text-faint">Session spend</span>
            <span className="font-mono text-[11px] tabular-nums text-muted">
              {monthlyCost === null ? "—" : formatUsd(monthlyCost, { precise: true })}
            </span>
          </div>
        </div>

        <Link
          href="/new"
          className="mt-3 flex items-center gap-2.5 rounded-xl px-2 py-2 text-[11.5px] text-faint transition-colors hover:text-muted"
        >
          <Sparkles className="size-3.5 text-lime/70" />
          One recording in. A week out.
        </Link>
      </div>
    </div>
  );

  return (
    <div className="min-h-dvh">
      <aside className="fixed inset-y-0 left-0 z-40 hidden w-[248px] border-r border-line bg-[#0a0c0a]/88 backdrop-blur-xl lg:block">
        {sidebar}
      </aside>

      <header className="glass sticky top-0 z-30 flex h-14 items-center justify-between border-b border-line px-4 lg:hidden">
        <Link href="/" aria-label="ClipMind home">
          <LogoMark />
        </Link>
        <span className="text-[13px] font-semibold tracking-[-0.02em]">ClipMind</span>
        <button
          ref={menuButtonRef}
          type="button"
          onClick={() => setMobileOpen(true)}
          aria-label="Open navigation"
          aria-expanded={mobileOpen}
          aria-controls="mobile-navigation"
          className="flex size-11 items-center justify-center rounded-lg border border-line bg-raised text-muted"
        >
          <Menu className="size-4" />
        </button>
      </header>

      {mobileOpen ? (
        <div className="fixed inset-0 z-50 lg:hidden">
          <button
            type="button"
            aria-label="Close navigation"
            onClick={() => setMobileOpen(false)}
            className="absolute inset-0 bg-black/70 backdrop-blur-sm"
          />
          <div
            ref={drawerRef}
            id="mobile-navigation"
            role="dialog"
            aria-modal="true"
            aria-label="Mobile navigation"
            tabIndex={-1}
            className="animate-in-fast absolute inset-y-0 left-0 w-[min(282px,calc(100vw-2rem))] border-r border-line bg-[#0a0c0a]"
          >
            <button
              type="button"
              onClick={() => setMobileOpen(false)}
              aria-label="Close navigation"
              className="absolute right-3 top-4 z-10 flex size-11 items-center justify-center rounded-lg text-muted hover:bg-white/5"
            >
              <X className="size-4" />
            </button>
            {sidebar}
          </div>
        </div>
      ) : null}

      <main className="lg:pl-[248px]">
        <div className="mx-auto w-full max-w-[1500px] px-4 pb-14 pt-6 sm:px-6 lg:px-8 lg:pt-8">
          {children}
        </div>
      </main>
    </div>
  );
}
