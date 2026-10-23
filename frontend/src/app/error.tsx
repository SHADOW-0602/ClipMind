"use client";

import { useEffect } from "react";
import { useRouter } from "next/navigation";
import { AlertTriangle, RefreshCw } from "lucide-react";
import { Button } from "@/components/ui/button";

export default function GlobalError({
  error,
  reset,
}: {
  error: Error & { digest?: string };
  reset: () => void;
}) {
  const router = useRouter();
  useEffect(() => {
    console.error(error);
  }, [error]);

  return (
    <div className="mx-auto flex min-h-[60vh] max-w-lg flex-col items-center justify-center text-center">
      <div className="flex size-14 items-center justify-center rounded-2xl border border-danger/25 bg-danger/[0.06] text-danger">
        <AlertTriangle className="size-6" />
      </div>
      <h1 className="mt-6 text-2xl font-semibold tracking-[-0.03em] text-mist">Something broke on this screen</h1>
      <p className="mt-2 text-[13px] leading-relaxed text-muted">
        The API may be restarting. Try again, or return to the project list.
      </p>
      <div className="mt-6 flex gap-2">
        <Button variant="secondary" onClick={reset}>
          <RefreshCw className="size-3.5" />
          Try again
        </Button>
        <Button variant="ghost" onClick={() => router.push("/")}>
          Back to projects
        </Button>
      </div>
    </div>
  );
}
