import Link from "next/link";
import { ArrowLeft, Compass } from "lucide-react";

export default function NotFound() {
  return (
    <div className="mx-auto flex min-h-[70vh] max-w-lg flex-col items-center justify-center text-center">
      <div className="flex size-14 items-center justify-center rounded-2xl border border-line bg-raised text-faint">
        <Compass className="size-6" />
      </div>
      <p className="mt-6 font-mono text-[10px] uppercase tracking-[0.24em] text-lime/70">404 · off script</p>
      <h1 className="mt-3 text-balance text-3xl font-semibold tracking-[-0.04em] text-mist">
        This moment is not in the transcript.
      </h1>
      <p className="mt-3 text-[13px] leading-relaxed text-muted">
        The page you are looking for does not exist, or the project was deleted.
      </p>
      <Link
        href="/"
        className="mt-7 inline-flex h-10 items-center gap-2 rounded-xl border border-line bg-raised px-4 text-[12.5px] font-medium text-mist transition-colors hover:border-[#3a4135] hover:bg-elevated"
      >
        <ArrowLeft className="size-3.5" />
        Back to projects
      </Link>
    </div>
  );
}
