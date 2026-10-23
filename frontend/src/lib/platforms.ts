import {
  AtSign,
  BriefcaseBusiness,
  Camera,
  Music2,
  Play,
  type LucideIcon,
} from "lucide-react";
import type { Platform } from "./types";

export interface PlatformMeta {
  id: Platform;
  label: string;
  short: string;
  icon: LucideIcon;
  accent: string;
  hint: string;
  captionLimit: number;
}

export const PLATFORMS: PlatformMeta[] = [
  {
    id: "instagram",
    label: "Instagram",
    short: "IG",
    icon: Camera,
    accent: "#f2a3c7",
    hint: "Punchy, visual, save-worthy",
    captionLimit: 2200,
  },
  {
    id: "youtube",
    label: "YouTube Shorts",
    short: "YT",
    icon: Play,
    accent: "#ff8a80",
    hint: "Complete little lesson",
    captionLimit: 5000,
  },
  {
    id: "tiktok",
    label: "TikTok",
    short: "TT",
    icon: Music2,
    accent: "#8ce7e1",
    hint: "Fast, human, native",
    captionLimit: 2200,
  },
  {
    id: "linkedin",
    label: "LinkedIn",
    short: "LI",
    icon: BriefcaseBusiness,
    accent: "#8fc6ff",
    hint: "Professional argument",
    captionLimit: 3000,
  },
  {
    id: "x",
    label: "X",
    short: "X",
    icon: AtSign,
    accent: "#d8d8d8",
    hint: "Compressed insight",
    captionLimit: 280,
  },
];

export const DEFAULT_PLATFORMS: Platform[] = ["instagram", "tiktok", "linkedin"];

export function platformMeta(id: string): PlatformMeta {
  return PLATFORMS.find((platform) => platform.id === id) ?? PLATFORMS[0];
}

export function platformLabel(id: string): string {
  return platformMeta(id).label;
}
