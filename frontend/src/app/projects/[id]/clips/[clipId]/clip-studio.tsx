"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import {
  ArrowLeft,
  ChevronRight,
  Clock3,
  Copy,
  Download,
  FileText,
  Film,
  Loader2,
  RefreshCw,
  RotateCcw,
  Save,
  Scissors,
  Sparkles,
  TriangleAlert,
  Wand2,
  Waves,
} from "lucide-react";
import { api, ApiError, mediaUrl } from "@/lib/api";
import type { Clip, Project } from "@/lib/types";
import { PLATFORMS, platformMeta } from "@/lib/platforms";
import { cn, formatDuration, formatTimecode } from "@/lib/utils";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Field, Input, Textarea } from "@/components/ui/input";
import { Skeleton } from "@/components/ui/skeleton";
import { Tabs } from "@/components/ui/tabs";
import { EmptyState } from "@/components/ui/empty-state";
import { useCopyToClipboard, useDocumentTitle, useToast } from "@/components/ui/toast";
import { StatusBadge } from "@/components/status-badge";

interface VariantDraft {
  platform: string;
  caption: string;
  hooks: string[];
  hashtags: string[];
  cta: string;
  version: number;
}

function draftsFromClip(clip: Clip): Record<string, VariantDraft> {
  const result: Record<string, VariantDraft> = {};
  for (const variant of clip.copy_variants) {
    result[variant.platform] = {
      platform: variant.platform,
      caption: variant.caption,
      hooks: [...variant.hooks],
      hashtags: [...variant.hashtags],
      cta: variant.cta,
      version: variant.version,
    };
  }
  return result;
}

