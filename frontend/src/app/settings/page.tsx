"use client";

import { useCallback, useEffect, useState } from "react";
import {
  BookOpen,
  Check,
  CircleDollarSign,
  Code2,
  Copy,
  Database,
  ExternalLink,
  Gauge,
  HardDrive,
  KeyRound,
  RefreshCw,
  Server,
  Sparkles,
  Terminal,
  Timer,
  Wand2,
} from "lucide-react";
import { API_URL, api, ApiError } from "@/lib/api";
import type { Health, SystemInfo, Usage } from "@/lib/types";
import { cn, formatDuration, formatUsd } from "@/lib/utils";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Skeleton } from "@/components/ui/skeleton";
import { useCopyToClipboard, useDocumentTitle } from "@/components/ui/toast";
import { PageHeader } from "@/components/page-header";

export default function SettingsPage() {
  const [health, setHealth] = useState<Health | null>(null);
  const [system, setSystem] = useState<SystemInfo | null>(null);
  const [usage, setUsage] = useState<Usage | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const copy = useCopyToClipboard();
  useDocumentTitle("Settings");

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const [healthResult, systemResult, usageResult] = await Promise.allSettled([
        api.health(),
        api.system(),
        api.getUsage(),
      ]);
      if (healthResult.status === "fulfilled") setHealth(healthResult.value);
      else throw healthResult.reason;
      if (systemResult.status === "fulfilled") setSystem(systemResult.value);
      if (usageResult.status === "fulfilled") setUsage(usageResult.value);
      setError(null);
    } catch (reason) {
      setError(reason instanceof ApiError ? reason.detail : "Could not reach the ClipMind API.");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  const liveEnv =
    "PROVIDER=groq\nMODEL_API_KEY=your_key_here\n# Optional overrides\nLLM_MODEL=openai/gpt-oss-120b\nLLM_ASR_MODEL=whisper-large-v3-turbo";
  const runBackend = "cd backend\nuvicorn app.main:app --reload --port 8000";
  const runFrontend = "cd frontend\nnpm run dev";

  return (
    <div className="animate-in">
      <PageHeader
        eyebrow={
          <>
            <span>System</span>
            <span className="size-1 rounded-full bg-faint" />
            <span>Configuration</span>
          </>
        }
        title="Know what is running, and why."
        description="ClipMind keeps the operational surface small: one provider switch, one budget guard, one storage root, and explicit processing limits. Everything below is read from the running backend — no secrets are exposed."
        actions={
          <Button variant="secondary" onClick={() => void load()} loading={loading}>
            <RefreshCw className="size-3.5" />
            Re-check
          </Button>
        }
      />

      {error ? (
        <div className="mb-5 rounded-xl border border-warning/25 bg-warning/[0.055] px-4 py-3 text-[12px] text-warning">
          {error}
        </div>
      ) : null}

      <div className="panel mb-3 overflow-hidden">
        <div className="flex flex-col gap-4 p-5 sm:flex-row sm:items-center sm:justify-between">
          <div className="flex items-center gap-4">
            <div className="relative flex size-12 items-center justify-center rounded-2xl border border-lime/20 bg-lime/[0.07] text-lime">
              <Server className="size-5" />
              <span className="absolute -right-0.5 -top-0.5 size-2.5 rounded-full border-2 border-surface bg-lime pulse-dot" />
            </div>
            <div>
              <div className="flex flex-wrap items-center gap-2">
                <p className="text-[13.5px] font-semibold text-mist">
                  {health ? "API connected" : loading ? "Checking connection…" : "API unreachable"}
                </p>
                <Badge tone={health ? "success" : loading ? "neutral" : "danger"}>
                  {health ? "online" : loading ? "checking" : "offline"}
                </Badge>
                <Badge tone="sky">live provider</Badge>
              </div>
              <p className="mt-1 font-mono text-[10px] text-faint">{API_URL}</p>
            </div>
          </div>
          <div className="flex flex-wrap gap-4 sm:justify-end">
            <Stat label="Version" value={health?.version ?? "—"} />
            <Stat label="Provider" value={health?.provider ?? "—"} />
            <Stat label="Model" value={health?.model ?? "—"} mono />
          </div>
        </div>
      </div>

      <div className="grid items-start gap-3 lg:grid-cols-2">
        <Card
          icon={<Sparkles className="size-3.5" />}
          title="Engine & models"
          description="The provider switch is read once at startup. No request can silently fall through to a paid model."
        >
          {loading && !system ? (
            <div className="space-y-3">
              {Array.from({ length: 5 }).map((_, index) => (
                <Skeleton key={index} className="h-4 w-full" />
              ))}
            </div>
          ) : (
            <div className="space-y-0.5">
              <Row label="Provider" value={system?.provider ?? health?.provider ?? "—"} />
              <Row label="Endpoint" value={system?.provider_base_url ?? "—"} mono truncate />
              <Row label="Text model" value={system?.model ?? health?.model ?? "—"} mono />
              <Row label="Transcription" value={system?.asr_model ?? "—"} mono />
              <Row
                label="ASR route"
                value={
                  system?.asr_provider === "whisper"
                    ? "Local Whisper"
                    : system?.asr_provider === "meta"
                      ? "Meta Voice"
                      : "OpenAI-compatible"
                }
              />
              <Row label="Local whisper fallback" value={system?.force_whisper ? "Forced" : "Available if installed"} />
            </div>
          )}
          <div className="mt-4 rounded-xl border border-line-soft bg-void/50 p-3.5">
            <div className="flex items-center justify-between">
              <p className="font-mono text-[8.5px] uppercase tracking-[0.14em] text-faint">
                Switch provider
              </p>
              <button
                type="button"
                aria-label="Copy live environment"
                onClick={() => void copy(liveEnv, "Environment snippet copied")}
                className="rounded p-1 text-faint hover:text-mist"
              >
                <Copy className="size-3" />
              </button>
            </div>
            <pre className="mt-2 overflow-x-auto font-mono text-[10px] leading-relaxed text-muted">
              {liveEnv}
            </pre>
            <p className="mt-2 text-[9.5px] leading-relaxed text-faint">
              Add these to <span className="font-mono">.env</span>, restart the API, and verify with{" "}
              <span className="font-mono">/api/health</span>.
            </p>
          </div>
        </Card>

        <Card
          icon={<CircleDollarSign className="size-3.5" />}
          title="Budget & pricing"
          description="A hard guard runs before every model and ASR request. Prices are per million tokens."
        >
          <div className="rounded-xl border border-lime/15 bg-lime/[0.035] p-4">
            <div className="flex items-end justify-between gap-4">
              <div>
                <p className="font-mono text-[8.5px] uppercase tracking-[0.14em] text-lime/70">
                  Session spend
                </p>
                <p className="mt-1.5 text-[24px] font-semibold leading-none tracking-[-0.04em] text-mist">
                  {formatUsd(usage?.total_cost_usd ?? 0, { precise: true })}
                </p>
              </div>
              <div className="text-right">
                <p className="font-mono text-[8.5px] uppercase tracking-[0.14em] text-faint">Budget</p>
                <p className="mt-1.5 text-[14px] font-medium tabular-nums text-muted">
                  {formatUsd(system?.max_budget_usd ?? 0, { precise: false })}
                </p>
              </div>
            </div>
          </div>
          <div className="mt-4 space-y-0.5">
            <Row label="Input / 1M" value={formatUsd(system?.input_price_per_m ?? 0, { precise: false })} />
            <Row label="Cached input / 1M" value={formatUsd(system?.cached_input_price_per_m ?? 0, { precise: false })} />
            <Row label="Output / 1M" value={formatUsd(system?.output_price_per_m ?? 0, { precise: false })} />
            <Row label="ASR / hour" value={formatUsd(system?.asr_usd_per_hour ?? 0, { precise: true })} />
            <Row label="Hackathon credits" value={formatUsd(system?.hackathon_credits_usd ?? 0, { precise: false })} />
            <Row label="Remaining" value={formatUsd(usage?.remaining_usd ?? 0, { precise: false })} accent />
          </div>
          <p className="mt-3 text-[10px] leading-relaxed text-faint">
            Pricing is read from environment variables so a changed rate never requires a code change.
          </p>
        </Card>

        <Card
          icon={<Timer className="size-3.5" />}
          title="Processing limits"
          description="These are the guardrails the UI and API enforce before accepting work."
        >
          <div className="grid grid-cols-2 gap-2">
            <Mini label="Max upload" value={`${system?.max_upload_mb ?? 500} MB`} />
            <Mini label="Max duration" value={formatDuration(system?.max_duration_s ?? 7200)} />
            <Mini label="Clip window" value={`${system?.min_clip_s ?? 15}–${system?.max_clip_s ?? 60}s`} />
            <Mini label="Job concurrency" value={String(system?.job_concurrency ?? 1)} />
          </div>
          <div className="mt-4 space-y-0.5">
            <Row label="Auto-resume jobs" value={system?.auto_resume_jobs ? "On" : "Off"} />
            <Row label="Rate limit" value="60 writes / minute / client" />
            <Row label="Render format" value="1080 × 1920 · H.264 · burned SRT" />
            <Row label="Export" value="MP4 + SRT + copy.csv + summary.md + insights" />
          </div>
        </Card>

        <Card
          icon={<HardDrive className="size-3.5" />}
          title="Storage & network"
          description="Uploads, normalized media, renders, and the SQLite database live under one data root."
        >
          <div className="space-y-0.5">
            <Row label="Data root" value={system?.data_dir ?? "./data"} mono truncate />
            <Row label="Database" value="SQLite · data/clipmind.db" mono />
            <Row label="Public API" value={system?.public_api_url ?? API_URL} mono truncate />
            <Row label="Environment" value={system?.environment ?? "development"} />
          </div>
          <div className="mt-4">
            <p className="font-mono text-[8.5px] uppercase tracking-[0.14em] text-faint">
              CORS origins
            </p>
            <div className="mt-2 flex flex-wrap gap-1.5">
              {(system?.cors_origins ?? ["http://localhost:3000"]).map((origin) => (
                <Badge key={origin} tone="outline" className="font-mono text-[9px]">
                  {origin}
                </Badge>
              ))}
            </div>
          </div>
          <div className="mt-4 flex items-center gap-2">
            <a
              href={`${API_URL}/docs`}
              target="_blank"
              rel="noreferrer"
              className="inline-flex h-8 items-center gap-1.5 rounded-lg border border-line bg-raised px-3 text-[11px] text-muted transition-colors hover:border-[#3a4135] hover:text-mist"
            >
              <Code2 className="size-3" />
              API reference
              <ExternalLink className="size-2.5" />
            </a>
            <a
              href={`${API_URL}/health`}
              target="_blank"
              rel="noreferrer"
              className="inline-flex h-8 items-center gap-1.5 rounded-lg border border-line bg-raised px-3 text-[11px] text-muted transition-colors hover:border-[#3a4135] hover:text-mist"
            >
              <Gauge className="size-3" />
              Health JSON
              <ExternalLink className="size-2.5" />
            </a>
          </div>
        </Card>
      </div>

      <div className="mt-3 grid gap-3 lg:grid-cols-2">
        <div className="panel p-5">
          <div className="flex items-center gap-2">
            <Terminal className="size-3.5 text-lime/70" />
            <p className="font-mono text-[9.5px] uppercase tracking-[0.18em] text-faint">
              Run it locally
            </p>
          </div>
          <div className="mt-4 space-y-3">
            <Command label="Backend · FastAPI" command={runBackend} onCopy={() => void copy(runBackend, "Backend command copied")} />
            <Command label="Frontend · Next.js" command={runFrontend} onCopy={() => void copy(runFrontend, "Frontend command copied")} />
            <Command
              label="One-click demo"
              command="Open the dashboard → Run the demo"
              onCopy={() => undefined}
              hideCopy
            />
          </div>
        </div>

        <div className="panel p-5">
          <div className="flex items-center gap-2">
            <BookOpen className="size-3.5 text-lime/70" />
            <p className="font-mono text-[9.5px] uppercase tracking-[0.18em] text-faint">
              How the guardrails work
            </p>
          </div>
          <ul className="mt-4 space-y-3">
            {[
              [<KeyRound key="key" className="size-3.5" />, "No secrets in the browser", "Only the public API URL reaches the client. The model key stays in the backend environment."],
              [<Database key="db" className="size-3.5" />, "Quote-grounded clips", "Every selected moment must overlap a verbatim transcript quote. Invalid timings are rejected before render."],
              [<CircleDollarSign key="budget" className="size-3.5" />, "Budget before request", "The cost estimate is checked before dispatch, then reconciled from provider usage."],
              [<Wand2 key="brand" className="size-3.5" />, "Brand rules at two layers", "Banned words are scrubbed during generation and rejected again on manual edits."],
            ].map(([icon, title, body]) => (
              <li key={String(title)} className="flex gap-3">
                <span className="mt-0.5 text-lime/75">{icon}</span>
                <div>
                  <p className="text-[11.5px] font-medium text-mist">{title}</p>
                  <p className="mt-0.5 text-[10.5px] leading-relaxed text-faint">{body}</p>
                </div>
              </li>
            ))}
          </ul>
        </div>
      </div>

      <div className="mt-4 flex flex-wrap items-center justify-between gap-3 rounded-xl border border-line bg-void/40 px-4 py-3">
        <p className="text-[10.5px] text-faint">
          Changes to provider, budget, or limits require an API restart. The UI never writes secrets.
        </p>
        <span className="flex items-center gap-1.5 font-mono text-[9px] uppercase tracking-[0.12em] text-faint">
          <Check className="size-3 text-lime/70" />
          config loaded from .env
        </span>
      </div>
    </div>
  );
}

