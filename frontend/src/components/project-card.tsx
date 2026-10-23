import { cn, formatDuration, formatRelative, pluralize } from "@/lib/utils";
import type { ProjectListItem } from "@/lib/types";
import Link from "next/link";
import { ArrowUpRight, Film, Play } from "lucide-react";
import { StatusBadge } from "./status-badge";
import { mediaUrl } from "@/lib/api";

export function ProjectCard({ project, index = 0 }: { project: ProjectListItem; index?: number }) {
  const thumbnail = mediaUrl(project.thumbnail_url);
  return (
    <Link
      href={`/projects/${project.id}`}
      className="panel panel-hover group animate-in relative flex flex-col overflow-hidden"
      style={{ animationDelay: `${Math.min(index, 8) * 45}ms` }}
    >
      <div className="relative aspect-[16/9] overflow-hidden border-b border-line-soft bg-[#0d0f0d]">
        {thumbnail ? (
          // eslint-disable-next-line @next/next/no-img-element
          <img
            src={thumbnail}
            alt=""
            className="h-full w-full object-cover opacity-90 transition duration-500 group-hover:scale-[1.025] group-hover:opacity-100"
          />
        ) : (
          <div className="dot-grid flex h-full w-full items-center justify-center bg-[radial-gradient(circle_at_30%_20%,rgba(216,255,99,0.09),transparent_55%)]">
            <span className="flex size-11 items-center justify-center rounded-full border border-white/10 bg-black/30 text-muted backdrop-blur">
              <Film className="size-4" />
            </span>
          </div>
        )}
        <div className="absolute inset-x-0 top-0 flex items-start justify-between p-3">
          <StatusBadge status={project.status} />
          <span className="flex size-7 items-center justify-center rounded-full border border-white/10 bg-black/45 text-white/70 opacity-0 backdrop-blur transition-opacity group-hover:opacity-100">
            <ArrowUpRight className="size-3.5" />
          </span>
        </div>
        {project.duration_s > 0 ? (
          <div className="absolute bottom-3 left-3 flex items-center gap-1.5 rounded-md border border-white/10 bg-black/60 px-2 py-1 font-mono text-[10px] tabular-nums text-white/85 backdrop-blur">
            <Play className="size-2.5 fill-current" />
            {formatDuration(project.duration_s)}
          </div>
        ) : null}
        {project.clip_count > 0 ? (
          <div className="absolute bottom-3 right-3 rounded-md border border-white/10 bg-black/60 px-2 py-1 font-mono text-[10px] text-white/85 backdrop-blur">
            {pluralize(project.clip_count, "clip")}
          </div>
        ) : null}
      </div>
      <div className="flex flex-1 flex-col p-4">
        <h3 className="line-clamp-1 text-[13.5px] font-semibold tracking-[-0.015em] text-mist group-hover:text-lime/95">
          {project.name}
        </h3>
        <div className="mt-2 flex items-center justify-between gap-2">
          <span className={cn("text-[11px]", project.status === "failed" ? "text-danger" : "text-faint")}>
            {project.status === "completed"
              ? "Ready to export"
              : project.status === "processing"
                ? "Working through the pipeline"
                : project.status === "queued"
                  ? "Waiting in the queue"
                  : project.status === "failed"
                    ? "Needs attention"
                    : project.status === "uploaded"
                      ? "Source ready to process"
                      : "Not processed yet"}
          </span>
          <span className="shrink-0 text-[10.5px] text-faint">{formatRelative(project.updated_at)}</span>
        </div>
      </div>
    </Link>
  );
}
