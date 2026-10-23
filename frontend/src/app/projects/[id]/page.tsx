import type { Metadata } from "next";
import { ProjectWorkspace } from "./workspace";

export const metadata: Metadata = {
  title: "Project workspace",
};

export default async function ProjectPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  return <ProjectWorkspace projectId={id} />;
}