function Card({
  icon,
  title,
  description,
  children,
}: {
  icon: React.ReactNode;
  title: string;
  description: string;
  children: React.ReactNode;
}) {
  return (
    <div className="panel p-5">
      <div className="flex items-start gap-3">
        <span className="mt-0.5 flex size-8 shrink-0 items-center justify-center rounded-lg border border-line bg-raised text-faint">
          {icon}
        </span>
        <div>
          <h2 className="text-[13px] font-semibold tracking-[-0.015em] text-mist">{title}</h2>
          <p className="mt-0.5 text-[10.5px] leading-relaxed text-faint">{description}</p>
        </div>
      </div>
      <div className="mt-4">{children}</div>
    </div>
  );
}

function Row({
  label,
  value,
  mono,
  accent,
  truncate,
}: {
  label: string;
  value: string;
  mono?: boolean;
  accent?: boolean;
  truncate?: boolean;
}) {
  return (
    <div className="flex items-start justify-between gap-4 border-b border-line-soft py-2 last:border-0">
      <span className="shrink-0 text-[10.5px] text-faint">{label}</span>
      <span
        className={cn(
          "max-w-[62%] text-right text-[10.5px] font-medium",
          mono && "font-mono text-[9.5px]",
          accent ? "text-lime" : "text-muted",
          truncate && "truncate",
        )}
        title={value}
      >
        {value}
      </span>
    </div>
  );
}

