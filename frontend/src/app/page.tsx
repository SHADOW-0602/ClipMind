"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import {
  ArrowRight,
  Clock3,
  Film,
  FolderOpen,
  Gauge,
  Plus,
  Scissors,
  Sparkles,
  Wand2,
} from "lucide-react";
import { api, ApiError } from "@/lib/api";
import type { Health, ProjectListItem, Usage } from "@/lib/types";
import { formatDuration, formatUsd, pluralize } from "@/lib/utils";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { EmptyState } from "@/components/ui/empty-state";
import { useToast } from "@/components/ui/toast";
import { PageHeader } from "@/components/page-header";
import { ProjectCard } from "@/components/project-card";
import { StatusBadge } from "@/components/status-badge";

export default function DashboardPage() {
  const router = useRouter();
  const { toast } = useToast();
  const [projects, setProjects] = useState<ProjectListItem[]>([]);
  const [usage, setUsage] = useState<Usage | null>(null);
  const [health, setHealth] = useState<Health | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [demoLoading, setDemoLoading] = useState(false);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    const [projectsResult, usageResult, healthResult] = await Promise.allSettled([
      api.listProjects(),
      api.getUsage(),
      api.health(),
    ]);
    if (projectsResult.status === "fulfilled") setProjects(projectsResult.value);
    else setError(projectsResult.reason instanceof ApiError ? projectsResult.reason.detail : "Could not reach the ClipMind API.");
    if (usageResult.status === "fulfilled") setUsage(usageResult.value);
    if (healthResult.status === "fulfilled") setHealth(healthResult.value);
    setLoading(false);
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  const totals = useMemo(() => {
    const clips = projects.reduce((sum, project) => sum + project.clip_count, 0);
    const seconds = projects.reduce((sum, project) => sum + project.duration_s, 0);
    const active = projects.filter((project) => ["queued", "processing"].includes(project.status));
    return { clips, seconds, active };
  }, [projects]);

  const runDemo = async () => {
    setDemoLoading(true);
    try {
      const project = await api.createDemoProject(null);
      await api.startProcess(project.id, {
        n_clips: 3,
        platforms: ["instagram", "tiktok", "linkedin"],
        min_clip_s: 12,
        max_clip_s: 35,
      });
      toast({
        title: "Demo recording is in the pipeline",
        description: "Transcript-grounded clips are being selected and rendered.",
        tone: "success",
      });
      router.push(`/projects/${project.id}`);
    } catch (reason) {
      toast({
        title: "Could not start the demo",
        description: reason instanceof ApiError ? reason.detail : "Is the API running on port 8000?",
        tone: "error",
      });
      setDemoLoading(false);
    }
  };

  return (
    <div className="animate-in">
      <PageHeader
        eyebrow={
          <>
            <span>Studio</span>
            <span className="size-1 rounded-full bg-faint" />
            <span>Overview</span>
          </>
        }
        title="Make the recording worth publishing."
        description="ClipMind turns one long conversation into transcript-grounded clips, platform-native copy, captioned vertical renders, and an honest read on what to improve."
        actions={
          <>
            <Button variant="secondary" onClick={runDemo} loading={demoLoading}>
              <Wand2 className="size-3.5" />
              Run the demo
            </Button>
            <Button variant="primary" onClick={() => router.push("/new")}>
              <Plus className="size-3.5" />
              New project
            </Button>
          </>
        }
      />

      {error ? (
        <div className="mb-6 flex flex-col gap-3 rounded-xl border border-warning/25 bg-warning/[0.055] px-4 py-3.5 sm:flex-row sm:items-center sm:justify-between">
          <div className="flex items-start gap-2.5">
            <Gauge className="mt-0.5 size-4 shrink-0 text-warning" />
            <div>
              <p className="text-[12.5px] font-medium text-warning">The API is not responding</p>
              <p className="mt-0.5 text-[11.5px] text-warning/75">
                {error} Start it with <span className="font-mono">uvicorn app.main:app --reload</span>.
              </p>
            </div>
          </div>
          <Button size="sm" variant="secondary" onClick={() => void load()}>
            Try again
          </Button>
        </div>
      ) : null}

      <section className="grid grid-cols-2 gap-3 xl:grid-cols-4" aria-label="Workspace totals">
        <MetricCard
          icon={<FolderOpen className="size-4" />}
          label="Projects"
          value={loading ? null : String(projects.length)}
          detail={totals.active.length ? `${totals.active.length} in progress` : "All sources in one place"}
        />
        <MetricCard
          icon={<Scissors className="size-4" />}
          label="Clips generated"
          value={loading ? null : String(totals.clips)}
          detail="Grounded in the transcript"
        />
        <MetricCard
          icon={<Clock3 className="size-4" />}
          label="Source analyzed"
          value={loading ? null : formatDuration(totals.seconds)}
          detail="Video, audio, and pasted text"
        />
        <MetricCard
          icon={<Sparkles className="size-4" />}
          label="Model spend"
          value={loading ? null : formatUsd(usage?.total_cost_usd ?? 0, { precise: true })}
          detail={
            health?.mock_mode
              ? "Mock mode · $0 runtime"
              : usage
                ? `${formatUsd(usage.remaining_usd, { precise: false })} budget left`
                : "Tracked per call"
          }
          accent
        />
      </section>

      {totals.active.length > 0 ? (
        <section className="mt-4 overflow-hidden rounded-xl border border-lime/15 bg-lime/[0.035]">
          <div className="flex flex-col gap-2 px-4 py-3 sm:flex-row sm:items-center sm:justify-between">
            <div className="flex items-center gap-2.5">
              <span className="relative flex size-2">
                <span className="absolute inline-flex size-full animate-ping rounded-full bg-lime opacity-60" />
                <span className="relative inline-flex size-2 rounded-full bg-lime" />
              </span>
              <p className="text-[12.5px] font-medium text-mist">
                {pluralize(totals.active.length, "project")} moving through the pipeline
              </p>
            </div>
            <div className="flex flex-wrap gap-2">
              {totals.active.slice(0, 3).map((project) => (
                <Link
                  key={project.id}
                  href={`/projects/${project.id}`}
                  className="inline-flex items-center gap-1.5 rounded-lg border border-lime/20 bg-lime/10 px-2.5 py-1 text-[11px] text-lime transition-colors hover:bg-lime/15"
                >
                  <span className="max-w-[180px] truncate">{project.name}</span>
                  <StatusBadge status={project.status} className="border-0 bg-transparent px-0 text-[10px] text-lime" />
                </Link>
              ))}
            </div>
          </div>
        </section>
      ) : null}

      <section className="mt-9">
        <div className="mb-4 flex items-end justify-between gap-4">
          <div>
            <h2 className="text-[15px] font-semibold tracking-[-0.02em] text-mist">Recent projects</h2>
            <p className="mt-1 text-[11.5px] text-faint">
              Pick up where you left off, or open a project to edit its clip pack.
            </p>
          </div>
          {projects.length > 0 ? (
            <Button variant="ghost" size="sm" onClick={() => router.push("/new")}>
              <Plus className="size-3.5" />
              Add source
            </Button>
          ) : null}
        </div>

        {loading ? (
          <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-3 2xl:grid-cols-4">
            {Array.from({ length: 4 }).map((_, index) => (
              <div key={index} className="panel overflow-hidden">
                <Skeleton className="aspect-[16/9] rounded-none" />
                <div className="space-y-2.5 p-4">
                  <Skeleton className="h-3.5 w-2/3" />
                  <Skeleton className="h-2.5 w-1/2" />
                </div>
              </div>
            ))}
          </div>
        ) : projects.length === 0 ? (
          <div className="grid gap-4 lg:grid-cols-[1.4fr_1fr]">
            <EmptyState
              icon={<Film className="size-5" />}
              title="Your first clip pack starts with one recording"
              description="Bring a podcast, a Zoom call, a voice memo, or paste a transcript. ClipMind finds the moments with a before and an after, then builds the rest around them."
              action={
                <div className="flex flex-wrap justify-center gap-2">
                  <Button variant="primary" onClick={() => router.push("/new")}>
                    <Plus className="size-3.5" />
                    Start a project
                  </Button>
                  <Button variant="secondary" onClick={runDemo} loading={demoLoading}>
                    <Wand2 className="size-3.5" />
                    Try the demo
                  </Button>
                </div>
              }
              className="min-h-[340px] bg-void/30"
            />
            <div className="panel p-5">
              <div className="flex items-center justify-between">
                <h3 className="text-[13px] font-semibold text-mist">The path from source to post</h3>
                <span className="font-mono text-[9px] uppercase tracking-[0.16em] text-faint">6 stages</span>
              </div>
              <ol className="mt-5 space-y-4">
                {[
                  ["Ingest", "Normalize the source, extract audio and frames."],
                  ["Understand", "Word-level transcript, topics, energy, and claims."],
                  ["Select", "Candidate moments, quote validation, self-critique."],
                  ["Write", "Hooks, captions, and a summary for each platform."],
                  ["Render", "1080×1920 captions burned into every clip."],
                  ["Read", "Structural engagement scores and next tests."],
                ].map(([label, body], index) => (
                  <li key={label} className="flex gap-3">
                    <span className="mt-0.5 flex size-5 shrink-0 items-center justify-center rounded-md border border-line bg-raised font-mono text-[9.5px] text-lime">
                      {String(index + 1).padStart(2, "0")}
                    </span>
                    <div>
                      <p className="text-[12px] font-medium text-mist">{label}</p>
                      <p className="mt-0.5 text-[11px] leading-relaxed text-faint">{body}</p>
                    </div>
                  </li>
                ))}
              </ol>
              <div className="mt-5 border-t border-line-soft pt-4">
                <p className="text-[10.5px] leading-relaxed text-faint">
                  A complete run in mock mode is deterministic and costs $0. Set{" "}
                  <span className="font-mono text-muted">MOCK_MODE=false</span> to use Meta models.
                </p>
              </div>
            </div>
          </div>
        ) : (
          <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-3 2xl:grid-cols-4">
            {projects.map((project, index) => (
              <ProjectCard key={project.id} project={project} index={index} />
            ))}
            <Link
              href="/new"
              className="group flex min-h-[210px] flex-col items-center justify-center rounded-[1.15rem] border border-dashed border-line text-center transition-colors hover:border-[#414a3a] hover:bg-white/[0.018]"
            >
              <span className="flex size-10 items-center justify-center rounded-xl border border-line bg-raised text-faint transition-colors group-hover:border-lime/30 group-hover:text-lime">
                <Plus className="size-4" />
              </span>
              <p className="mt-3 text-[12.5px] font-medium text-muted group-hover:text-mist">New source</p>
              <p className="mt-1 text-[10.5px] text-faint">One recording is enough</p>
            </Link>
          </div>
        )}
      </section>

      {projects.length > 0 ? (
        <section className="mt-8 grid gap-3 md:grid-cols-3">
          <QuickAction
            icon={<Wand2 className="size-4" />}
            title="Run the bundled demo"
            body="A 100-second recording with word-level ground truth. No upload needed."
            action="Start demo"
            onClick={runDemo}
            loading={demoLoading}
          />
          <QuickAction
            icon={<Sparkles className="size-4" />}
            title="Set a brand voice"
            body="Banned words, tone, audience, and examples flow into every caption."
            action="Brand profiles"
            href="/brands"
          />
          <QuickAction
            icon={<Gauge className="size-4" />}
            title="Know the cost"
            body="Every model and transcription call is metered against your budget."
            action="Usage & spend"
            href="/usage"
          />
        </section>
      ) : null}

      <div className="mt-10 flex items-center justify-between border-t border-line-soft pt-4">
        <p className="font-mono text-[9.5px] uppercase tracking-[0.16em] text-faint">
          ClipMind {health?.version ?? "0.1.0"} · {health?.provider ?? "mock"} engine
        </p>
        <Link href="/settings" className="group inline-flex items-center gap-1.5 text-[11px] text-faint hover:text-mist">
          System settings
          <ArrowRight className="size-3 transition-transform group-hover:translate-x-0.5" />
        </Link>
      </div>
    </div>
  );
}

