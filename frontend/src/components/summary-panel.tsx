"use client";

import { BookOpen, Copy, Quote, Sparkles } from "lucide-react";
import type { Summary } from "@/lib/types";
import { formatTimecode } from "@/lib/utils";
import { useCopyToClipboard } from "./ui/toast";
import { Button } from "./ui/button";
import { EmptyState } from "./ui/empty-state";

export function SummaryPanel({
  summary,
  onSeek,
}: {
  summary: Summary | null;
  onSeek?: (seconds: number) => void;
}) {
  const copy = useCopyToClipboard();

  if (!summary) {
    return (
      <EmptyState
        icon={<BookOpen className="size-5" />}
        title="Summary is not ready yet"
        description="Run the pipeline to generate a TL;DR, key takeaways, chapters, and quotes verified against the transcript."
        className="bg-void/25"
      />
    );
  }

  const markdown = [
    "## TL;DR",
    summary.tldr,
    "",
    "## Key takeaways",
    ...summary.bullets.map((bullet) => `- ${bullet}`),
    "",
    "## Chapters",
    ...summary.chapters.map(
      (chapter) => `- **${formatTimecode(chapter.start)}** — ${chapter.title}${chapter.summary ? `. ${chapter.summary}` : ""}`,
    ),
    "",
    "## Quotes",
    ...summary.quotes.map((quote) => `> ${quote.text}\n>\n> — ${formatTimecode(quote.start)}`),
  ].join("\n");

  return (
    <div className="space-y-3">
      <div className="panel relative overflow-hidden p-5">
        <div className="pointer-events-none absolute -right-8 -top-10 size-40 rounded-full bg-lime/[0.06] blur-3xl" />
        <div className="flex items-center justify-between gap-3">
          <span className="flex items-center gap-1.5 font-mono text-[9.5px] uppercase tracking-[0.18em] text-lime/80">
            <Sparkles className="size-3" />
            TL;DR
          </span>
          <Button
            variant="ghost"
            size="sm"
            onClick={() => void copy(markdown, "Summary copied as Markdown")}
          >
            <Copy className="size-3.5" />
            Copy
          </Button>
        </div>
        <p className="mt-3 text-pretty text-[15px] font-medium leading-relaxed tracking-[-0.015em] text-mist">
          {summary.tldr}
        </p>
      </div>

      <div className="grid gap-3 lg:grid-cols-2">
        <div className="panel p-5">
          <p className="font-mono text-[9.5px] uppercase tracking-[0.18em] text-faint">Key takeaways</p>
          <ul className="mt-4 space-y-3">
            {summary.bullets.map((bullet, index) => (
              <li key={`${index}-${bullet.slice(0, 12)}`} className="flex gap-3">
                <span className="mt-0.5 flex size-5 shrink-0 items-center justify-center rounded-md border border-line bg-raised font-mono text-[9px] text-lime">
                  {String(index + 1).padStart(2, "0")}
                </span>
                <p className="text-[12px] leading-relaxed text-muted">{bullet}</p>
              </li>
            ))}
          </ul>
        </div>

        <div className="panel p-5">
          <p className="font-mono text-[9.5px] uppercase tracking-[0.18em] text-faint">Chapters</p>
          <ol className="mt-4 space-y-1">
            {summary.chapters.map((chapter, index) => (
              <li key={`${chapter.start}-${index}`}>
                <button
                  type="button"
                  onClick={() => onSeek?.(chapter.start)}
                  className="group flex w-full items-start gap-3 rounded-lg px-1.5 py-2 text-left transition-colors hover:bg-white/[0.035]"
                >
                  <span className="mt-0.5 rounded border border-line bg-void px-1.5 py-0.5 font-mono text-[9px] tabular-nums text-faint group-hover:border-lime/25 group-hover:text-lime/80">
                    {formatTimecode(chapter.start)}
                  </span>
                  <span className="min-w-0">
                    <span className="block text-[12px] font-medium text-mist">{chapter.title}</span>
                    {chapter.summary ? (
                      <span className="mt-0.5 line-clamp-2 block text-[10.5px] leading-relaxed text-faint">
                        {chapter.summary}
                      </span>
                    ) : null}
                  </span>
                </button>
              </li>
            ))}
          </ol>
        </div>
      </div>

      {summary.quotes.length > 0 ? (
        <div className="panel p-5">
          <div className="flex items-center justify-between">
            <p className="font-mono text-[9.5px] uppercase tracking-[0.18em] text-faint">Verified quotes</p>
            <span className="font-mono text-[9px] text-faint">{summary.quotes.length} found</span>
          </div>
          <div className="mt-4 grid gap-2.5 sm:grid-cols-2">
            {summary.quotes.map((quote, index) => (
              <div
                key={`${quote.start}-${index}`}
                className="group relative rounded-xl border border-line-soft bg-void/50 p-4"
              >
                <Quote className="size-3.5 text-lime/35" />
                <p className="mt-2 text-[12px] font-medium leading-relaxed text-mist/90">
                  “{quote.text}”
                </p>
                <div className="mt-3 flex items-center justify-between">
                  <button
                    type="button"
                    onClick={() => onSeek?.(quote.start)}
                    className="font-mono text-[9.5px] tabular-nums text-faint transition-colors hover:text-lime"
                  >
                    {formatTimecode(quote.start)}
                  </button>
                  <button
                    type="button"
                    aria-label="Copy quote"
                    onClick={() => void copy(quote.text, "Quote copied")}
                    className="rounded p-1 text-faint opacity-0 transition-opacity hover:text-mist group-hover:opacity-100"
                  >
                    <Copy className="size-3" />
                  </button>
                </div>
              </div>
            ))}
          </div>
        </div>
      ) : null}
    </div>
  );
}
