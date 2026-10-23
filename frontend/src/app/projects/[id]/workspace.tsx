"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import {
  ArrowLeft,
  BookOpen,
  ChevronRight,
  Download,
  Film,
  FolderOpen,
  Loader2,
  Play,
  RefreshCw,
  Scissors,
  Sparkles,
  Trash2,
  TrendingUp,
  TriangleAlert,
  Type,
  Wand2,
} from "lucide-react";
import { api, ApiError, exportUrl } from "@/lib/api";
import type { InsightsReport, Job, Project, Summary, Transcript } from "@/lib/types";
import { DEFAULT_PLATFORMS } from "@/lib/platforms";
import { formatDate, formatDuration, pluralize } from "@/lib/utils";
import { useJobStream } from "@/hooks/use-job-stream";
import { Button, IconButton } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Modal } from "@/components/ui/modal";
import { Progress } from "@/components/ui/progress";
import { Skeleton } from "@/components/ui/skeleton";
import { Tabs } from "@/components/ui/tabs";
import { EmptyState } from "@/components/ui/empty-state";
import { useDocumentTitle, useToast } from "@/components/ui/toast";
import { StatusBadge } from "@/components/status-badge";
import { SourcePanel } from "@/components/source-panel";
import { PipelineProgress } from "@/components/pipeline-progress";
import { ClipCard } from "@/components/clip-card";
import { SummaryPanel } from "@/components/summary-panel";
import { InsightsPanel } from "@/components/insights-panel";
import { TranscriptPanel } from "@/components/transcript-panel";

type TabValue = "clips" | "summary" | "insights" | "transcript";

