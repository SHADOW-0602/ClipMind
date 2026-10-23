import Link from "next/link";
import { ArrowUpRight, Clock3, Film, TriangleAlert } from "lucide-react";
import type { Clip } from "@/lib/types";
import { mediaUrl } from "@/lib/api";
import { formatDuration, formatTimecode, truncate } from "@/lib/utils";
import { platformMeta } from "@/lib/platforms";
import { StatusBadge } from "./status-badge";

export function ClipCard({
  clip,
  projectId,
  index = 0,
}: {
  clip: Clip;
  projectId: string;
  index?: number;
}) {
  const thumbnail = mediaUrl(clip.thumbnail_url);
  return (
    <Link
      href={`/projects/${projectId}/clips/${clip.id}`}
      className="panel panel-hover group animate-in flex gap-4 overflow-hidden p-3"
      style={{ animationDelay: `${Math.min(index, 8) * 40}ms` }}
    >
      <div className="relative aspect-[9/16] w-[92px] shrink-0 overflow-hidden rounded-lg border border-line-soft bg-[#0c0e0c]">
        {thumbnail ? (
          // eslint-disable-next-line @next/next/no-img-element
          <img
            src={thumbnail}
            alt=""
            className="h-full w-full object-cover transition duration-500 group-hover:scale-[1.03]"
          />
        ) : (
          <div className="dot-grid flex h-full items-center justify-center">
            <Film className="size-4 text-faint" />
          </div>
        )}
        <span className="absolute left-1.5 top-1.5 rounded bg-black/65 px-1.5 py-0.5 font-mono text-[9px] font-medium text-white/90 backdrop-blur">
          {Math.round(clip.score)}
        </span>
        <span className="absolute bottom-1.5 right-1.5 rounded bg-black/65 px-1.5 py-0.5 font-mono text-[8.5px] text-white/80 backdrop-blur">
          {formatDuration(clip.end - clip.start)}
        </span>
      </div>

      <div className="flex min-w-0 flex-1 flex-col py-0.5">
        <div className="flex items-start justify-between gap-2">
          <h3 className="line-clamp-2 text-[12.5px] font-semibold leading-snug tracking-[-0.01em] text-mist group-hover:text-lime/95">
            {clip.title}
          </h3>
          <ArrowUpRight className="mt-0.5 size-3.5 shrink-0 text-faint opacity-0 transition-opacity group-hover:opacity-100" />
        </div>
        {clip.hook ? (
          <p className="mt-1 line-clamp-2 text-[10.5px] leading-relaxed text-faint">{truncate(clip.hook, 110)}</p>
        ) : null}

        <div className="mt-auto space-y-2 pt-2.5">
          <div className="flex items-center gap-2 text-[10px] text-faint">
            <Clock3 className="size-3" />
            <span className="font-mono tabular-nums">
              {formatTimecode(clip.start)} → {formatTimecode(clip.end)}
            </span>
          </div>
          <div className="flex flex-wrap items-center gap-1.5">
            <StatusBadge status={clip.status} />
            {clip.copy_variants.slice(0, 5).map((variant) => {
              const meta = platformMeta(variant.platform);
              return (
                <span
                  key={variant.id}
                  title={meta.label}
                  className="flex size-5 items-center justify-center rounded border border-line bg-void font-mono text-[8.5px] font-semibold"
                  style={{ color: meta.accent }}
                >
                  {meta.short}
                </span>
              );
            })}
            {clip.risk_flags_json.length > 0 ? (
              <span
                className="inline-flex items-center gap-1 text-[9.5px] text-warning"
                title={clip.risk_flags_json.join(", ")}
              >
                <TriangleAlert className="size-3" />
                review
              </span>
            ) : null}
          </div>
        </div>
      </div>
    </Link>
  );
}
