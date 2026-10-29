"use client";

import { useRef, useState } from "react";
import { FileAudio, FileText, FileVideo, UploadCloud, X } from "lucide-react";
import { cn, formatBytes } from "@/lib/utils";

const ACCEPT = ".mp4,.mov,.mkv,.webm,.avi,.m4v,.mp3,.wav,.m4a,.aac,.flac,.ogg,.opus,.txt,.md,.srt,.vtt";

export function UploadDropzone({
  file,
  onFileChange,
  className,
  disabled,
}: {
  file: File | null;
  onFileChange: (file: File | null) => void;
  className?: string;
  disabled?: boolean;
}) {
  const inputRef = useRef<HTMLInputElement>(null);
  const [dragging, setDragging] = useState(false);

  const handleFiles = (files: FileList | null) => {
    const next = files?.[0];
    if (next) onFileChange(next);
  };

  const Icon = file
    ? file.type.startsWith("audio")
      ? FileAudio
      : file.type.startsWith("video") || /\.(mp4|mov|webm|mkv|avi)$/i.test(file.name)
        ? FileVideo
        : FileText
    : UploadCloud;

  if (file) {
    return (
      <div className={cn("panel flex items-center gap-3.5 p-4", className)}>
        <div className="flex size-11 shrink-0 items-center justify-center rounded-xl border border-lime/20 bg-lime/10 text-lime">
          <Icon className="size-5" />
        </div>
        <div className="min-w-0 flex-1">
          <p className="truncate text-[13px] font-medium text-mist">{file.name}</p>
          <p className="mt-0.5 font-mono text-[10.5px] text-faint">
            {formatBytes(file.size)} · {file.type || "media file"}
          </p>
        </div>
        <button
          type="button"
          onClick={() => onFileChange(null)}
          disabled={disabled}
          aria-label="Remove selected file"
          className="flex size-11 items-center justify-center rounded-lg text-faint transition-colors hover:bg-white/5 hover:text-mist disabled:opacity-40"
        >
          <X className="size-4" />
        </button>
      </div>
    );
  }

  return (
    <div
      role="button"
      tabIndex={disabled ? -1 : 0}
      aria-label="Upload a video, audio file, or transcript"
      aria-disabled={disabled || undefined}
      onClick={() => !disabled && inputRef.current?.click()}
      onKeyDown={(event) => {
        if ((event.key === "Enter" || event.key === " ") && !disabled) {
          event.preventDefault();
          inputRef.current?.click();
        }
      }}
      onDragOver={(event) => {
        event.preventDefault();
        if (!disabled) setDragging(true);
      }}
      onDragLeave={() => setDragging(false)}
      onDrop={(event) => {
        event.preventDefault();
        setDragging(false);
        if (!disabled) handleFiles(event.dataTransfer.files);
      }}
      className={cn(
        "group relative flex min-h-[190px] cursor-pointer flex-col items-center justify-center rounded-2xl border border-dashed px-6 py-8 text-center transition-all",
        dragging
          ? "border-lime/60 bg-lime/[0.055]"
          : "border-line bg-void/40 hover:border-[#414a3a] hover:bg-white/[0.02]",
        disabled && "pointer-events-none opacity-60",
        className,
      )}
    >
      <input
        ref={inputRef}
        type="file"
        accept={ACCEPT}
        className="sr-only"
        onChange={(event) => handleFiles(event.target.files)}
        tabIndex={-1}
      />
      <div
        className={cn(
          "mb-4 flex size-12 items-center justify-center rounded-2xl border transition-colors",
          dragging
            ? "border-lime/40 bg-lime/15 text-lime"
            : "border-line bg-raised text-muted group-hover:text-mist",
        )}
      >
        <UploadCloud className="size-5" />
      </div>
      <p className="text-[13px] font-medium text-mist">
        {dragging ? "Drop it — we'll take it from here" : "Drop media here, or browse"}
      </p>
      <p className="mt-1.5 max-w-xs text-[11.5px] leading-relaxed text-faint">
        MP4, MOV, WebM, MP3, WAV, M4A, or a transcript. Up to 500 MB and 2 hours.
      </p>
      <div className="mt-4 flex items-center gap-2 font-mono text-[9px] uppercase tracking-[0.14em] text-faint/80">
        <span className="rounded border border-line px-1.5 py-0.5">video</span>
        <span className="rounded border border-line px-1.5 py-0.5">audio</span>
        <span className="rounded border border-line px-1.5 py-0.5">text</span>
      </div>
    </div>
  );
}
