import type {
  BrandProfile,
  BrandProfileInput,
  Clip,
  Health,
  InsightsReport,
  Job,
  MediaAsset,
  ProcessOptions,
  Project,
  ProjectListItem,
  Summary,
  SystemInfo,
  Transcript,
  Usage,
  UsageCall,
} from "./types";

export const API_URL = (process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000").replace(/\/$/, "");

export class ApiError extends Error {
  status: number;
  detail: string;

  constructor(status: number, detail: string) {
    super(detail);
    this.name = "ApiError";
    this.status = status;
    this.detail = detail;
  }
}

async function parseError(response: Response): Promise<string> {
  try {
    const body = await response.json();
    if (typeof body?.detail === "string") return body.detail;
    if (Array.isArray(body?.detail)) {
      return body.detail
        .map((item: { msg?: string; loc?: string[] }) => item.msg ?? item.loc?.join("."))
        .filter(Boolean)
        .join(", ");
    }
    return JSON.stringify(body);
  } catch {
    return response.statusText || `Request failed (${response.status})`;
  }
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const headers = new Headers(init?.headers);
  if (init?.body && !(init.body instanceof FormData)) {
    headers.set("Content-Type", "application/json");
  }
  const response = await fetch(`${API_URL}${path}`, {
    ...init,
    headers,
    cache: "no-store",
  });
  if (!response.ok) {
    throw new ApiError(response.status, await parseError(response));
  }
  if (response.status === 204) return undefined as T;
  const contentType = response.headers.get("content-type") ?? "";
  if (!contentType.includes("application/json")) return (await response.text()) as T;
  return (await response.json()) as T;
}

export const api = {
  health: () => request<Health>("/api/health"),
  system: () => request<SystemInfo>("/api/system"),

  listProjects: () => request<ProjectListItem[]>("/api/projects"),
  getProject: (id: string) => request<Project>(`/api/projects/${id}`),
  createProject: (payload: { name: string; brand_profile_id?: string | null }) =>
    request<Project>("/api/projects", { method: "POST", body: JSON.stringify(payload) }),
  updateProject: (id: string, payload: { name?: string; brand_profile_id?: string | null }) =>
    request<Project>(`/api/projects/${id}`, { method: "PATCH", body: JSON.stringify(payload) }),
  deleteProject: (id: string) =>
    request<{ deleted: boolean }>(`/api/projects/${id}`, { method: "DELETE" }),

  createDemoProject: (brandProfileId?: string | null) =>
    request<Project>("/api/demo-project", {
      method: "POST",
      body: JSON.stringify({ brand_profile_id: brandProfileId ?? null }),
    }),

  uploadMedia: (
    projectId: string,
    payload: { file?: File; text?: string; rightsAttested: boolean; kindHint?: string },
  ) => {
    const form = new FormData();
    if (payload.file) form.set("file", payload.file);
    if (payload.text) form.set("text", payload.text);
    form.set("rights_attested", payload.rightsAttested ? "true" : "false");
    if (payload.kindHint) form.set("kind_hint", payload.kindHint);
    return request<MediaAsset>(`/api/projects/${projectId}/upload`, {
      method: "POST",
      body: form,
    });
  },

  startProcess: (projectId: string, options: ProcessOptions) =>
    request<Job>(`/api/projects/${projectId}/process`, {
      method: "POST",
      body: JSON.stringify(options),
    }),
  getJob: (jobId: string) => request<Job>(`/api/jobs/${jobId}`),
  retryJob: (jobId: string) => request<Job>(`/api/jobs/${jobId}/retry`, { method: "POST" }),

  getTranscript: (projectId: string) =>
    request<Transcript>(`/api/projects/${projectId}/transcript`),
  getSummary: (projectId: string) => request<Summary>(`/api/projects/${projectId}/summary`),
  getInsights: (projectId: string) =>
    request<{ report: InsightsReport }>(`/api/projects/${projectId}/insights`),

  getClip: (clipId: string) => request<Clip>(`/api/clips/${clipId}`),
  updateClip: (
    clipId: string,
    payload: {
      start?: number;
      end?: number;
      title?: string;
      hook?: string;
      variants?: Array<{
        platform: string;
        caption: string;
        hooks: string[];
        hashtags: string[];
        cta: string;
      }>;
    },
  ) => request<Clip>(`/api/clips/${clipId}`, { method: "PATCH", body: JSON.stringify(payload) }),
  regenerateClip: (
    clipId: string,
    payload: { kind: "copy" | "clip"; platform?: string; feedback?: string },
  ) => request<Clip>(`/api/clips/${clipId}/regenerate`, { method: "POST", body: JSON.stringify(payload) }),
  renderClip: (clipId: string) => request<Clip>(`/api/clips/${clipId}/render`, { method: "POST" }),
  deleteClip: (clipId: string) =>
    request<{ deleted: boolean }>(`/api/clips/${clipId}`, { method: "DELETE" }),

  listBrands: () => request<BrandProfile[]>("/api/brand-profiles"),
  createBrand: (payload: BrandProfileInput) =>
    request<BrandProfile>("/api/brand-profiles", { method: "POST", body: JSON.stringify(payload) }),
  updateBrand: (id: string, payload: Partial<BrandProfileInput>) =>
    request<BrandProfile>(`/api/brand-profiles/${id}`, {
      method: "PATCH",
      body: JSON.stringify(payload),
    }),
  deleteBrand: (id: string) =>
    request<{ deleted: boolean }>(`/api/brand-profiles/${id}`, { method: "DELETE" }),

  getUsage: () => request<Usage>("/api/usage"),
  getUsageCalls: (limit = 50) => request<UsageCall[]>(`/api/usage/calls?limit=${limit}`),
};

export function jobStreamUrl(jobId: string): string {
  return `${API_URL}/api/jobs/${jobId}/events`;
}

export function exportUrl(projectId: string): string {
  return `${API_URL}/api/projects/${projectId}/export`;
}

export function mediaUrl(path: string | null | undefined): string | undefined {
  if (!path) return undefined;
  if (/^(https?:|data:|blob:)/i.test(path)) return path;
  return `${API_URL}${path.startsWith("/") ? "" : "/"}${path}`;
}
