"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { api, jobStreamUrl } from "@/lib/api";
import type { Job, JobEvent, JobStage } from "@/lib/types";

const EVENT_TYPES = [
  "queued",
  "progress",
  "stage_start",
  "stage_complete",
  "stage_retry",
  "stage_failed",
  "job_complete",
  "job_failed",
  "error",
  "stream_end",
];

function applyEvent(job: Job | null, event: JobEvent): Job | null {
  if (!job) return job;
  const stages: JobStage[] = (job.stages_json ?? []).map((stage) => ({ ...stage }));
  const stage = stages.find((item) => item.name === event.stage);
  if (stage) {
    if (event.type === "stage_start") {
      stage.status = "running";
      stage.message = event.message;
      stage.progress = Math.max(stage.progress, event.progress);
    } else if (event.type === "stage_complete") {
      stage.status = "complete";
      stage.progress = 1;
      stage.message = event.message;
    } else if (event.type === "stage_failed") {
      stage.status = "failed";
      stage.message = event.message;
    } else if (event.type === "progress") {
      stage.status = "running";
      stage.progress = Math.max(stage.progress, event.progress);
      stage.message = event.message;
    } else if (event.type === "stage_retry") {
      stage.message = event.message;
    }
  }
  const terminal = event.type === "job_complete" || event.type === "job_failed";
  return {
    ...job,
    stages_json: stages,
    stage: event.stage || job.stage,
    progress: terminal && event.type === "job_complete" ? 100 : event.progress * 100 || job.progress,
    status: terminal
      ? event.type === "job_complete"
        ? "completed"
        : "failed"
      : job.status === "queued"
        ? "running"
        : job.status,
    error: event.type === "job_failed" ? event.message : job.error,
  };
}

export function useJobStream(jobId: string | null | undefined) {
  const [job, setJob] = useState<Job | null>(null);
  const [events, setEvents] = useState<JobEvent[]>([]);
  const [connected, setConnected] = useState(false);
  const [loading, setLoading] = useState(Boolean(jobId));
  const terminalRef = useRef(false);
  const sourceRef = useRef<EventSource | null>(null);
  const pollRef = useRef<number | null>(null);

  const stopPolling = useCallback(() => {
    if (pollRef.current !== null) {
      window.clearInterval(pollRef.current);
      pollRef.current = null;
    }
  }, []);

  const refresh = useCallback(async () => {
    if (!jobId) return null;
    const fresh = await api.getJob(jobId);
    setJob(fresh);
    setLoading(false);
    if (["completed", "failed", "cancelled"].includes(fresh.status)) {
      terminalRef.current = true;
      stopPolling();
      sourceRef.current?.close();
      setConnected(false);
    }
    return fresh;
  }, [jobId, stopPolling]);

  useEffect(() => {
    terminalRef.current = false;
    setJob(null);
    setEvents([]);
    setConnected(false);
    setLoading(Boolean(jobId));
    if (!jobId) return;
    let cancelled = false;

    const startPolling = () => {
      if (cancelled || pollRef.current !== null || terminalRef.current) return;
      setConnected(false);
      pollRef.current = window.setInterval(() => {
        refresh().catch(() => undefined);
      }, 1600);
    };

    api
      .getJob(jobId)
      .then((initial) => {
        if (cancelled) return;
        setJob(initial);
        setLoading(false);
        if (["completed", "failed", "cancelled"].includes(initial.status)) {
          terminalRef.current = true;
          return;
        }

        const source = new EventSource(jobStreamUrl(jobId));
        sourceRef.current = source;
        source.onopen = () => {
          if (!cancelled) setConnected(true);
        };
        source.onerror = () => {
          if (cancelled) return;
          setConnected(false);
          source.close();
          if (!terminalRef.current) startPolling();
        };

        const handle = (raw: MessageEvent) => {
          if (cancelled) return;
          let event: JobEvent;
          try {
            event = JSON.parse(raw.data) as JobEvent;
          } catch {
            return;
          }
          setEvents((current) => {
            if (current.some((entry) => entry.seq === event.seq && entry.type === event.type)) {
              return current;
            }
            return [...current.slice(-80), event];
          });
          setJob((current) => applyEvent(current, event));
          if (event.type === "job_complete" || event.type === "job_failed" || event.type === "stream_end") {
            terminalRef.current = true;
            source.close();
            setConnected(false);
            refresh().catch(() => undefined);
          }
        };

        for (const type of EVENT_TYPES) source.addEventListener(type, handle as EventListener);
      })
      .catch(() => {
        if (!cancelled) {
          setLoading(false);
          startPolling();
        }
      });

    return () => {
      cancelled = true;
      sourceRef.current?.close();
      sourceRef.current = null;
      stopPolling();
    };
  }, [jobId, refresh, stopPolling]);

  return { job, events, connected, loading, refresh };
}
