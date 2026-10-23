"use client";

import { Check, Circle, Loader2, Radio, RotateCw, TriangleAlert } from "lucide-react";
import type { Job } from "@/lib/types";
import { cn, formatRelative } from "@/lib/utils";
import { Progress } from "./ui/progress";
import { Button } from "./ui/button";

export function PipelineProgress({
  job,
  connected,
  onRetry,
  retrying,
  className,
}: {
  job: Job | null;
  connected?: boolean;
  onRetry?: () => void;
  retrying?: boolean;
  className?: string;
}) {
  if (!job) {
    return (
      <div className={cn("panel p-5", className)}>
        <p className="text-[12px] text-faint">Upload a source to see the pipeline.</p>
      </div>
    );
  }

  const running = job.status === "running" || job.status === "queued";
  const failed = job.status === "failed";

  return (
    <div className={cn("panel overflow-hidden", className)}>
      <div className="border-b border-line-soft p-5">
        <div className="flex items-center justify-between gap-3">
          <div className="flex items-center gap-2">
            <span className="font-mono text-[9.5px] uppercase tracking-[0.18em] text-faint">
              Pipeline
            </span>
            {running ? (
              <span className="flex items-center gap-1 rounded-full bg-lime/10 px-1.5 py-0.5 font-mono text-[9px] uppercase tracking-wider text-lime">
                <Radio className="size-2.5 pulse-dot" />
                {connected ? "live" : "polling"}
              </span>
            ) : null}
          </div>
          <span className="font-mono text-[11px] tabular-nums text-muted">
            {Math.round(job.progress)}%
          </span>
        </div>
        <div className="mt-2.5 flex items-end justify-between gap-3">
          <p className="text-[13.5px] font-medium text-mist">
            {job.status === "completed"
              ? "Your clip pack is ready"
              : job.status === "failed"
                ? "Pipeline stopped"
                : job.status === "queued"
                  ? "Queued for processing"
                  : job.stages_json?.find((stage) => stage.status === "running")?.label ?? "Processing"}
          </p>
          <span className="text-[10.5px] text-faint">{formatRelative(job.updated_at)}</span>
        </div>
        <Progress
          value={job.progress}
          className="mt-3"
          indicatorClassName={failed ? "bg-danger" : undefined}
          label="Pipeline progress"
        />
      </div>

      <div className="space-y-0.5 p-3">
        {(job.stages_json ?? []).map((stage, index) => {
          const active = stage.status === "running";
          const complete = stage.status === "complete";
          const stageFailed = stage.status === "failed";
          return (
            <div
              key={stage.name}
              className={cn(
                "flex items-start gap-3 rounded-lg px-2.5 py-2 transition-colors",
                active && "bg-white/[0.035]",
              )}
            >
              <div className="relative mt-0.5 flex size-4 shrink-0 items-center justify-center">
                {complete ? (
                  <span className="flex size-4 items-center justify-center rounded-full bg-lime/15 text-lime">
                    <Check className="size-2.5" strokeWidth={3} />
                  </span>
                ) : active ? (
                  <Loader2 className="size-3.5 animate-spin text-lime" />
                ) : stageFailed ? (
                  <TriangleAlert className="size-3.5 text-danger" />
                ) : (
                  <Circle className="size-3 text-faint/70" />
                )}
                {index < (job.stages_json?.length ?? 0) - 1 ? (
                  <span
                    className={cn(
                      "absolute left-1/2 top-4 h-[calc(100%+0.55rem)] w-px -translate-x-1/2",
                      complete ? "bg-lime/20" : "bg-line",
                    )}
                  />
                ) : null}
              </div>
              <div className="min-w-0 flex-1 pb-0.5">
                <div className="flex items-baseline justify-between gap-2">
                  <p
                    className={cn(
                      "text-[12px] font-medium",
                      active || complete ? "text-mist" : stageFailed ? "text-danger" : "text-faint",
                    )}
                  >
                    {stage.label}
                  </p>
                  {active ? (
                    <span className="font-mono text-[9.5px] tabular-nums text-lime/80">
                      {Math.round(stage.progress * 100)}%
                    </span>
                  ) : null}
                </div>
                {stage.message && (active || stageFailed) ? (
                  <p className="mt-0.5 line-clamp-2 text-[10.5px] leading-relaxed text-faint">
                    {stage.message}
                  </p>
                ) : null}
                {active ? (
                  <Progress value={stage.progress * 100} className="mt-1.5 h-0.5" />
                ) : null}
              </div>
            </div>
          );
        })}
      </div>

      {failed ? (
        <div className="border-t border-line-soft bg-danger/[0.045] p-4">
          <p className="text-[11.5px] leading-relaxed text-danger/90">
            {job.error ?? "The pipeline hit an error. Check the backend logs for details."}
          </p>
          {onRetry ? (
            <Button
              size="sm"
              variant="secondary"
              className="mt-3"
              onClick={onRetry}
              loading={retrying}
            >
              <RotateCw className="size-3.5" />
              Retry job
            </Button>
          ) : null}
        </div>
      ) : null}
    </div>
  );
}