export function ClipStudio({ projectId, clipId }: { projectId: string; clipId: string }) {
  const router = useRouter();
  const { toast } = useToast();
  const copyToClipboard = useCopyToClipboard();
  const [clip, setClip] = useState<Clip | null>(null);
  const [project, setProject] = useState<Project | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [tab, setTab] = useState("copy");
  const [activePlatform, setActivePlatform] = useState("instagram");
  const [title, setTitle] = useState("");
  const [hook, setHook] = useState("");
  const [start, setStart] = useState(0);
  const [end, setEnd] = useState(0);
  const [drafts, setDrafts] = useState<Record<string, VariantDraft>>({});
  const [dirty, setDirty] = useState(false);
  const [saving, setSaving] = useState(false);
  const [rendering, setRendering] = useState(false);
  const [regenerating, setRegenerating] = useState(false);
  const [repicking, setRepicking] = useState(false);
  const [copyFeedback, setCopyFeedback] = useState("");
  const [clipFeedback, setClipFeedback] = useState("");
  const [cacheBust, setCacheBust] = useState(0);
  const videoRef = useRef<HTMLVideoElement | null>(null);

  const applyClip = useCallback((next: Clip) => {
    setClip(next);
    setTitle(next.title);
    setHook(next.hook);
    setStart(next.start);
    setEnd(next.end);
    setDrafts(draftsFromClip(next));
    setDirty(false);
  }, []);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const [clipResult, projectResult] = await Promise.all([
        api.getClip(clipId),
        api.getProject(projectId),
      ]);
      applyClip(clipResult);
      setProject(projectResult);
      const firstPlatform = clipResult.copy_variants[0]?.platform ?? "instagram";
      setActivePlatform(firstPlatform);
      setError(null);
    } catch (reason) {
      setError(
        reason instanceof ApiError
          ? reason.status === 404
            ? "This clip does not exist, or it was replaced by a newer run."
            : reason.detail
          : "Could not load this clip.",
      );
    } finally {
      setLoading(false);
    }
  }, [clipId, projectId, applyClip]);

  useEffect(() => {
    void load();
  }, [load]);

  useDocumentTitle(clip?.title ?? "Clip studio");

  const asset = project?.assets?.[0] ?? null;
  const duration = asset?.duration_s ?? Math.max(end, 1);
  const trimDirty = Boolean(clip && (Math.abs(start - clip.start) > 0.01 || Math.abs(end - clip.end) > 0.01));
  const useRendered = Boolean(clip?.media_url && clip.status === "rendered" && !trimDirty);
  const previewSource = useRendered ? mediaUrl(clip?.media_url) : mediaUrl(asset?.media_url);
  const activeDraft = drafts[activePlatform];
  const platform = platformMeta(activePlatform);

  const markDirty = () => setDirty(true);

  const updateDraft = (patch: Partial<VariantDraft>) => {
    if (!activeDraft) return;
    setDrafts((current) => ({
      ...current,
      [activePlatform]: { ...activeDraft, ...patch },
    }));
    markDirty();
  };

  const setHookAt = (index: number, value: string) => {
    if (!activeDraft) return;
    const hooks = [...activeDraft.hooks];
    hooks[index] = value;
    updateDraft({ hooks });
  };

  const addHook = () => {
    if (!activeDraft || activeDraft.hooks.length >= 5) return;
    updateDraft({ hooks: [...activeDraft.hooks, ""] });
  };

  const removeHook = (index: number) => {
    if (!activeDraft) return;
    updateDraft({ hooks: activeDraft.hooks.filter((_, itemIndex) => itemIndex !== index) });
  };

  const save = async () => {
    if (!clip) return;
    if (!title.trim()) {
      toast({ title: "Give the clip a title", tone: "error" });
      return;
    }
    if (end - start < 8) {
      toast({ title: "Clips need at least 8 seconds", tone: "error" });
      return;
    }
    if (end > duration + 0.1) {
      toast({ title: "The clip extends past the source", description: `Source is ${formatDuration(duration)} long.`, tone: "error" });
      return;
    }
    setSaving(true);
    try {
      const next = await api.updateClip(clip.id, {
        title: title.trim(),
        hook: hook.trim(),
        start: Number(start.toFixed(2)),
        end: Number(end.toFixed(2)),
        variants: Object.values(drafts)
          .filter((draft) => draft.platform)
          .map((draft) => ({
            platform: draft.platform,
            caption: draft.caption,
            hooks: draft.hooks.filter((item) => item.trim()),
            hashtags: draft.hashtags,
            cta: draft.cta,
          })),
      });
      const trimmed = Math.abs(next.start - clip.start) > 0.01 || Math.abs(next.end - clip.end) > 0.01;
      applyClip(next);
      toast({
        title: trimmed ? "Timing saved — render the clip again" : "Changes saved",
        description: trimmed ? "Burned-in captions still match the old cut." : "Your edits are live.",
        tone: "success",
      });
      if (trimmed) setTab("edit");
    } catch (reason) {
      toast({
        title: "Could not save changes",
        description: reason instanceof ApiError ? reason.detail : "Try again in a moment.",
        tone: "error",
      });
    } finally {
      setSaving(false);
    }
  };

  const regenerateCopy = async () => {
    if (!clip) return;
    setRegenerating(true);
    try {
      const next = await api.regenerateClip(clip.id, {
        kind: "copy",
        platform: activePlatform,
        feedback: copyFeedback.trim(),
      });
      applyClip(next);
      setCopyFeedback("");
      toast({
        title: `${platform.label} copy rewritten`,
        description: copyFeedback.trim() ? "Your direction was applied." : "A fresh variant is ready.",
        tone: "success",
      });
    } catch (reason) {
      toast({
        title: "Could not rewrite the copy",
        description: reason instanceof ApiError ? reason.detail : "Try again in a moment.",
        tone: "error",
      });
    } finally {
      setRegenerating(false);
    }
  };

  const repick = async () => {
    if (!clip) return;
    setRepicking(true);
    try {
      const next = await api.regenerateClip(clip.id, {
        kind: "clip",
        feedback: clipFeedback.trim(),
      });
      applyClip(next);
      setClipFeedback("");
      setCacheBust((value) => value + 1);
      toast({
        title: "A new moment was selected",
        description: "Review the new timing and copy, then render.",
        tone: "success",
      });
    } catch (reason) {
      toast({
        title: "Could not pick a new moment",
        description: reason instanceof ApiError ? reason.detail : "Try again with different feedback.",
        tone: "error",
      });
    } finally {
      setRepicking(false);
    }
  };

  const render = async () => {
    if (!clip) return;
    setRendering(true);
    try {
      const next = await api.renderClip(clip.id);
      applyClip(next);
      setCacheBust((value) => value + 1);
      toast({
        title: "Vertical clip rendered",
        description: "1080×1920 with burned-in captions and a fresh thumbnail.",
        tone: "success",
      });
    } catch (reason) {
      toast({
        title: "Render failed",
        description: reason instanceof ApiError ? reason.detail : "Check that FFmpeg is available.",
        tone: "error",
      });
    } finally {
      setRendering(false);
    }
  };

  useEffect(() => {
    if (!previewSource || useRendered) return;
    const element = videoRef.current;
    if (element) {
      try {
        element.currentTime = start;
      } catch {
        // Metadata may not be ready yet; loadedmetadata handles it.
      }
    }
  }, [previewSource, start, useRendered]);

  if (loading) return <StudioSkeleton />;

  if (!clip || !project) {
    return (
      <div className="mx-auto max-w-xl py-20 text-center">
        <div className="mx-auto flex size-12 items-center justify-center rounded-2xl border border-line bg-raised text-faint">
          <Scissors className="size-5" />
        </div>
        <h1 className="mt-5 text-xl font-semibold tracking-[-0.03em] text-mist">Clip not found</h1>
        <p className="mt-2 text-[13px] text-muted">{error ?? "It may have been replaced by a newer run."}</p>
        <Button variant="secondary" className="mt-6" onClick={() => router.push(`/projects/${projectId}`)}>
          <ArrowLeft className="size-3.5" />
          Back to project
        </Button>
      </div>
    );
  }

  const captionCount = activeDraft?.caption.length ?? 0;
  const overLimit = captionCount > platform.captionLimit;

  return (
    <div className="animate-in">
      <div className="mb-5 flex flex-wrap items-center justify-between gap-3">
        <Link
          href={`/projects/${projectId}`}
          className="inline-flex min-w-0 items-center gap-1.5 text-[11.5px] text-faint transition-colors hover:text-mist"
        >
          <ArrowLeft className="size-3.5 shrink-0" />
          <span className="max-w-[180px] truncate">{project.name}</span>
          <ChevronRight className="size-3 shrink-0 text-faint/60" />
          <span className="text-muted">Clip studio</span>
        </Link>
        <div className="flex items-center gap-2">
          {dirty ? (
            <span className="hidden items-center gap-1.5 font-mono text-[9.5px] uppercase tracking-[0.12em] text-warning sm:flex">
              <span className="size-1.5 rounded-full bg-warning" />
              Unsaved
            </span>
          ) : null}
          <Button variant="primary" onClick={save} loading={saving} disabled={!dirty}>
            <Save className="size-3.5" />
            Save changes
          </Button>
        </div>
      </div>

      <div className="grid items-start gap-5 lg:grid-cols-[360px_minmax(0,1fr)]">
        <div className="space-y-3 lg:sticky lg:top-6">
          <div className="panel overflow-hidden">
            <div className="flex items-center justify-between border-b border-line-soft px-4 py-3">
              <div className="flex items-center gap-2">
                <span className="font-mono text-[9.5px] uppercase tracking-[0.18em] text-faint">
                  Preview
                </span>
                {useRendered ? (
                  <Badge tone="success" className="px-2 py-0 text-[9px]">
                    9:16
                  </Badge>
                ) : (
                  <Badge tone="warning" className="px-2 py-0 text-[9px]">
                    source cut
                  </Badge>
                )}
              </div>
              <StatusBadge status={clip.status} />
            </div>

            <div className="relative flex aspect-[9/16] max-h-[64vh] items-center justify-center overflow-hidden bg-black">
              {previewSource ? (
                <video
                  ref={videoRef}
                  key={`${previewSource}-${cacheBust}`}
                  src={previewSource}
                  controls
                  preload="metadata"
                  className={cn("h-full w-full", useRendered ? "object-cover" : "object-contain")}
                  onLoadedMetadata={() => {
                    const element = videoRef.current;
                    if (element && !useRendered) element.currentTime = start;
                  }}
                  onTimeUpdate={() => {
                    const element = videoRef.current;
                    if (element && !useRendered && element.currentTime >= end) {
                      element.pause();
                      element.currentTime = end;
                    }
                  }}
                />
              ) : (
                <div className="flex flex-col items-center gap-3 text-faint">
                  <Waves className="size-8" />
                  <p className="text-[11px]">Preview is available after the first render.</p>
                </div>
              )}
              {rendering ? (
                <div className="absolute inset-0 flex flex-col items-center justify-center gap-3 bg-black/75 backdrop-blur-sm">
                  <Loader2 className="size-6 animate-spin text-lime" />
                  <p className="text-[11.5px] font-medium text-mist">Rendering captions…</p>
                  <p className="text-[10px] text-faint">FFmpeg is cutting and burning in the SRT.</p>
                </div>
              ) : null}
            </div>

            <div className="flex items-center gap-2 border-t border-line-soft p-3">
              <Button
                variant={clip.status === "rendered" ? "secondary" : "primary"}
                className="flex-1"
                onClick={render}
                loading={rendering}
                disabled={rendering}
              >
                <Film className="size-3.5" />
                {clip.status === "rendered" ? "Re-render" : "Render clip"}
              </Button>
              <Button
                variant="secondary"
                size="icon"
                aria-label="Download rendered clip"
                disabled={!clip.media_url}
                onClick={() => {
                  if (clip.media_url) window.location.assign(mediaUrl(clip.media_url)!);
                }}
              >
                <Download className="size-3.5" />
              </Button>
              <Button
                variant="secondary"
                size="icon"
                aria-label="Download SRT captions"
                disabled={!clip.srt_url}
                onClick={() => {
                  if (clip.srt_url) window.location.assign(mediaUrl(clip.srt_url)!);
                }}
              >
                <FileText className="size-3.5" />
              </Button>
            </div>
          </div>

          <div className="panel p-4">
            <div className="flex items-center justify-between">
              <span className="font-mono text-[9.5px] uppercase tracking-[0.16em] text-faint">
                Moment
              </span>
              <span className="flex items-center gap-1.5 font-mono text-[10px] text-muted">
                <Clock3 className="size-3 text-faint" />
                {formatTimecode(start)} → {formatTimecode(end)}
              </span>
            </div>
            <div className="mt-3 flex items-center gap-3">
              <ScoreDial value={Math.round(clip.score)} />
              <div className="min-w-0">
                <p className="text-[11.5px] font-medium text-mist">
                  {formatDuration(end - start)} clip
                </p>
                <p className="mt-0.5 line-clamp-2 text-[10px] leading-relaxed text-faint">
                  {clip.rationale}
                </p>
              </div>
            </div>
            {clip.risk_flags_json.length > 0 ? (
              <div className="mt-3 flex items-start gap-2 rounded-lg border border-warning/20 bg-warning/[0.045] p-2.5">
                <TriangleAlert className="mt-0.5 size-3.5 shrink-0 text-warning" />
                <div>
                  <p className="text-[10px] font-medium text-warning">Review before publishing</p>
                  <p className="mt-0.5 font-mono text-[9px] leading-relaxed text-warning/70">
                    {clip.risk_flags_json.join(" · ")}
                  </p>
                </div>
              </div>
            ) : null}
          </div>
        </div>

        <div className="min-w-0">
          <div className="mb-4 flex flex-wrap items-center justify-between gap-3">
            <Tabs
              items={[
                { value: "copy", label: "Platform copy", icon: <Sparkles className="size-3" /> },
                { value: "edit", label: "Edit clip", icon: <Scissors className="size-3" /> },
              ]}
              value={tab}
              onValueChange={setTab}
            />
            <span className="font-mono text-[9px] uppercase tracking-[0.14em] text-faint">
              {clip.copy_variants.length} platform{clip.copy_variants.length === 1 ? "" : "s"} written
            </span>
          </div>

          {tab === "copy" ? (
            <div className="space-y-3">
              <div className="flex flex-wrap gap-1.5">
                {PLATFORMS.map((item) => {
                  const Icon = item.icon;
                  const available = Boolean(drafts[item.id]);
                  return (
                    <button
                      key={item.id}
                      type="button"
                      onClick={() => setActivePlatform(item.id)}
                      className={cn(
                        "inline-flex h-9 items-center gap-2 rounded-xl border px-3 text-[11.5px] font-medium transition-all",
                        activePlatform === item.id
                          ? "border-lime/35 bg-lime/[0.075] text-mist"
                          : "border-line bg-void text-faint hover:border-[#3a4135] hover:text-muted",
                      )}
                    >
                      <Icon className="size-3.5" style={{ color: available ? item.accent : undefined }} />
                      {item.label}
                      {available ? (
                        <span className="size-1 rounded-full bg-lime/70" />
                      ) : (
                        <span className="font-mono text-[8px] uppercase text-faint/60">new</span>
                      )}
                    </button>
                  );
                })}
              </div>

              {activeDraft ? (
                <div className="panel overflow-hidden">
                  <div className="flex flex-wrap items-center justify-between gap-2 border-b border-line-soft px-4 py-3">
                    <div className="flex items-center gap-2">
                      <span className="text-[12.5px] font-semibold text-mist">{platform.label}</span>
                      <Badge tone="outline" className="px-2 py-0 text-[9px] uppercase tracking-wider">
                        v{activeDraft.version}
                      </Badge>
                    </div>
                    <span className="font-mono text-[9px] text-faint">{platform.hint}</span>
                  </div>

                  <div className="space-y-4 p-4">
                    <Field label="Caption">
                      <Textarea
                        value={activeDraft.caption}
                        onChange={(event) => updateDraft({ caption: event.target.value })}
                        rows={7}
                        className="min-h-[160px] text-[12.5px]"
                      />
                      <div className="flex items-center justify-between text-[10px]">
                        <span className="text-faint">Platform-native, grounded in the transcript.</span>
                        <span className={cn("font-mono tabular-nums", overLimit ? "text-danger" : "text-faint")}>
                          {captionCount.toLocaleString()} / {platform.captionLimit.toLocaleString()}
                        </span>
                      </div>
                    </Field>

                    <div>
                      <div className="mb-2 flex items-center justify-between">
                        <span className="text-[12px] font-medium text-muted">Hook variants</span>
                        <button
                          type="button"
                          onClick={addHook}
                          disabled={activeDraft.hooks.length >= 5}
                          className="text-[10px] font-medium text-lime/75 transition-colors hover:text-lime disabled:opacity-40"
                        >
                          + Add hook
                        </button>
                      </div>
                      <div className="space-y-2">
                        {activeDraft.hooks.map((item, index) => (
                          <div key={index} className="flex items-center gap-2">
                            <span className="w-5 shrink-0 font-mono text-[9px] text-faint">
                              {String(index + 1).padStart(2, "0")}
                            </span>
                            <Input
                              value={item}
                              onChange={(event) => setHookAt(index, event.target.value)}
                              placeholder="A promise with a little danger in it"
                              className="h-9 text-[12px]"
                            />
                            <button
                              type="button"
                              onClick={() => removeHook(index)}
                              aria-label={`Remove hook ${index + 1}`}
                              className="shrink-0 rounded p-1 text-faint hover:text-danger"
                            >
                              <RotateCcw className="size-3" />
                            </button>
                          </div>
                        ))}
                      </div>
                    </div>

                    <div className="grid gap-4 sm:grid-cols-2">
                      <Field label="Hashtags" hint="Space-separated. Platform-safe tags only.">
                        <Input
                          value={activeDraft.hashtags.join(" ")}
                          onChange={(event) =>
                            updateDraft({
                              hashtags: event.target.value
                                .split(/\s+/)
                                .map((tag) => tag.trim())
                                .filter(Boolean),
                            })
                          }
                          placeholder="#creators #contentstrategy"
                          className="h-9 text-[12px]"
                        />
                      </Field>
                      <Field label="Call to action">
                        <Input
                          value={activeDraft.cta}
                          onChange={(event) => updateDraft({ cta: event.target.value })}
                          placeholder="Save this for your next recording."
                          className="h-9 text-[12px]"
                        />
                      </Field>
                    </div>

                    <div className="flex flex-wrap items-center justify-between gap-2 border-t border-line-soft pt-3">
                      <Button
                        variant="ghost"
                        size="sm"
                        onClick={() =>
                          void copyToClipboard(
                            `${activeDraft.caption}\n\n${activeDraft.hashtags.join(" ")}\n\n${activeDraft.cta}`,
                            `${platform.label} copy copied`,
                          )
                        }
                      >
                        <Copy className="size-3.5" />
                        Copy post
                      </Button>
                      <Button variant="secondary" size="sm" onClick={save} loading={saving} disabled={!dirty}>
                        <Save className="size-3.5" />
                        Save
                      </Button>
                    </div>
                  </div>
                </div>
              ) : (
                <EmptyState
                  icon={<Sparkles className="size-5" />}
                  title={`No ${platform.label} copy yet`}
                  description="Generate a platform-native variant grounded in this clip's transcript. It will use the project's brand profile and banned-word rules."
                  action={
                    <Button variant="primary" onClick={regenerateCopy} loading={regenerating}>
                      <Wand2 className="size-3.5" />
                      Write {platform.label} copy
                    </Button>
                  }
                  className="bg-void/25"
                />
              )}

              <div className="panel p-4">
                <div className="flex items-center gap-2">
                  <Wand2 className="size-3.5 text-lime/70" />
                  <p className="text-[12px] font-medium text-mist">Rewrite with direction</p>
                </div>
                <p className="mt-1 text-[10.5px] leading-relaxed text-faint">
                  Tell the model what to change. The quote, timing, and brand guardrails stay fixed.
                </p>
                <div className="mt-3 flex flex-col gap-2 sm:flex-row">
                  <Input
                    value={copyFeedback}
                    onChange={(event) => setCopyFeedback(event.target.value)}
                    placeholder="e.g. Lead with the counterintuitive claim; cut the throat-clearing."
                    className="h-9 text-[12px]"
                    onKeyDown={(event) => {
                      if (event.key === "Enter" && !event.shiftKey) {
                        event.preventDefault();
                        if (!regenerating) void regenerateCopy();
                      }
                    }}
                  />
                  <Button
                    variant="secondary"
                    onClick={regenerateCopy}
                    loading={regenerating}
                    className="shrink-0"
                  >
                    <RefreshCw className="size-3.5" />
                    Rewrite {platform.short}
                  </Button>
                </div>
              </div>
            </div>
          ) : (
            <div className="space-y-3">
              <div className="panel p-5">
                <p className="font-mono text-[9.5px] uppercase tracking-[0.18em] text-faint">
                  Direction
                </p>
                <div className="mt-4 space-y-4">
                  <Field label="Title">
                    <Input
                      value={title}
                      onChange={(event) => {
                        setTitle(event.target.value);
                        markDirty();
                      }}
                      maxLength={240}
                    />
                  </Field>
                  <Field label="Hook" hint="The first line someone hears or reads. Specific beats clever.">
                    <Textarea
                      value={hook}
                      onChange={(event) => {
                        setHook(event.target.value);
                        markDirty();
                      }}
                      rows={3}
                      className="min-h-[84px] text-[12.5px]"
                    />
                  </Field>
                  {clip.source_quote ? (
                    <div className="rounded-xl border border-line-soft bg-void/50 p-4">
                      <p className="font-mono text-[8.5px] uppercase tracking-[0.14em] text-faint">
                        Transcript quote
                      </p>
                      <p className="mt-2 text-[12px] leading-relaxed text-mist/85">“{clip.source_quote}”</p>
                      <p className="mt-2 text-[9.5px] text-faint">
                        Verified against the source transcript. Every clip must be grounded here.
                      </p>
                    </div>
                  ) : null}
                </div>
              </div>

              <div className="panel p-5">
                <div className="flex flex-wrap items-center justify-between gap-2">
                  <div>
                    <p className="font-mono text-[9.5px] uppercase tracking-[0.18em] text-faint">
                      Trim
                    </p>
                    <p className="mt-1 text-[11px] text-faint">
                      Source: {formatDuration(duration)} · selection {formatDuration(end - start)}
                    </p>
                  </div>
                  <Badge tone={trimDirty ? "warning" : "outline"}>
                    {trimDirty ? "unsaved cut" : "current cut"}
                  </Badge>
                </div>

                <div className="mt-5 space-y-4">
                  <div>
                    <div className="mb-1.5 flex items-center justify-between">
                      <span className="text-[11px] text-muted">Start</span>
                      <span className="font-mono text-[10px] tabular-nums text-mist">
                        {formatTimecode(start)}
                      </span>
                    </div>
                    <input
                      type="range"
                      min={0}
                      max={Math.max(0, end - 8)}
                      step={0.1}
                      value={start}
                      onChange={(event) => {
                        setStart(Math.min(Number(event.target.value), end - 8));
                        markDirty();
                      }}
                      className="h-1.5 w-full cursor-pointer appearance-none rounded-full bg-white/10 accent-[#d8ff63]"
                    />
                  </div>
                  <div>
                    <div className="mb-1.5 flex items-center justify-between">
                      <span className="text-[11px] text-muted">End</span>
                      <span className="font-mono text-[10px] tabular-nums text-mist">
                        {formatTimecode(end)}
                      </span>
                    </div>
                    <input
                      type="range"
                      min={Math.min(duration, start + 8)}
                      max={duration}
                      step={0.1}
                      value={end}
                      onChange={(event) => {
                        setEnd(Math.max(Number(event.target.value), start + 8));
                        markDirty();
                      }}
                      className="h-1.5 w-full cursor-pointer appearance-none rounded-full bg-white/10 accent-[#d8ff63]"
                    />
                  </div>
                  <div className="grid grid-cols-2 gap-3">
                    <Field label="Start (seconds)">
                      <Input
                        type="number"
                        min={0}
                        max={Math.max(0, end - 8)}
                        step={0.1}
                        value={start}
                        onChange={(event) => {
                          setStart(Math.max(0, Math.min(Number(event.target.value), end - 8)));
                          markDirty();
                        }}
                        className="h-9 font-mono text-[11px]"
                      />
                    </Field>
                    <Field label="End (seconds)">
                      <Input
                        type="number"
                        min={start + 8}
                        max={duration}
                        step={0.1}
                        value={end}
                        onChange={(event) => {
                          setEnd(Math.max(start + 8, Math.min(Number(event.target.value), duration)));
                          markDirty();
                        }}
                        className="h-9 font-mono text-[11px]"
                      />
                    </Field>
                  </div>
                  {trimDirty ? (
                    <p className="flex items-start gap-1.5 text-[10px] leading-relaxed text-warning/80">
                      <TriangleAlert className="mt-0.5 size-3 shrink-0" />
                      Saving a new cut invalidates the current render. Save, then render again.
                    </p>
                  ) : null}
                </div>
              </div>

              <div className="panel p-5">
                <div className="flex items-center gap-2">
                  <RotateCcw className="size-3.5 text-lime/70" />
                  <p className="text-[12px] font-medium text-mist">Pick a different moment</p>
                </div>
                <p className="mt-1 text-[10.5px] leading-relaxed text-faint">
                  Finds the strongest non-overlapping moment in the transcript. This replaces the timing,
                  title, hook, and all platform copy, then asks you to render again.
                </p>
                <div className="mt-3 flex flex-col gap-2 sm:flex-row">
                  <Input
                    value={clipFeedback}
                    onChange={(event) => setClipFeedback(event.target.value)}
                    placeholder="e.g. Find something about distribution, not capture."
                    className="h-9 text-[12px]"
                  />
                  <Button variant="secondary" onClick={repick} loading={repicking} className="shrink-0">
                    <RotateCcw className="size-3.5" />
                    Re-pick moment
                  </Button>
                </div>
              </div>

              <div className="panel p-5">
                <p className="font-mono text-[9.5px] uppercase tracking-[0.18em] text-faint">
                  Why this clip
                </p>
                <p className="mt-3 text-[12px] leading-relaxed text-muted">{clip.rationale}</p>
                <div className="mt-4 grid grid-cols-3 gap-2">
                  <Stat label="Score" value={String(Math.round(clip.score))} />
                  <Stat label="Length" value={formatDuration(end - start)} />
                  <Stat label="Platforms" value={String(clip.copy_variants.length)} />
                </div>
              </div>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}

function ScoreDial({ value }: { value: number }) {
  return (
    <div className="relative flex size-11 shrink-0 items-center justify-center">
      <svg viewBox="0 0 44 44" className="absolute inset-0 -rotate-90" aria-hidden>
        <circle cx="22" cy="22" r="18" fill="none" stroke="rgba(255,255,255,0.07)" strokeWidth="3" />
        <circle
          cx="22"
          cy="22"
          r="18"
          fill="none"
          stroke="#d8ff63"
          strokeWidth="3"
          strokeLinecap="round"
          strokeDasharray={`${(value / 100) * 113} 113`}
        />
      </svg>
      <span className="font-mono text-[11px] font-semibold tabular-nums text-mist">{value}</span>
    </div>
  );
}

function Stat({ label, value }: { label: string; value: string }) {
  return (
    <div className="rounded-lg border border-line-soft bg-void/40 px-2.5 py-2">
      <p className="font-mono text-[8px] uppercase tracking-[0.12em] text-faint">{label}</p>
      <p className="mt-0.5 text-[11px] font-medium tabular-nums text-mist">{value}</p>
    </div>
  );
}

function StudioSkeleton() {
  return (
    <div className="animate-in">
      <Skeleton className="h-3 w-64" />
      <div className="mt-6 grid gap-5 lg:grid-cols-[360px_minmax(0,1fr)]">
        <div className="space-y-3">
          <Skeleton className="aspect-[9/16] rounded-2xl" />
          <Skeleton className="h-24 rounded-2xl" />
        </div>
        <div className="space-y-3">
          <Skeleton className="h-10 w-64" />
          <Skeleton className="h-[480px] rounded-2xl" />
        </div>
      </div>
    </div>
  );
}
