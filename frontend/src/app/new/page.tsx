"use client";

import { useEffect, useMemo, useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import {
  ArrowLeft,
  Check,
  ChevronRight,
  Clock3,
  FileText,
  Fingerprint,
  Info,
  Loader2,
  Plus,
  ShieldCheck,
  Sparkles,
  UploadCloud,
  Wand2,
} from "lucide-react";
import { api, ApiError } from "@/lib/api";
import type { BrandProfile, Platform } from "@/lib/types";
import { DEFAULT_PLATFORMS, PLATFORMS } from "@/lib/platforms";
import { cn, formatUsd, pluralize } from "@/lib/utils";
import { Button } from "@/components/ui/button";
import { Field, Input, Select, Textarea } from "@/components/ui/input";
import { Switch } from "@/components/ui/switch";
import { useToast } from "@/components/ui/toast";
import { UploadDropzone } from "@/components/upload-dropzone";
import { PageHeader } from "@/components/page-header";

type SourceType = "file" | "text";
type Phase = "idle" | "creating" | "uploading" | "starting";

const CLIP_CHOICES = [3, 5, 8, 10];
const MIN_CHOICES = [12, 15, 20, 30];
const MAX_CHOICES = [30, 45, 60, 90];

export default function NewProjectPage() {
  const router = useRouter();
  const { toast } = useToast();
  const [brands, setBrands] = useState<BrandProfile[]>([]);
  const [name, setName] = useState("");
  const [brandId, setBrandId] = useState<string>("");
  const [sourceType, setSourceType] = useState<SourceType>("file");
  const [file, setFile] = useState<File | null>(null);
  const [text, setText] = useState("");
  const [rights, setRights] = useState(false);
  const [nClips, setNClips] = useState(5);
  const [platforms, setPlatforms] = useState<Platform[]>(DEFAULT_PLATFORMS);
  const [minClip, setMinClip] = useState(15);
  const [maxClip, setMaxClip] = useState(45);
  const [phase, setPhase] = useState<Phase>("idle");
  const [error, setError] = useState<string | null>(null);
  const [demoLoading, setDemoLoading] = useState(false);

  useEffect(() => {
    api
      .listBrands()
      .then((items) => {
        setBrands(items);
        if (items.length === 1) setBrandId(items[0].id);
      })
      .catch(() => undefined);
  }, []);

  const busy = phase !== "idle" || demoLoading;

  const sourceReady = sourceType === "file" ? Boolean(file) : text.trim().length >= 40;
  const canSubmit = Boolean(name.trim()) && sourceReady && rights && platforms.length > 0 && !busy;
  const sourceLabel = sourceType === "file" ? file?.name : `${text.trim().split(/\s+/).filter(Boolean).length} words`;

  const estimate = useMemo(() => {
    const words = sourceType === "text" ? text.trim().split(/\s+/).filter(Boolean).length : 0;
    const minutes = sourceType === "text" ? Math.max(1, words / 150) : 0;
    return { minutes };
  }, [sourceType, text]);

  const togglePlatform = (platform: Platform) => {
    setPlatforms((current) =>
      current.includes(platform)
        ? current.filter((item) => item !== platform)
        : [...current, platform],
    );
  };

  const changeMin = (value: number) => {
    setMinClip(value);
    if (maxClip < value) setMaxClip(MAX_CHOICES.find((option) => option >= value) ?? 90);
  };

  const submit = async () => {
    if (!canSubmit) return;
    setError(null);
    setPhase("creating");
    let projectId: string | null = null;
    try {
      const project = await api.createProject({
        name: name.trim(),
        brand_profile_id: brandId || null,
      });
      projectId = project.id;
      setPhase("uploading");
      await api.uploadMedia(project.id, {
        file: sourceType === "file" ? (file ?? undefined) : undefined,
        text: sourceType === "text" ? text.trim() : undefined,
        rightsAttested: true,
        kindHint: sourceType === "text" ? "text" : undefined,
      });
      setPhase("starting");
      await api.startProcess(project.id, {
        n_clips: nClips,
        platforms,
        min_clip_s: minClip,
        max_clip_s: maxClip,
        brand_profile_id: brandId || null,
      });
      toast({
        title: "Project is in the pipeline",
        description: "You can watch each stage live from the workspace.",
        tone: "success",
      });
      router.push(`/projects/${project.id}`);
    } catch (reason) {
      const detail = reason instanceof ApiError ? reason.detail : "Something went wrong while creating the project.";
      setError(detail);
      setPhase("idle");
      if (projectId) {
        toast({ title: "Project created, but processing did not start", description: detail, tone: "error" });
        router.push(`/projects/${projectId}`);
      } else {
        toast({ title: "Could not create project", description: detail, tone: "error" });
      }
    }
  };

  const runDemo = async () => {
    setDemoLoading(true);
    setError(null);
    try {
      const project = await api.createDemoProject(brandId || null);
      await api.startProcess(project.id, {
        n_clips: 3,
        platforms: ["instagram", "tiktok", "linkedin"],
        min_clip_s: 12,
        max_clip_s: 35,
        brand_profile_id: brandId || null,
      });
      router.push(`/projects/${project.id}`);
    } catch (reason) {
      const detail = reason instanceof ApiError ? reason.detail : "Could not start the demo project.";
      setError(detail);
      setDemoLoading(false);
    }
  };

  return (
    <div className="animate-in mx-auto max-w-6xl">
      <Link
        href="/"
        className="mb-6 inline-flex items-center gap-1.5 text-[11.5px] text-faint transition-colors hover:text-mist"
      >
        <ArrowLeft className="size-3.5" />
        Back to projects
      </Link>

      <PageHeader
        eyebrow={
          <>
            <span>New project</span>
            <span className="size-1 rounded-full bg-faint" />
            <span>Source to clip pack</span>
          </>
        }
        title="Give one recording a second life."
        description="Bring the raw material. ClipMind handles the transcript, the moment selection, the copy, and the vertical render — while showing its work at every stage."
        actions={
          <Button variant="secondary" onClick={runDemo} loading={demoLoading} disabled={busy}>
            <Wand2 className="size-3.5" />
            Use demo recording
          </Button>
        }
      />

      <div className="grid items-start gap-5 lg:grid-cols-[minmax(0,1fr)_340px]">
        <div className="space-y-4">
          <section className="panel overflow-hidden">
            <SectionHeading
              index="01"
              title="Name the project"
              description="A working title is enough. You can rename it later."
            />
            <div className="grid gap-4 p-5 pt-4 sm:grid-cols-[1fr_240px]">
              <Field label="Project name">
                <Input
                  value={name}
                  onChange={(event) => setName(event.target.value)}
                  placeholder="e.g. The Creator Operating System"
                  maxLength={160}
                  autoFocus
                />
              </Field>
              <Field label="Brand profile" optional hint={brands.length ? undefined : "None yet — create one in Brand profiles."}>
                <div className="flex gap-2">
                  <Select value={brandId} onChange={(event) => setBrandId(event.target.value)}>
                    <option value="">No brand profile</option>
                    {brands.map((brand) => (
                      <option key={brand.id} value={brand.id}>
                        {brand.name}
                      </option>
                    ))}
                  </Select>
                  <Link
                    href="/brands"
                    aria-label="Manage brand profiles"
                    className="flex size-10 shrink-0 items-center justify-center rounded-xl border border-line bg-raised text-muted transition-colors hover:border-[#3a4135] hover:text-mist"
                  >
                    <Fingerprint className="size-4" />
                  </Link>
                </div>
              </Field>
            </div>
          </section>

          <section className="panel overflow-hidden">
            <SectionHeading
              index="02"
              title="Add the source"
              description="Video, audio, or plain text. We keep the original and work from a normalized copy."
            />
            <div className="p-5 pt-4">
              <div className="mb-4 flex w-fit items-center gap-1 rounded-xl border border-line bg-void/70 p-1">
                <button
                  type="button"
                  onClick={() => setSourceType("file")}
                  aria-pressed={sourceType === "file"}
                  className={cn(
                    "inline-flex min-h-11 items-center gap-1.5 rounded-lg px-3 text-[12px] font-medium transition-colors",
                    sourceType === "file" ? "bg-raised text-mist" : "text-muted hover:text-mist",
                  )}
                >
                  <UploadCloud className="size-3.5" />
                  Upload media
                </button>
                <button
                  type="button"
                  onClick={() => setSourceType("text")}
                  aria-pressed={sourceType === "text"}
                  className={cn(
                    "inline-flex min-h-11 items-center gap-1.5 rounded-lg px-3 text-[12px] font-medium transition-colors",
                    sourceType === "text" ? "bg-raised text-mist" : "text-muted hover:text-mist",
                  )}
                >
                  <FileText className="size-3.5" />
                  Paste transcript
                </button>
              </div>

              {sourceType === "file" ? (
                <UploadDropzone file={file} onFileChange={setFile} disabled={busy} />
              ) : (
                <div>
                  <Textarea
                    value={text}
                    onChange={(event) => setText(event.target.value)}
                    placeholder="Paste a transcript, an essay, or the notes from a talk. Separate ideas with paragraphs. ClipMind will give every sentence a synthetic timestamp and work from there."
                    className="min-h-[230px] font-[450]"
                    disabled={busy}
                  />
                  <div className="mt-2 flex items-center justify-between text-[10.5px] text-faint">
                    <span>{text.trim() ? `${text.trim().split(/\s+/).filter(Boolean).length} words` : "At least 40 characters"}</span>
                    <span className="font-mono">{text.length.toLocaleString()} chars</span>
                  </div>
                </div>
              )}

              <label className="mt-4 flex cursor-pointer items-start gap-3 rounded-xl border border-line bg-void/40 p-3.5 transition-colors hover:border-[#343b30]">
                <input
                  type="checkbox"
                  checked={rights}
                  onChange={(event) => setRights(event.target.checked)}
                  className="mt-0.5 size-4 shrink-0 rounded border-line bg-void accent-lime"
                />
                <span>
                  <span className="flex items-center gap-1.5 text-[12px] font-medium text-mist">
                    <ShieldCheck className="size-3.5 text-lime/80" />
                    I have the rights to process this content
                  </span>
                  <span className="mt-0.5 block text-[11px] leading-relaxed text-faint">
                    You are responsible for the source and for reviewing every clip before publishing.
                  </span>
                </span>
              </label>
            </div>
          </section>

          <section className="panel overflow-hidden">
            <SectionHeading
              index="03"
              title="Shape the output"
              description="Set the editorial guardrails. The pipeline will stay inside them."
            />
            <div className="space-y-5 p-5 pt-4">
              <div>
                <div className="mb-2 flex items-center justify-between">
                  <span className="text-[12px] font-medium text-muted">Clips to find</span>
                  <span className="font-mono text-[10.5px] text-faint">{nClips} clips</span>
                </div>
                <div className="grid grid-cols-4 gap-2">
                  {CLIP_CHOICES.map((choice) => (
                    <button
                      key={choice}
                      type="button"
                      onClick={() => setNClips(choice)}
                      disabled={busy}
                      className={cn(
                        "flex min-h-11 items-center justify-center rounded-xl border text-[12.5px] font-medium transition-all",
                        nClips === choice
                          ? "border-lime/45 bg-lime/10 text-lime"
                          : "border-line bg-void text-muted hover:border-[#3a4135] hover:text-mist",
                      )}
                    >
                      {choice}
                    </button>
                  ))}
                </div>
              </div>

              <div>
                <div className="mb-2 flex items-center justify-between">
                  <span className="text-[12px] font-medium text-muted">Platforms</span>
                  <span className="font-mono text-[10.5px] text-faint">
                    {pluralize(platforms.length, "channel")}
                  </span>
                </div>
                <div className="flex flex-wrap gap-2">
                  {PLATFORMS.map((platform) => {
                    const Icon = platform.icon;
                    const active = platforms.includes(platform.id);
                    return (
                      <button
                        key={platform.id}
                        type="button"
                        onClick={() => togglePlatform(platform.id)}
                        disabled={busy}
                        aria-pressed={active}
                        className={cn(
                          "inline-flex min-h-11 items-center gap-2 rounded-xl border px-3 text-[11.5px] font-medium transition-all",
                          active
                            ? "border-lime/35 bg-lime/[0.075] text-mist"
                            : "border-line bg-void text-faint hover:border-[#3a4135] hover:text-muted",
                        )}
                      >
                        <Icon className="size-3.5" style={{ color: active ? platform.accent : undefined }} />
                        {platform.label}
                        {active ? <Check className="size-3 text-lime" /> : <Plus className="size-3" />}
                      </button>
                    );
                  })}
                </div>
                <p className="mt-2 text-[10.5px] text-faint">
                  Every selected platform gets its own hook, caption, hashtags, and CTA.
                </p>
              </div>

              <div className="grid gap-4 sm:grid-cols-2">
                <Field label="Shortest clip">
                  <Select value={minClip} onChange={(event) => changeMin(Number(event.target.value))} disabled={busy}>
                    {MIN_CHOICES.map((choice) => (
                      <option key={choice} value={choice}>
                        {choice} seconds
                      </option>
                    ))}
                  </Select>
                </Field>
                <Field label="Longest clip">
                  <Select value={maxClip} onChange={(event) => setMaxClip(Number(event.target.value))} disabled={busy}>
                    {MAX_CHOICES.filter((choice) => choice >= minClip).map((choice) => (
                      <option key={choice} value={choice}>
                        {choice} seconds
                      </option>
                    ))}
                  </Select>
                </Field>
              </div>

              <Switch
                id="auto-render"
                checked
                onCheckedChange={() => undefined}
                disabled
                label="Render 9:16 captioned clips automatically"
                description="Burned-in captions, safe zones, and a thumbnail are generated for every selected moment."
              />
            </div>
          </section>

          {error ? (
            <div className="flex items-start gap-2.5 rounded-xl border border-danger/25 bg-danger/[0.055] px-4 py-3">
              <Info className="mt-0.5 size-4 shrink-0 text-danger" />
              <p className="text-[12px] leading-relaxed text-danger/90">{error}</p>
            </div>
          ) : null}

          <div className="flex flex-col-reverse items-stretch gap-2 sm:flex-row sm:items-center sm:justify-between">
            <Link
              href="/"
              className="inline-flex h-10 items-center justify-center rounded-xl px-4 text-[12.5px] text-faint transition-colors hover:text-mist"
            >
              Cancel
            </Link>
            <Button
              variant="primary"
              size="lg"
              onClick={submit}
              disabled={!canSubmit}
              loading={busy}
              className="min-w-[210px]"
            >
              {phase === "idle" ? (
                <>
                  <Sparkles className="size-4" />
                  Create & process
                </>
              ) : (
                <>
                  <Loader2 className="size-4 animate-spin" />
                  {phase === "creating"
                    ? "Creating project…"
                    : phase === "uploading"
                      ? "Uploading source…"
                      : "Starting pipeline…"}
                </>
              )}
            </Button>
          </div>
        </div>

        <aside className="space-y-3 lg:sticky lg:top-6">
          <div className="panel overflow-hidden">
            <div className="border-b border-line-soft px-4 py-3">
              <p className="font-mono text-[9.5px] uppercase tracking-[0.18em] text-faint">Run summary</p>
            </div>
            <div className="space-y-3 p-4">
              <SummaryRow label="Project" value={name.trim() || "Untitled"} />
              <SummaryRow label="Source" value={sourceLabel || "Not selected"} />
              <SummaryRow
                label="Output"
                value={`${nClips} clips × ${platforms.length} platform${platforms.length === 1 ? "" : "s"}`}
              />
              <SummaryRow label="Clip window" value={`${minClip}–${maxClip}s`} />
              <SummaryRow
                label="Brand"
                value={brands.find((brand) => brand.id === brandId)?.name ?? "Default voice"}
              />
              <div className="border-t border-line-soft pt-3">
                <SummaryRow label="Estimated spend" value={formatUsd(0)} accent />
                <p className="mt-1.5 text-[10px] leading-relaxed text-faint">
                  The default Groq preset is free; live calls are metered against your budget.
                </p>
              </div>
            </div>
          </div>

          <div className="rounded-xl border border-line bg-void/50 p-4">
            <div className="flex items-center gap-2 text-[11.5px] font-medium text-mist">
              <Clock3 className="size-3.5 text-lime/75" />
              What happens next
            </div>
            <ul className="mt-3 space-y-2.5">
              {[
                "Source normalized, audio extracted, frames sampled",
                "Word-level transcript + story understanding",
                "Candidate moments validated against exact quotes",
                "Per-platform copy, summary, captions, render",
                "Engagement scorecard with next tests",
              ].map((item, index) => (
                <li key={item} className="flex gap-2.5 text-[11px] leading-relaxed text-faint">
                  <span className="mt-[3px] flex size-3.5 shrink-0 items-center justify-center rounded-full border border-line font-mono text-[8px] text-muted">
                    {index + 1}
                  </span>
                  {item}
                </li>
              ))}
            </ul>
            {estimate.minutes > 0 ? (
              <p className="mt-3 border-t border-line-soft pt-3 text-[10.5px] text-faint">
                Pasted text maps to roughly {estimate.minutes.toFixed(0)} minute
                {estimate.minutes === 1 ? "" : "s"} of synthetic runtime.
              </p>
            ) : null}
          </div>

          <button
            type="button"
            onClick={runDemo}
            disabled={busy}
            className="group flex w-full items-center justify-between gap-3 rounded-xl border border-lime/15 bg-lime/[0.04] p-4 text-left transition-colors hover:bg-lime/[0.07] disabled:opacity-50"
          >
            <div>
              <p className="flex items-center gap-1.5 text-[11.5px] font-medium text-lime">
                <Wand2 className="size-3.5" />
                No file handy?
              </p>
              <p className="mt-1 text-[10.5px] leading-relaxed text-lime/55">
                Run the bundled 100-second demo with ground-truth word timings.
              </p>
            </div>
            <ChevronRight className="size-4 shrink-0 text-lime/60 transition-transform group-hover:translate-x-0.5" />
          </button>
        </aside>
      </div>
    </div>
  );
}

function SectionHeading({
  index,
  title,
  description,
}: {
  index: string;
  title: string;
  description: string;
}) {
  return (
    <div className="flex items-start gap-3 border-b border-line-soft px-5 py-4">
      <span className="mt-0.5 flex size-6 shrink-0 items-center justify-center rounded-md border border-line bg-raised font-mono text-[9.5px] text-lime">
        {index}
      </span>
      <div>
        <h2 className="text-[13.5px] font-semibold tracking-[-0.015em] text-mist">{title}</h2>
        <p className="mt-0.5 text-[11.5px] leading-relaxed text-faint">{description}</p>
      </div>
    </div>
  );
}

function SummaryRow({
  label,
  value,
  accent,
}: {
  label: string;
  value: string;
  accent?: boolean;
}) {
  return (
    <div className="flex items-start justify-between gap-4">
      <span className="text-[11px] text-faint">{label}</span>
      <span
        className={cn(
          "max-w-[190px] truncate text-right text-[11.5px] font-medium",
          accent ? "font-mono text-lime" : "text-mist",
        )}
        title={value}
      >
        {value}
      </span>
    </div>
  );
}