export function ProjectWorkspace({ projectId }: { projectId: string }) {
  const router = useRouter();
  const { toast } = useToast();
  const [project, setProject] = useState<Project | null>(null);
  const [summary, setSummary] = useState<Summary | null>(null);
  const [insights, setInsights] = useState<InsightsReport | null>(null);
  const [transcript, setTranscript] = useState<Transcript | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [tab, setTab] = useState<TabValue>("clips");
  const [activeJobId, setActiveJobId] = useState<string | null>(null);
  const [starting, setStarting] = useState(false);
  const [retrying, setRetrying] = useState(false);
  const [deleteOpen, setDeleteOpen] = useState(false);
  const [deleting, setDeleting] = useState(false);
  const videoRef = useRef<HTMLVideoElement | null>(null);
  const audioRef = useRef<HTMLAudioElement | null>(null);
  const refreshedJobRef = useRef<string>("");

  const load = useCallback(
    async (silent = false) => {
      if (!silent) setLoading(true);
      try {
        const fresh = await api.getProject(projectId);
        setProject(fresh);
        setError(null);
        // These endpoints only exist after a successful run. Avoid noisy 404s
        // while the first pipeline is still working.
        if (!fresh.clips.length) {
          setSummary(null);
          setInsights(null);
          setTranscript(null);
          return;
        }
        const [summaryResult, insightsResult, transcriptResult] = await Promise.allSettled([
          api.getSummary(projectId),
          api.getInsights(projectId),
          api.getTranscript(projectId),
        ]);
        setSummary(summaryResult.status === "fulfilled" ? summaryResult.value : null);
        setInsights(insightsResult.status === "fulfilled" ? insightsResult.value.report : null);
        setTranscript(transcriptResult.status === "fulfilled" ? transcriptResult.value : null);
      } catch (reason) {
        setError(
          reason instanceof ApiError
            ? reason.status === 404
              ? "This project does not exist, or it was deleted."
              : reason.detail
            : "Could not load this project.",
        );
      } finally {
        setLoading(false);
      }
    },
    [projectId],
  );

  useEffect(() => {
    void load();
  }, [load]);

  const jobId = activeJobId ?? project?.latest_job?.id ?? null;
  const stream = useJobStream(jobId);
  const job: Job | null = stream.job ?? project?.latest_job ?? null;

  useEffect(() => {
    const status = stream.job?.status;
    if (!stream.job || !status || !["completed", "failed", "cancelled"].includes(status)) return;
    const key = `${stream.job.id}:${status}`;
    if (refreshedJobRef.current === key) return;
    refreshedJobRef.current = key;
    void load(true);
  }, [stream.job, load]);

  useDocumentTitle(project?.name ?? "Project");

  const asset = project?.assets?.[0] ?? null;
  const clips = project?.clips ?? [];
  const active = job ? ["queued", "running"].includes(job.status) : false;

  const seek = useCallback((seconds: number) => {
    const element = videoRef.current ?? audioRef.current;
    if (!element) return;
    element.currentTime = Math.max(0, seconds);
    void element.play().catch(() => undefined);
  }, []);

  const runPipeline = async () => {
    if (!project) return;
    setStarting(true);
    try {
      const platforms = Array.from(
        new Set(clips.flatMap((clip) => clip.copy_variants.map((variant) => variant.platform))),
      ).filter((platform): platform is (typeof DEFAULT_PLATFORMS)[number] =>
        DEFAULT_PLATFORMS.includes(platform as (typeof DEFAULT_PLATFORMS)[number]),
      );
      const nextJob = await api.startProcess(project.id, {
        n_clips: clips.length ? Math.min(10, Math.max(3, clips.length)) : 5,
        platforms: platforms.length ? platforms : DEFAULT_PLATFORMS,
        min_clip_s: 15,
        max_clip_s: 60,
        brand_profile_id: project.brand_profile_id,
      });
      setActiveJobId(nextJob.id);
      setProject((current) => (current ? { ...current, status: "queued", latest_job: nextJob } : current));
      toast({
        title: clips.length ? "Re-running the pipeline" : "Pipeline started",
        description: "Follow the stages in the pipeline panel.",
        tone: "success",
      });
    } catch (reason) {
      toast({
        title: "Could not start the pipeline",
        description: reason instanceof ApiError ? reason.detail : "Try again in a moment.",
        tone: "error",
      });
    } finally {
      setStarting(false);
    }
  };

  const retry = async () => {
    if (!job) return;
    setRetrying(true);
    try {
      const nextJob = await api.retryJob(job.id);
      setActiveJobId(nextJob.id);
      setProject((current) => (current ? { ...current, status: "queued", latest_job: nextJob } : current));
    } catch (reason) {
      toast({
        title: "Could not retry the job",
        description: reason instanceof ApiError ? reason.detail : "Try again in a moment.",
        tone: "error",
      });
    } finally {
      setRetrying(false);
    }
  };

  const removeProject = async () => {
    setDeleting(true);
    try {
      await api.deleteProject(projectId);
      toast({ title: "Project deleted", tone: "success" });
      router.push("/");
    } catch (reason) {
      toast({
        title: "Could not delete the project",
        description: reason instanceof ApiError ? reason.detail : "Try again in a moment.",
        tone: "error",
      });
      setDeleting(false);
      setDeleteOpen(false);
    }
  };

  const tabs = useMemo(
    () => [
      { value: "clips", label: "Clips", count: clips.length, icon: <Scissors className="size-3" /> },
      { value: "summary", label: "Summary", icon: <BookOpen className="size-3" /> },
      { value: "insights", label: "Insights", icon: <TrendingUp className="size-3" /> },
      { value: "transcript", label: "Transcript", icon: <Type className="size-3" /> },
    ],
    [clips.length],
  );

  if (loading) {
    return <WorkspaceSkeleton />;
  }

  if (!project) {
    return (
      <div className="mx-auto max-w-xl py-20 text-center">
        <div className="mx-auto flex size-12 items-center justify-center rounded-2xl border border-line bg-raised text-faint">
          <FolderOpen className="size-5" />
        </div>
        <h1 className="mt-5 text-xl font-semibold tracking-[-0.03em] text-mist">Project not found</h1>
        <p className="mt-2 text-[13px] text-muted">{error ?? "This project may have been deleted."}</p>
        <Button variant="secondary" className="mt-6" onClick={() => router.push("/")}>
          <ArrowLeft className="size-3.5" />
          Back to projects
        </Button>
      </div>
    );
  }

  return (
    <div className="animate-in">
      <div className="mb-5 flex items-center justify-between gap-3">
        <Link
          href="/"
          className="inline-flex items-center gap-1.5 text-[11.5px] text-faint transition-colors hover:text-mist"
        >
          <ArrowLeft className="size-3.5" />
          Projects
          <ChevronRight className="size-3 text-faint/60" />
          <span className="max-w-[240px] truncate text-muted">{project.name}</span>
        </Link>
        <div className="flex items-center gap-2">
          <IconButton
            label="Delete project"
            variant="ghost"
            size="icon-sm"
            onClick={() => setDeleteOpen(true)}
            disabled={active}
            className="text-faint hover:text-danger"
          >
            <Trash2 className="size-3.5" />
          </IconButton>
        </div>
      </div>

      <div className="flex flex-col gap-5 pb-6 lg:flex-row lg:items-end lg:justify-between">
        <div className="min-w-0">
          <div className="mb-3 flex flex-wrap items-center gap-2">
            <StatusBadge status={project.status} />
            {project.brand_profile ? (
              <Badge tone="outline">
                <Sparkles className="size-2.5 text-lime/70" />
                {project.brand_profile.name}
              </Badge>
            ) : (
              <Badge tone="outline">No brand profile</Badge>
            )}
            {asset ? (
              <span className="font-mono text-[9.5px] uppercase tracking-[0.12em] text-faint">
                {asset.kind} · {formatDuration(asset.duration_s)}
              </span>
            ) : null}
          </div>
          <h1 className="text-balance text-[26px] font-semibold leading-[1.08] tracking-[-0.035em] text-mist sm:text-[32px]">
            {project.name}
          </h1>
          <p className="mt-2 text-[11.5px] text-faint">
            Created {formatDate(project.created_at)}
            {asset ? ` · ${asset.original_filename}` : ""}
            {clips.length ? ` · ${pluralize(clips.length, "clip")}` : ""}
          </p>
        </div>

        <div className="flex flex-wrap items-center gap-2">
          <Button
            variant="secondary"
            onClick={() => {
              if (!clips.length) {
                toast({ title: "Nothing to export yet", description: "Run the pipeline first.", tone: "info" });
                return;
              }
              window.location.assign(exportUrl(project.id));
            }}
            disabled={!clips.length}
          >
            <Download className="size-3.5" />
            Export pack
          </Button>
          <Button
            variant={clips.length ? "secondary" : "primary"}
            onClick={runPipeline}
            loading={starting}
            disabled={!asset || active}
          >
            {clips.length ? <RefreshCw className="size-3.5" /> : <Play className="size-3.5" />}
            {clips.length ? "Re-run pipeline" : "Run pipeline"}
          </Button>
        </div>
      </div>

      {active && job ? (
        <div className="mb-5 flex flex-col gap-2.5 rounded-xl border border-lime/15 bg-lime/[0.035] px-4 py-3 sm:flex-row sm:items-center sm:justify-between">
          <div className="flex min-w-0 items-center gap-3">
            <span className="relative flex size-2 shrink-0">
              <span className="absolute inline-flex size-full animate-ping rounded-full bg-lime opacity-60" />
              <span className="relative inline-flex size-2 rounded-full bg-lime" />
            </span>
            <p className="truncate text-[12px] text-mist">
              <span className="font-medium">
                {job.status === "queued" ? "Queued" : job.stages_json.find((stage) => stage.status === "running")?.label ?? "Processing"}
              </span>
              <span className="ml-2 text-faint">
                {job.stages_json.find((stage) => stage.status === "running")?.message || "Working through the pipeline…"}
              </span>
            </p>
          </div>
          <div className="flex items-center gap-3 sm:w-56">
            <Progress value={job.progress} className="h-1" />
            <span className="w-9 text-right font-mono text-[10px] tabular-nums text-lime">
              {Math.round(job.progress)}%
            </span>
          </div>
        </div>
      ) : null}

      {project.status === "failed" && project.error && !active ? (
        <div className="mb-5 flex items-start gap-2.5 rounded-xl border border-danger/25 bg-danger/[0.055] px-4 py-3">
          <TriangleAlert className="mt-0.5 size-4 shrink-0 text-danger" />
          <div>
            <p className="text-[12px] font-medium text-danger">The last run stopped</p>
            <p className="mt-0.5 text-[11.5px] leading-relaxed text-danger/75">{project.error}</p>
          </div>
        </div>
      ) : null}

      {!asset ? (
        <EmptyState
          icon={<Wand2 className="size-5" />}
          title="This project has no source yet"
          description="Create a new project with a video, audio file, or pasted transcript, then come back here to edit the clip pack."
          action={
            <Button variant="primary" onClick={() => router.push("/new")}>
              <Wand2 className="size-3.5" />
              Add a source
            </Button>
          }
          className="bg-void/25 py-20"
        />
      ) : (
        <div className="grid items-start gap-5 xl:grid-cols-[minmax(0,1fr)_330px]">
          <div className="min-w-0">
            <div className="mb-4 flex flex-wrap items-center justify-between gap-3">
              <Tabs
                items={tabs}
                value={tab}
                onValueChange={(value) => setTab(value as TabValue)}
              />
              {tab === "clips" && clips.length > 0 ? (
                <span className="font-mono text-[9.5px] uppercase tracking-[0.14em] text-faint">
                  {clips.filter((clip) => clip.status === "rendered").length}/{clips.length} rendered
                </span>
              ) : null}
            </div>

            {tab === "clips" ? (
              clips.length === 0 ? (
                active ? (
                  <div className="space-y-3">
                    <div className="flex items-center gap-2 rounded-xl border border-line bg-void/40 px-4 py-3">
                      <Loader2 className="size-3.5 animate-spin text-lime" />
                      <p className="text-[12px] text-muted">
                        Reading the transcript and testing candidate moments. Clips will appear as they
                        clear validation.
                      </p>
                    </div>
                    <div className="grid gap-3 md:grid-cols-2">
                      {Array.from({ length: 4 }).map((_, index) => (
                        <div key={index} className="panel flex gap-4 p-3">
                          <Skeleton className="aspect-[9/16] w-[92px] rounded-lg" />
                          <div className="flex-1 space-y-3 py-1">
                            <Skeleton className="h-3.5 w-4/5" />
                            <Skeleton className="h-2.5 w-3/5" />
                            <Skeleton className="h-2.5 w-2/5" />
                          </div>
                        </div>
                      ))}
                    </div>
                  </div>
                ) : (
                  <EmptyState
                    icon={<Scissors className="size-5" />}
                    title="No clips yet"
                    description="Run the pipeline to find transcript-grounded moments, write platform copy, and render vertical clips."
                    action={
                      <Button variant="primary" onClick={runPipeline} loading={starting}>
                        <Play className="size-3.5" />
                        Run pipeline
                      </Button>
                    }
                    className="bg-void/25"
                  />
                )
              ) : (
                <div className="grid gap-3 md:grid-cols-2">
                  {clips.map((clip, index) => (
                    <ClipCard key={clip.id} clip={clip} projectId={project.id} index={index} />
                  ))}
                </div>
              )
            ) : null}

            {tab === "summary" ? <SummaryPanel summary={summary} onSeek={seek} /> : null}
            {tab === "insights" ? <InsightsPanel report={insights} /> : null}
            {tab === "transcript" ? <TranscriptPanel transcript={transcript} onSeek={seek} /> : null}
          </div>

          <aside className="space-y-3 xl:sticky xl:top-6">
            <SourcePanel asset={asset} videoRef={videoRef} audioRef={audioRef} />
            <PipelineProgress
              job={job}
              connected={stream.connected}
              onRetry={retry}
              retrying={retrying}
            />
            <div className="panel p-4">
              <p className="font-mono text-[9.5px] uppercase tracking-[0.18em] text-faint">
                Project notes
              </p>
              <dl className="mt-3 space-y-2.5">
                <Row label="Source" value={asset.original_filename} />
                <Row label="Duration" value={formatDuration(asset.duration_s)} />
                <Row label="Clips" value={String(clips.length)} />
                <Row label="Rendered" value={String(clips.filter((clip) => clip.status === "rendered").length)} />
                <Row label="Brand" value={project.brand_profile?.name ?? "Default voice"} />
                <Row label="Updated" value={formatDate(project.updated_at)} />
              </dl>
              <div className="mt-4 flex items-start gap-2 border-t border-line-soft pt-3">
                <Film className="mt-0.5 size-3 shrink-0 text-faint" />
                <p className="text-[10px] leading-relaxed text-faint">
                  Clips are rendered at 1080×1920 with burned-in captions. Review sensitive moments before
                  publishing.
                </p>
              </div>
            </div>
          </aside>
        </div>
      )}

      <Modal
        open={deleteOpen}
        onClose={() => setDeleteOpen(false)}
        title="Delete this project?"
        description="The source, transcript, renders, copy, and insights will be permanently removed."
        size="sm"
        footer={
          <>
            <Button variant="ghost" onClick={() => setDeleteOpen(false)} disabled={deleting}>
              Cancel
            </Button>
            <Button variant="danger" onClick={removeProject} loading={deleting}>
              <Trash2 className="size-3.5" />
              Delete project
            </Button>
          </>
        }
      >
        <div className="rounded-xl border border-danger/20 bg-danger/[0.045] p-4">
          <p className="text-[12px] font-medium text-mist">{project.name}</p>
          <p className="mt-1 text-[11.5px] leading-relaxed text-danger/75">
            This cannot be undone. Export the clip pack first if you want to keep any of it.
          </p>
        </div>
      </Modal>
    </div>
  );
}