function Stat({ label, value, mono }: { label: string; value: string; mono?: boolean }) {
  return (
    <div>
      <p className="font-mono text-[8px] uppercase tracking-[0.14em] text-faint">{label}</p>
      <p className={cn("mt-1 text-[11px] font-medium text-muted", mono && "font-mono text-[10px]")}>{value}</p>
    </div>
  );
}

function Mini({ label, value }: { label: string; value: string }) {
  return (
    <div className="rounded-lg border border-line-soft bg-void/40 px-3 py-2">
      <p className="font-mono text-[8px] uppercase tracking-[0.12em] text-faint">{label}</p>
      <p className="mt-0.5 text-[11px] font-medium tabular-nums text-mist">{value}</p>
    </div>
  );
}

function Command({
  label,
  command,
  onCopy,
  hideCopy,
}: {
  label: string;
  command: string;
  onCopy: () => void;
  hideCopy?: boolean;
}) {
  return (
    <div>
      <div className="flex items-center justify-between">
        <p className="text-[10px] text-faint">{label}</p>
        {!hideCopy ? (
          <button
            type="button"
            onClick={onCopy}
            aria-label={`Copy ${label} command`}
            className="rounded p-1 text-faint hover:text-mist"
          >
            <Copy className="size-3" />
          </button>
        ) : null}
      </div>
      <pre className="mt-1.5 overflow-x-auto rounded-lg border border-line-soft bg-void/60 px-3 py-2 font-mono text-[9.5px] leading-relaxed text-muted">
        {command}
      </pre>
    </div>
  );
}
