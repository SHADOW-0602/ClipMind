"use client";

import { useMemo, useState } from "react";
import { Clock3, Copy, Search, TextQuote, Type } from "lucide-react";
import type { Transcript } from "@/lib/types";
import { formatDuration, formatTimecode, formatNumber } from "@/lib/utils";
import { Badge } from "./ui/badge";
import { EmptyState } from "./ui/empty-state";
import { Input } from "./ui/input";
import { Button } from "./ui/button";
import { useCopyToClipboard } from "./ui/toast";

export function TranscriptPanel({
  transcript,
  onSeek,
}: {
  transcript: Transcript | null;
  onSeek?: (seconds: number) => void;
}) {
  const [query, setQuery] = useState("");
  const copy = useCopyToClipboard();

  const segments = useMemo(() => {
    if (!transcript) return [];
    const needle = query.trim().toLowerCase();
    if (!needle) return transcript.segments_json;
    return transcript.segments_json.filter((segment) =>
      segment.text.toLowerCase().includes(needle),
    );
  }, [transcript, query]);

  const wordCount = useMemo(
    () =>
      transcript?.segments_json.reduce(
        (sum, segment) => sum + (segment.words?.length ?? segment.text.split(/\s+/).length),
        0,
      ) ?? 0,
    [transcript],
  );

  if (!transcript) {
    return (
      <EmptyState
        icon={<Type className="size-5" />}
        title="Transcript is not ready yet"
        description="Once the source is transcribed, the word-level transcript appears here. Every clip and quote is validated against it."
        className="bg-void/25"
      />
    );
  }

  return (
    <div className="panel overflow-hidden">
      <div className="flex flex-col gap-3 border-b border-line-soft p-4 sm:flex-row sm:items-center sm:justify-between">
        <div className="flex flex-wrap items-center gap-2">
          <Badge tone="outline" className="font-mono uppercase">
            {transcript.provider === "sample-ground-truth" ? "ground truth" : transcript.provider}
          </Badge>
          <Badge tone="outline" className="uppercase">
            {transcript.language}
          </Badge>
          <span className="font-mono text-[9.5px] text-faint">
            {formatNumber(wordCount)} words · {transcript.segments_json.length} segments
          </span>
        </div>
        <div className="flex items-center gap-2">
          <div className="relative w-full sm:w-56">
            <Search className="pointer-events-none absolute left-3 top-1/2 size-3.5 -translate-y-1/2 text-faint" />
            <Input
              value={query}
              onChange={(event) => setQuery(event.target.value)}
              placeholder="Search transcript…"
              className="h-8 pl-8 text-[11.5px]"
            />
          </div>
          <Button
            variant="ghost"
            size="icon-sm"
            aria-label="Copy transcript"
            onClick={() => void copy(transcript.text, "Transcript copied")}
          >
            <Copy className="size-3.5" />
          </Button>
        </div>
      </div>

      <div className="max-h-[620px] overflow-y-auto">
        {segments.length === 0 ? (
          <div className="p-8 text-center text-[12px] text-faint">No segments match “{query}”.</div>
        ) : (
          <div className="divide-y divide-line-soft/70">
            {segments.map((segment, index) => (
              <div
                key={`${segment.start}-${index}`}
                className="group flex gap-3 px-4 py-3 transition-colors hover:bg-white/[0.018]"
              >
                <button
                  type="button"
                  onClick={() => onSeek?.(segment.start)}
                  className="mt-0.5 flex h-6 shrink-0 items-center gap-1 rounded border border-line bg-void px-1.5 font-mono text-[9px] tabular-nums text-faint transition-colors hover:border-lime/25 hover:text-lime"
                  title="Jump to this moment in the source"
                >
                  <Clock3 className="size-2.5" />
                  {formatTimecode(segment.start)}
                </button>
                <div className="min-w-0 flex-1">
                  <p className="text-[12px] leading-[1.65] text-mist/85">
                    {segment.text}
                  </p>
                  <div className="mt-1 flex items-center gap-2 opacity-0 transition-opacity group-hover:opacity-100">
                    <button
                      type="button"
                      onClick={() => void copy(segment.text, "Segment copied")}
                      className="inline-flex items-center gap-1 text-[9px] text-faint hover:text-mist"
                    >
                      <TextQuote className="size-2.5" />
                      Copy line
                    </button>
                    <span className="text-[9px] text-faint/60">
                      {formatDuration(segment.start)} → {formatDuration(segment.end)}
                    </span>
                  </div>
                </div>
              </div>
            ))}
          </div>
        )}
      </div>
      <div className="border-t border-line-soft bg-void/30 px-4 py-2.5">
        <p className="text-[10px] text-faint">
          Word timestamps power exact clip boundaries and burned-in captions. Click any timestamp to
          jump to that moment.
        </p>
      </div>
    </div>
  );
}
