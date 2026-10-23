"use client";

import { Activity, Gauge, Lightbulb, ShieldAlert, TrendingUp } from "lucide-react";
import type { InsightScores, InsightsReport } from "@/lib/types";
import { cn } from "@/lib/utils";
import { Badge } from "./ui/badge";
import { EmptyState } from "./ui/empty-state";

const SCORE_LABELS: Array<{ key: keyof InsightScores; label: string; hint: string }> = [
  { key: "hook_strength", label: "Hook strength", hint: "Does the first line earn the next second?" },
  { key: "pacing", label: "Pacing", hint: "Words per minute and pause rhythm." },
  { key: "clarity", label: "Clarity", hint: "Filler rate and sentence structure." },
  { key: "emotional_peaks", label: "Emotional peaks", hint: "Moments of tension or belief change." },
];

const performanceTone = {
  high: "success",
  medium: "warning",
  low: "danger",
} as const;

export function InsightsPanel({ report }: { report: InsightsReport | null }) {
  if (!report) {
    return (
      <EmptyState
        icon={<TrendingUp className="size-5" />}
        title="Insights are not ready yet"
        description="After clips are selected, ClipMind builds a structural scorecard from the transcript and clip shape. These are editorial estimates, not platform guarantees."
        className="bg-void/25"
      />
    );
  }

  return (
    <div className="space-y-3">
      <div className="panel relative overflow-hidden p-5">
        <div className="pointer-events-none absolute -right-12 -top-12 size-48 rounded-full bg-sky/[0.055] blur-3xl" />
        <div className="flex flex-wrap items-start justify-between gap-4">
          <div className="max-w-xl">
            <div className="flex items-center gap-2">
              <span className="font-mono text-[9.5px] uppercase tracking-[0.18em] text-sky/80">
                Engagement read
              </span>
              <Badge tone={performanceTone[report.predicted_performance]}>
                {report.predicted_performance} potential
              </Badge>
              <Badge tone="outline" className="capitalize">
                {report.confidence} confidence
              </Badge>
            </div>
            <h2 className="mt-3 text-balance text-[19px] font-semibold leading-tight tracking-[-0.025em] text-mist">
              {report.headline}
            </h2>
            <p className="mt-2 text-pretty text-[12px] leading-relaxed text-muted">{report.summary}</p>
          </div>
          <div className="flex items-center gap-4 rounded-xl border border-line bg-void/50 px-4 py-3">
            <div className="text-center">
              <p className="text-[26px] font-semibold leading-none tracking-[-0.05em] text-mist">
                {Math.round(
                  (report.overall.hook_strength +
                    report.overall.pacing +
                    report.overall.clarity +
                    report.overall.emotional_peaks) /
                    4,
                )}
              </p>
              <p className="mt-1 font-mono text-[8px] uppercase tracking-[0.14em] text-faint">
                avg score
              </p>
            </div>
            <div className="h-9 w-px bg-line" />
            <div>
              <p className="font-mono text-[9px] uppercase tracking-[0.14em] text-faint">Speech</p>
              <p className="mt-1 text-[12px] font-medium tabular-nums text-mist">
                {Math.round(report.metrics.wpm)} wpm
              </p>
              <p className="font-mono text-[9px] text-faint">
                {Math.round(report.metrics.pause_ratio * 100)}% pauses
              </p>
            </div>
          </div>
        </div>
      </div>

      <div className="grid gap-3 lg:grid-cols-[1.1fr_1fr]">
        <div className="panel p-5">
          <div className="flex items-center gap-2">
            <Gauge className="size-3.5 text-lime/70" />
            <p className="font-mono text-[9.5px] uppercase tracking-[0.18em] text-faint">Overall scorecard</p>
          </div>
          <div className="mt-4 space-y-3.5">
            {SCORE_LABELS.map(({ key, label, hint }) => (
              <ScoreRow key={key} label={label} hint={hint} value={report.overall[key]} />
            ))}
          </div>
          <div className="mt-5 grid grid-cols-2 gap-2 border-t border-line-soft pt-4">
            <MiniMetric label="Filler rate" value={`${(report.metrics.filler_rate * 100).toFixed(1)}%`} />
            <MiniMetric
              label="Source"
              value={
                report.metrics.word_count
                  ? `${report.metrics.word_count.toLocaleString()} words`
                  : report.source.kind
              }
            />
          </div>
        </div>

        <div className="panel p-5">
          <div className="flex items-center gap-2">
            <Lightbulb className="size-3.5 text-warning/80" />
            <p className="font-mono text-[9.5px] uppercase tracking-[0.18em] text-faint">Next tests</p>
          </div>
          <ul className="mt-4 space-y-3">
            {report.improvements.map((item, index) => (
              <li key={`${index}-${item.slice(0, 10)}`} className="flex gap-3">
                <span className="mt-0.5 flex size-5 shrink-0 items-center justify-center rounded-md border border-line bg-raised font-mono text-[9px] text-warning/80">
                  {String(index + 1).padStart(2, "0")}
                </span>
                <p className="text-[11.5px] leading-relaxed text-muted">{item}</p>
              </li>
            ))}
          </ul>
          <div className="mt-5 flex items-start gap-2 rounded-lg border border-line-soft bg-void/50 p-3">
            <Activity className="mt-0.5 size-3.5 shrink-0 text-faint" />
            <p className="text-[10px] leading-relaxed text-faint">{report.methodology}</p>
          </div>
        </div>
      </div>

      <div className="panel overflow-hidden">
        <div className="flex items-center justify-between border-b border-line-soft px-5 py-3.5">
          <p className="font-mono text-[9.5px] uppercase tracking-[0.18em] text-faint">Clip scorecards</p>
          <span className="font-mono text-[9px] text-faint">{report.clips.length} clips</span>
        </div>
        <div className="divide-y divide-line-soft">
          {report.clips.map((clip) => (
            <div key={clip.clip_id ?? clip.clip_index} className="p-5">
              <div className="flex flex-wrap items-start justify-between gap-3">
                <div className="flex min-w-0 items-start gap-3">
                  <span className="mt-0.5 flex size-6 shrink-0 items-center justify-center rounded-md border border-line bg-raised font-mono text-[9px] text-muted">
                    {String(clip.clip_index + 1).padStart(2, "0")}
                  </span>
                  <div className="min-w-0">
                    <p className="text-[12.5px] font-medium text-mist">{clip.title}</p>
                    <p className="mt-0.5 text-[10.5px] leading-relaxed text-faint">{clip.reasoning}</p>
                  </div>
                </div>
                <Badge tone={performanceTone[clip.predicted_performance]}>
                  {clip.predicted_performance}
                </Badge>
              </div>
              <div className="mt-4 grid grid-cols-2 gap-x-6 gap-y-3 sm:grid-cols-4">
                {SCORE_LABELS.map(({ key, label }) => (
                  <div key={key}>
                    <div className="flex items-baseline justify-between">
                      <span className="text-[9.5px] text-faint">{label}</span>
                      <span className="font-mono text-[9.5px] tabular-nums text-muted">
                        {clip.scores[key]}
                      </span>
                    </div>
                    <div className="mt-1.5 h-1 overflow-hidden rounded-full bg-white/[0.06]">
                      <div
                        className={cn(
                          "h-full rounded-full",
                          clip.scores[key] >= 80
                            ? "bg-lime/80"
                            : clip.scores[key] >= 60
                              ? "bg-warning/70"
                              : "bg-danger/70",
                        )}
                        style={{ width: `${clip.scores[key]}%` }}
                      />
                    </div>
                  </div>
                ))}
              </div>
              {clip.safety_notes && clip.safety_notes.length > 0 ? (
                <div className="mt-3 flex items-start gap-2 rounded-lg border border-warning/20 bg-warning/[0.045] p-2.5">
                  <ShieldAlert className="mt-0.5 size-3.5 shrink-0 text-warning" />
                  <p className="text-[10px] leading-relaxed text-warning/80">
                    {clip.safety_notes.join(" · ")}
                  </p>
                </div>
              ) : null}
            </div>
          ))}
        </div>
        <div className="border-t border-line-soft bg-void/30 px-5 py-3">
          <p className="text-[10px] leading-relaxed text-faint">
            Predictions are modeled estimates from transcript structure. They are not guarantees and do
            not use platform analytics or visual analysis.
          </p>
        </div>
      </div>
    </div>
  );
}

function ScoreRow({ label, hint, value }: { label: string; hint: string; value: number }) {
  return (
    <div>
      <div className="flex items-baseline justify-between gap-3">
        <span className="text-[11.5px] font-medium text-mist">{label}</span>
        <span className="font-mono text-[11px] tabular-nums text-muted">{value}</span>
      </div>
      <div className="mt-1.5 h-1.5 overflow-hidden rounded-full bg-white/[0.06]">
        <div
          className={cn(
            "h-full rounded-full transition-[width] duration-700",
            value >= 80 ? "bg-lime" : value >= 60 ? "bg-warning" : "bg-danger",
          )}
          style={{ width: `${value}%` }}
        />
      </div>
      <p className="mt-1 text-[9.5px] text-faint">{hint}</p>
    </div>
  );
}

function MiniMetric({ label, value }: { label: string; value: string }) {
  return (
    <div className="rounded-lg border border-line-soft bg-void/40 px-3 py-2">
      <p className="font-mono text-[8.5px] uppercase tracking-[0.12em] text-faint">{label}</p>
      <p className="mt-0.5 text-[11px] font-medium text-mist">{value}</p>
    </div>
  );
}
