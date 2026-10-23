"use client";

import { AudioLines, FileText, Film, Maximize2, Play } from "lucide-react";
import type { MediaAsset } from "@/lib/types";
import { mediaUrl } from "@/lib/api";
import { formatBytes, formatDuration, formatNumber } from "@/lib/utils";
import { Badge } from "./ui/badge";

export function SourcePanel({
  asset,
  videoRef,
  audioRef,
}: {
  asset: MediaAsset | null;
  videoRef: React.RefObject<HTMLVideoElement | null>;
  audioRef: React.RefObject<HTMLAudioElement | null>;
}) {
  const poster = asset?.frames?.[0]?.url ? mediaUrl(asset.frames[0].url) : undefined;
  const media = mediaUrl(asset?.media_url);

  if (!asset) {
    return (
      <div className="panel p-5">
        <p className="font-mono text-[9.5px] uppercase tracking-[0.18em] text-faint">Source</p>
        <p className="mt-3 text-[12px] text-faint">No source attached yet.</p>
      </div>
    );
  }

  return (
    <div className="panel overflow-hidden">
      <div className="flex items-center justify-between border-b border-line-soft px-4 py-3">
        <p className="font-mono text-[9.5px] uppercase tracking-[0.18em] text-faint">Source</p>
        <Badge tone="outline" className="px-2 py-0 text-[9.5px] uppercase tracking-wider">
          {asset.kind}
        </Badge>
      </div>

      {asset.kind === "video" && media ? (
        <div className="group relative aspect-video bg-black">
          <video
            ref={videoRef}
            src={media}
            poster={poster}
            controls
            preload="metadata"
            className="h-full w-full object-contain"
          />
          <div className="pointer-events-none absolute right-2 top-2 flex items-center gap-1 rounded-md border border-white/10 bg-black/50 px-1.5 py-1 font-mono text-[8.5px] text-white/70 opacity-0 backdrop-blur transition-opacity group-hover:opacity-100">
            <Maximize2 className="size-2.5" />
            1080 × 1920 render
          </div>
        </div>
      ) : null}

      {asset.kind === "audio" && media ? (
        <div className="relative overflow-hidden bg-[#0c0f0c] p-4">
          <div className="pointer-events-none absolute inset-x-0 top-0 flex h-16 items-center justify-center gap-[3px] px-6 opacity-30">
            {Array.from({ length: 44 }).map((_, index) => (
              <span
                key={index}
                className="w-[3px] rounded-full bg-lime"
                style={{ height: `${12 + Math.abs(Math.sin(index * 0.8)) * 38}px` }}
              />
            ))}
          </div>
          <div className="relative flex items-center gap-3 pt-10">
            <span className="flex size-9 shrink-0 items-center justify-center rounded-full bg-lime/10 text-lime">
              <AudioLines className="size-4" />
            </span>
            <div className="min-w-0 flex-1">
              <p className="truncate text-[12px] font-medium text-mist">{asset.original_filename}</p>
              <p className="font-mono text-[10px] text-faint">{formatDuration(asset.duration_s)}</p>
            </div>
          </div>
          <audio ref={audioRef} src={media} controls className="relative mt-3 w-full" preload="metadata" />
        </div>
      ) : null}

      {asset.kind === "text" ? (
        <div className="relative bg-[#0c0f0c] p-5">
          <div className="dot-grid pointer-events-none absolute inset-0 opacity-30" />
          <div className="relative flex items-start gap-3">
            <span className="flex size-9 shrink-0 items-center justify-center rounded-xl border border-line bg-raised text-muted">
              <FileText className="size-4" />
            </span>
            <div className="min-w-0">
              <p className="truncate text-[12px] font-medium text-mist">{asset.original_filename}</p>
              <p className="mt-1 text-[10.5px] leading-relaxed text-faint">
                Text source · synthetic timeline · {formatDuration(asset.duration_s)}
              </p>
            </div>
          </div>
          <div className="relative mt-4 flex items-center gap-2 rounded-lg border border-line bg-void/60 px-3 py-2 text-[10px] text-faint">
            <Play className="size-3 text-lime/70" />
            The transcript view is the source of truth for text projects.
          </div>
        </div>
      ) : null}

      <div className="grid grid-cols-2 gap-px border-t border-line-soft bg-line-soft">
        <Meta label="Duration" value={formatDuration(asset.duration_s)} />
        <Meta
          label="Format"
          value={
            asset.kind === "video"
              ? `${asset.width}×${asset.height}`
              : asset.kind === "audio"
                ? "Audio only"
                : "Plain text"
          }
        />
        <Meta label="Size" value={formatBytes(asset.size_bytes)} />
        <Meta
          label="Details"
          value={
            asset.kind === "video" && asset.fps
              ? `${asset.fps.toFixed(1)} fps`
              : asset.kind === "text"
                ? `${formatNumber(asset.duration_s)}s synthetic`
                : "Normalized"
          }
        />
      </div>
      <div className="flex items-center gap-2 border-t border-line-soft px-4 py-2.5">
        <Film className="size-3 text-faint" />
        <p className="truncate font-mono text-[9px] text-faint" title={asset.original_filename}>
          {asset.original_filename}
        </p>
      </div>
    </div>
  );
}

function Meta({ label, value }: { label: string; value: string }) {
  return (
    <div className="bg-surface px-4 py-2.5">
      <p className="font-mono text-[8.5px] uppercase tracking-[0.14em] text-faint">{label}</p>
      <p className="mt-0.5 text-[11px] font-medium tabular-nums text-mist">{value}</p>
    </div>
  );
}
