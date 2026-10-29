"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import {
  Activity,
  AudioLines,
  Coins,
  Database,
  Gauge,
  RefreshCw,
  Sparkles,
  TrendingDown,
  Zap,
} from "lucide-react";
import { api, ApiError } from "@/lib/api";
import type { Health, Usage, UsageCall } from "@/lib/types";
import { cn, formatNumber, formatRelative, formatUsd } from "@/lib/utils";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Progress } from "@/components/ui/progress";
import { Skeleton } from "@/components/ui/skeleton";
import { EmptyState } from "@/components/ui/empty-state";
import { useDocumentTitle } from "@/components/ui/toast";
import { PageHeader } from "@/components/page-header";

const PURPOSE_LABELS: Record<string, string> = {
  understand: "Story understanding",
  select_clips: "Clip selection",
  critique: "Self-critique",
  generate_copy: "Platform copy",
  summary: "Summary",
  insights: "Engagement insights",
  transcribe: "Transcription",
};

export default function UsagePage() {
  const [usage, setUsage] = useState<Usage | null>(null);
  const [calls, setCalls] = useState<UsageCall[]>([]);
  const [health, setHealth] = useState<Health | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  useDocumentTitle("Usage & spend");

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const [usageResult, callsResult, healthResult] = await Promise.allSettled([
        api.getUsage(),
        api.getUsageCalls(100),
        api.health(),
      ]);
      if (usageResult.status === "fulfilled") setUsage(usageResult.value);
      else throw usageResult.reason;
      if (callsResult.status === "fulfilled") setCalls(callsResult.value);
      if (healthResult.status === "fulfilled") setHealth(healthResult.value);
      setError(null);
    } catch (reason) {
      setError(reason instanceof ApiError ? reason.detail : "Could not load usage data.");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  const breakdown = useMemo(() => {
    const map = new Map<string, number>();
    for (const call of calls) {
      map.set(call.purpose, (map.get(call.purpose) ?? 0) + call.cost_usd);
    }
    const total = Array.from(map.values()).reduce((sum, value) => sum + value, 0);
    return Array.from(map.entries())
      .map(([purpose, cost]) => ({ purpose, cost, share: total ? cost / total : 0 }))
      .sort((a, b) => b.cost - a.cost);
  }, [calls]);

  const budgetShare = usage && usage.budget_usd > 0 ? (usage.total_cost_usd / usage.budget_usd) * 100 : 0;
  const cacheRate =
    usage && usage.input_tokens > 0 ? (usage.cached_tokens / usage.input_tokens) * 100 : 0;

  return (
    <div className="animate-in">
      <PageHeader
        eyebrow={
          <>
            <span>Operations</span>
            <span className="size-1 rounded-full bg-faint" />
            <span>Usage & spend</span>
          </>
        }
        title="Every call, accounted for."
        description="ClipMind meters model tokens and transcription seconds against a hard budget guard. If a run would cross the limit, it stops before the request is sent."
        actions={
          <Button variant="secondary" onClick={() => void load()} loading={loading}>
            <RefreshCw className="size-3.5" />
            Refresh
          </Button>
        }
      />

      {error ? (
        <div className="mb-5 rounded-xl border border-warning/25 bg-warning/[0.055] px-4 py-3 text-[12px] text-warning">
          {error}
        </div>
      ) : null}

      <div className="grid gap-3 lg:grid-cols-[1.35fr_1fr]">
        <div className="panel relative overflow-hidden p-5">
          <div className="pointer-events-none absolute -right-10 -top-16 size-56 rounded-full bg-lime/[0.06] blur-3xl" />
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-2">
              <Coins className="size-3.5 text-lime/80" />
              <span className="font-mono text-[9.5px] uppercase tracking-[0.18em] text-faint">
                Budget
              </span>
            </div>
            <Badge tone="sky">
              {health?.provider ? `${health.provider} live` : "Live provider"}
            </Badge>
          </div>

          <div className="mt-5 flex flex-wrap items-end gap-x-8 gap-y-3">
            <div>
              {loading && !usage ? (
                <Skeleton className="h-10 w-36" />
              ) : (
                <p className="text-[34px] font-semibold leading-none tracking-[-0.05em] text-mist">
                  {formatUsd(usage?.total_cost_usd ?? 0, { precise: true })}
                </p>
              )}
              <p className="mt-2 text-[10.5px] text-faint">spent this workspace</p>
            </div>
            <div>
              <p className="text-[18px] font-medium leading-none tabular-nums text-muted">
                {formatUsd(usage?.remaining_usd ?? 0, { precise: false })}
              </p>
              <p className="mt-2 text-[10.5px] text-faint">remaining of {formatUsd(usage?.budget_usd ?? 0, { precise: false })}</p>
            </div>
          </div>

          <div className="mt-5">
            <div className="mb-1.5 flex items-center justify-between font-mono text-[9px] text-faint">
              <span className="uppercase tracking-[0.14em]">Budget consumed</span>
              <span className="tabular-nums">{budgetShare.toFixed(1)}%</span>
            </div>
            <Progress
              value={budgetShare}
              className="h-2"
              indicatorClassName={budgetShare > 85 ? "bg-danger" : budgetShare > 65 ? "bg-warning" : undefined}
            />
            <p className="mt-2 text-[10px] leading-relaxed text-faint">
              The guard blocks any call that would push spend past{" "}
              {formatUsd(usage?.budget_usd ?? 0, { precise: false })}. Free-tier presets
              report $0 until you set their list prices.
            </p>
          </div>
        </div>

        <div className="grid grid-cols-2 gap-3">
          <UsageStat
            icon={<Sparkles className="size-3.5" />}
            label="Input tokens"
            value={formatNumber(usage?.input_tokens ?? 0)}
            detail={`${formatNumber(usage?.cached_tokens ?? 0)} cached`}
          />
          <UsageStat
            icon={<Zap className="size-3.5" />}
            label="Output tokens"
            value={formatNumber(usage?.output_tokens ?? 0)}
            detail={`${formatNumber(usage?.total_tokens ?? 0)} total`}
          />
          <UsageStat
            icon={<AudioLines className="size-3.5" />}
            label="Transcription"
            value={formatUsd(usage?.asr_cost_usd ?? 0, { precise: true })}
            detail={
              health?.asr_provider === "whisper"
                ? "Local Whisper"
                : health?.asr_provider === "meta"
                  ? "Meta Voice ASR"
                  : "Remote Whisper"
            }
          />
          <UsageStat
            icon={<Activity className="size-3.5" />}
            label="Calls"
            value={formatNumber(usage?.calls ?? 0)}
            detail={`${cacheRate.toFixed(0)}% cached input`}
          />
        </div>
      </div>

      <div className="mt-3 grid gap-3 lg:grid-cols-[1fr_1.4fr]">
        <div className="panel p-5">
          <div className="flex items-center gap-2">
            <Database className="size-3.5 text-faint" />
            <p className="font-mono text-[9.5px] uppercase tracking-[0.18em] text-faint">
              Spend by stage
            </p>
          </div>
          {breakdown.length === 0 ? (
            <p className="mt-5 text-[11.5px] leading-relaxed text-faint">
              No model calls recorded yet. Run a project and the breakdown appears here.
            </p>
          ) : (
            <div className="mt-4 space-y-3">
              {breakdown.map((item) => (
                <div key={item.purpose}>
                  <div className="flex items-baseline justify-between gap-3">
                    <span className="text-[11px] text-muted">
                      {PURPOSE_LABELS[item.purpose] ?? item.purpose}
                    </span>
                    <span className="font-mono text-[9.5px] tabular-nums text-faint">
                      {formatUsd(item.cost, { precise: true })}
                    </span>
                  </div>
                  <div className="mt-1.5 h-1 overflow-hidden rounded-full bg-white/[0.06]">
                    <div
                      className="h-full rounded-full bg-lime/70"
                      style={{ width: `${Math.max(2, item.share * 100)}%` }}
                    />
                  </div>
                </div>
              ))}
            </div>
          )}
          <div className="mt-5 flex items-start gap-2 rounded-lg border border-line-soft bg-void/50 p-3">
            <TrendingDown className="mt-0.5 size-3.5 shrink-0 text-faint" />
            <p className="text-[10px] leading-relaxed text-faint">
              Prompt caching is used for repeated system prompts. Cached input is billed at the lower
              cached rate when the provider reports it.
            </p>
          </div>
        </div>

        <div className="panel overflow-hidden">
          <div className="flex items-center justify-between border-b border-line-soft px-5 py-3.5">
            <p className="font-mono text-[9.5px] uppercase tracking-[0.18em] text-faint">
              Recent calls
            </p>
            <span className="font-mono text-[9px] text-faint">{calls.length} rows</span>
          </div>
          {loading && calls.length === 0 ? (
            <div className="space-y-3 p-5">
              {Array.from({ length: 6 }).map((_, index) => (
                <Skeleton key={index} className="h-8 w-full" />
              ))}
            </div>
          ) : calls.length === 0 ? (
            <EmptyState
              icon={<Gauge className="size-5" />}
              title="No calls yet"
              description="Process a project to see every model and transcription call, including tokens, latency, cache hits, and cost."
              className="m-5 border-0 bg-transparent py-10"
            />
          ) : (
            <div className="overflow-x-auto">
              <table className="w-full min-w-[620px] text-left">
                <thead>
                  <tr className="border-b border-line-soft text-[9px] uppercase tracking-[0.12em] text-faint">
                    <th className="px-5 py-2.5 font-medium">Call</th>
                    <th className="px-3 py-2.5 font-medium">Tokens</th>
                    <th className="px-3 py-2.5 font-medium">Cost</th>
                    <th className="px-3 py-2.5 font-medium">Latency</th>
                    <th className="px-5 py-2.5 text-right font-medium">When</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-line-soft/70">
                  {calls.slice(0, 40).map((call) => (
                    <tr key={`${call.kind}-${call.id}`} className="group hover:bg-white/[0.018]">
                      <td className="px-5 py-2.5">
                        <div className="flex items-center gap-2">
                          <span
                            className={cn(
                              "flex size-5 items-center justify-center rounded border",
                              call.kind === "asr"
                                ? "border-sky/20 bg-sky/10 text-sky"
                                : "border-line bg-raised text-faint",
                            )}
                          >
                            {call.kind === "asr" ? (
                              <AudioLines className="size-2.5" />
                            ) : (
                              <Sparkles className="size-2.5" />
                            )}
                          </span>
                          <div>
                            <p className="text-[11px] font-medium text-mist">
                              {PURPOSE_LABELS[call.purpose] ?? call.purpose}
                            </p>
                            <p className="font-mono text-[8.5px] text-faint">
                              {call.model}
                              {call.cache_hit ? " · cache hit" : ""}
                            </p>
                          </div>
                        </div>
                      </td>
                      <td className="px-3 py-2.5 font-mono text-[9.5px] tabular-nums text-muted">
                        {call.kind === "asr"
                          ? `${call.audio_seconds.toFixed(0)}s audio`
                          : `${formatNumber(call.input_tokens)} / ${formatNumber(call.output_tokens)}`}
                      </td>
                      <td className="px-3 py-2.5 font-mono text-[9.5px] tabular-nums text-muted">
                        {formatUsd(call.cost_usd, { precise: true })}
                      </td>
                      <td className="px-3 py-2.5 font-mono text-[9.5px] tabular-nums text-faint">
                        {call.latency_ms ? `${(call.latency_ms / 1000).toFixed(1)}s` : "—"}
                      </td>
                      <td className="px-5 py-2.5 text-right text-[9.5px] text-faint">
                        {formatRelative(call.created_at)}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </div>
      </div>

      <div className="mt-4 flex flex-wrap items-center justify-between gap-3 rounded-xl border border-line bg-void/40 px-4 py-3">
        <p className="text-[10.5px] leading-relaxed text-faint">
          Prices are configurable in <span className="font-mono text-muted">.env</span>. Free-tier
          presets report $0 until you add list prices; the guard is intentionally conservative.
        </p>
        <div className="flex items-center gap-3 font-mono text-[9px] uppercase tracking-[0.12em] text-faint">
          <span>credits {formatUsd(usage?.credits_remaining_usd ?? 0, { precise: false })}</span>
          <span className="size-1 rounded-full bg-faint" />
          <span>{health?.model ?? "—"}</span>
        </div>
      </div>
    </div>
  );
}

function UsageStat({
  icon,
  label,
  value,
  detail,
}: {
  icon: React.ReactNode;
  label: string;
  value: string;
  detail: string;
}) {
  return (
    <div className="panel px-4 py-3.5">
      <div className="flex items-center gap-1.5 text-faint">
        {icon}
        <span className="font-mono text-[8.5px] uppercase tracking-[0.12em]">{label}</span>
      </div>
      <p className="mt-2 truncate text-[18px] font-semibold leading-none tracking-[-0.03em] text-mist">
        {value}
      </p>
      <p className="mt-1.5 text-[9.5px] text-faint">{detail}</p>
    </div>
  );
}
