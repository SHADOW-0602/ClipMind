import type { Metadata } from "next";
import { ClipStudio } from "./clip-studio";

export const metadata: Metadata = {
  title: "Clip studio",
};

export default async function ClipStudioPage({
  params,
}: {
  params: Promise<{ id: string; clipId: string }>;
}) {
  const { id, clipId } = await params;
  return <ClipStudio projectId={id} clipId={clipId} />;
}