function Row({ label, value }: { label: string; value: string }) {
  return (
    <div className="flex items-start justify-between gap-3">
      <dt className="shrink-0 text-[10.5px] text-faint">{label}</dt>
      <dd className="max-w-[190px] truncate text-right text-[10.5px] font-medium text-muted" title={value}>
        {value}
      </dd>
    </div>
  );
}

function WorkspaceSkeleton() {
  return (
    <div className="animate-in">
      <Skeleton className="h-3 w-52" />
      <div className="mt-8 flex items-end justify-between gap-6">
        <div className="space-y-3">
          <Skeleton className="h-5 w-36" />
          <Skeleton className="h-8 w-80 max-w-full" />
          <Skeleton className="h-3 w-60" />
        </div>
        <div className="flex gap-2">
          <Skeleton className="h-10 w-28" />
          <Skeleton className="h-10 w-32" />
        </div>
      </div>
      <div className="mt-8 grid gap-5 xl:grid-cols-[minmax(0,1fr)_330px]">
        <div className="space-y-4">
          <Skeleton className="h-10 w-80" />
          <div className="grid gap-3 md:grid-cols-2">
            {Array.from({ length: 4 }).map((_, index) => (
              <div key={index} className="panel flex gap-4 p-3">
                <Skeleton className="aspect-[9/16] w-[92px] rounded-lg" />
                <div className="flex-1 space-y-3 py-1">
                  <Skeleton className="h-3.5 w-4/5" />
                  <Skeleton className="h-2.5 w-3/5" />
                  <Skeleton className="h-2.5 w-2/5" />
                </div>
              </div>
            ))}
          </div>
        </div>
        <div className="space-y-3">
          <Skeleton className="h-52 rounded-2xl" />
          <Skeleton className="h-64 rounded-2xl" />
        </div>
      </div>
    </div>
  );
}