function MetricCard({
  icon,
  label,
  value,
  detail,
  accent,
}: {
  icon: React.ReactNode;
  label: string;
  value: string | null;
  detail: string;
  accent?: boolean;
}) {
  return (
    <div className="panel relative overflow-hidden px-4 py-4">
      {accent ? (
        <div className="pointer-events-none absolute -right-6 -top-8 size-24 rounded-full bg-lime/10 blur-2xl" />
      ) : null}
      <div className="flex items-center gap-2 text-faint">
        <span className={accent ? "text-lime/80" : "text-faint"}>{icon}</span>
        <span className="font-mono text-[9.5px] uppercase tracking-[0.14em]">{label}</span>
      </div>
      <div className="mt-2.5 flex items-baseline gap-2">
        {value === null ? (
          <Skeleton className="h-7 w-20" />
        ) : (
          <span className="text-[25px] font-semibold leading-none tracking-[-0.04em] text-mist">
            {value}
          </span>
        )}
      </div>
      <p className="mt-2 text-[10.5px] text-faint">{detail}</p>
    </div>
  );
}

function QuickAction({
  icon,
  title,
  body,
  action,
  href,
  onClick,
  loading,
}: {
  icon: React.ReactNode;
  title: string;
  body: string;
  action: string;
  href?: string;
  onClick?: () => void;
  loading?: boolean;
}) {
  const content = (
    <>
      <div className="flex items-center gap-2 text-lime/75">{icon}</div>
      <p className="mt-3 text-[12.5px] font-medium text-mist">{title}</p>
      <p className="mt-1 line-clamp-2 text-[11px] leading-relaxed text-faint">{body}</p>
      <span className="mt-3 inline-flex items-center gap-1 text-[10.5px] font-medium text-muted">
        {loading ? "Starting…" : action}
        <ArrowRight className="size-3" />
      </span>
    </>
  );
  if (href) {
    return (
      <Link href={href} className="panel panel-hover p-4">
        {content}
      </Link>
    );
  }
  return (
    <button type="button" onClick={onClick} className="panel panel-hover p-4 text-left">
      {content}
    </button>
  );
}
