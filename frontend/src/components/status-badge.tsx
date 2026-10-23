import { Circle, CircleDot, Loader2, Check, AlertTriangle } from "lucide-react";
import { Badge } from "./ui/badge";

const statusMap: Record<
  string,
  { label: string; tone: "neutral" | "lime" | "success" | "warning" | "danger" | "sky" }
> = {
  draft: { label: "Draft", tone: "neutral" },
  uploaded: { label: "Ready to process", tone: "sky" },
  queued: { label: "Queued", tone: "sky" },
  processing: { label: "Processing", tone: "lime" },
  completed: { label: "Complete", tone: "success" },
  failed: { label: "Failed", tone: "danger" },
  rendered: { label: "Rendered", tone: "success" },
  selected: { label: "Needs render", tone: "warning" },
  rejected: { label: "Rejected", tone: "danger" },
  cancelled: { label: "Cancelled", tone: "neutral" },
  ready: { label: "Ready", tone: "success" },
};

export function StatusBadge({ status, className }: { status: string; className?: string }) {
  const meta = statusMap[status] ?? { label: status, tone: "neutral" as const };
  const pulse = status === "processing" || status === "running" || status === "queued";
  return (
    <Badge tone={meta.tone} className={className}>
      {pulse ? (
        <Loader2 className="size-2.5 animate-spin" />
      ) : status === "completed" || status === "rendered" || status === "ready" ? (
        <Check className="size-2.5" />
      ) : status === "failed" || status === "rejected" ? (
        <AlertTriangle className="size-2.5" />
      ) : status === "selected" ? (
        <CircleDot className="size-2.5" />
      ) : (
        <Circle className="size-2.5" />
      )}
      {meta.label}
    </Badge>
  );
}

export function StageIcon({ status }: { status: string }) {
  if (status === "complete") return <Check className="size-3.5 text-lime" />;
  if (status === "running") return <Loader2 className="size-3.5 animate-spin text-lime" />;
  if (status === "failed") return <AlertTriangle className="size-3.5 text-danger" />;
  return <Circle className="size-3 text-faint" />;
}
