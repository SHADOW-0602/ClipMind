"use client";

import { useEffect, useState } from "react";
import {
  Ban,
  Check,
  Fingerprint,
  Pencil,
  Plus,
  Sparkles,
  Target,
  Trash2,
  Users,
} from "lucide-react";
import { api, ApiError } from "@/lib/api";
import type { BrandProfile, BrandProfileInput } from "@/lib/types";
import { initials } from "@/lib/utils";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Field, Input, Textarea } from "@/components/ui/input";
import { Modal } from "@/components/ui/modal";
import { Skeleton } from "@/components/ui/skeleton";
import { EmptyState } from "@/components/ui/empty-state";
import { useDocumentTitle, useToast } from "@/components/ui/toast";
import { PageHeader } from "@/components/page-header";

const EMPTY_FORM: BrandProfileInput = {
  name: "",
  tone_description: "",
  target_audience: "",
  voice_dos: [],
  voice_donts: [],
  banned_words: [],
  example_posts: [],
};

const CARD_ACCENTS = ["#d8ff63", "#8ce7e1", "#f2a3c7", "#8fc6ff", "#f4bd5a"];

export default function BrandsPage() {
  const { toast } = useToast();
  const [brands, setBrands] = useState<BrandProfile[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [formOpen, setFormOpen] = useState(false);
  const [editing, setEditing] = useState<BrandProfile | null>(null);
  const [deleting, setDeleting] = useState<BrandProfile | null>(null);
  const [deleteLoading, setDeleteLoading] = useState(false);
  useDocumentTitle("Brand profiles");

  const load = async () => {
    setLoading(true);
    try {
      setBrands(await api.listBrands());
      setError(null);
    } catch (reason) {
      setError(reason instanceof ApiError ? reason.detail : "Could not load brand profiles.");
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    void load();
  }, []);

  const openCreate = () => {
    setEditing(null);
    setFormOpen(true);
  };

  const openEdit = (brand: BrandProfile) => {
    setEditing(brand);
    setFormOpen(true);
  };

  const remove = async () => {
    if (!deleting) return;
    setDeleteLoading(true);
    try {
      await api.deleteBrand(deleting.id);
      setBrands((current) => current.filter((brand) => brand.id !== deleting.id));
      toast({ title: "Brand profile deleted", description: "Projects keep their clips; the profile is detached.", tone: "success" });
      setDeleting(null);
    } catch (reason) {
      toast({
        title: "Could not delete brand profile",
        description: reason instanceof ApiError ? reason.detail : "Try again in a moment.",
        tone: "error",
      });
    } finally {
      setDeleteLoading(false);
    }
  };

  return (
    <div className="animate-in">
      <PageHeader
        eyebrow={
          <>
            <span>Brand</span>
            <span className="size-1 rounded-full bg-faint" />
            <span>Voice profiles</span>
          </>
        }
        title="A consistent voice, without the rewrites."
        description="Brand profiles carry your tone, audience, banned words, and examples into every hook, caption, and call to action. The pipeline enforces banned words before copy ever reaches the screen."
        actions={
          <Button variant="primary" onClick={openCreate}>
            <Plus className="size-3.5" />
            New profile
          </Button>
        }
      />

      {error ? (
        <div className="mb-5 rounded-xl border border-warning/25 bg-warning/[0.055] px-4 py-3 text-[12px] text-warning">
          {error}
        </div>
      ) : null}

      {loading ? (
        <div className="grid gap-3 md:grid-cols-2 xl:grid-cols-3">
          {Array.from({ length: 3 }).map((_, index) => (
            <div key={index} className="panel space-y-4 p-5">
              <Skeleton className="h-10 w-10 rounded-xl" />
              <Skeleton className="h-4 w-40" />
              <Skeleton className="h-3 w-full" />
              <Skeleton className="h-3 w-3/4" />
              <div className="flex gap-2">
                <Skeleton className="h-5 w-16 rounded-full" />
                <Skeleton className="h-5 w-16 rounded-full" />
              </div>
            </div>
          ))}
        </div>
      ) : brands.length === 0 ? (
        <div className="grid gap-4 lg:grid-cols-[1.4fr_1fr]">
          <EmptyState
            icon={<Fingerprint className="size-5" />}
            title="Give the machine your voice"
            description="A brand profile tells ClipMind how you sound, who you are talking to, and what you never want to say. It is applied at generation time and checked again on every manual edit."
            action={
              <Button variant="primary" onClick={openCreate}>
                <Plus className="size-3.5" />
                Create a brand profile
              </Button>
            }
            className="min-h-[320px] bg-void/30"
          />
          <div className="panel p-5">
            <p className="font-mono text-[9.5px] uppercase tracking-[0.18em] text-faint">
              What gets enforced
            </p>
            <ul className="mt-4 space-y-3">
              {[
                [<Ban key="ban" className="size-3.5" />, "Banned words", "Rejected at generation and on manual save."],
                [<Sparkles key="tone" className="size-3.5" />, "Tone", "Injected into every platform prompt."],
                [<Users key="aud" className="size-3.5" />, "Audience", "Shapes specificity and assumed context."],
                [<Target key="examples" className="size-3.5" />, "Examples", "Anchors rhythm and vocabulary."],
              ].map(([icon, title, body]) => (
                <li key={String(title)} className="flex gap-3">
                  <span className="mt-0.5 text-lime/75">{icon}</span>
                  <div>
                    <p className="text-[11.5px] font-medium text-mist">{title}</p>
                    <p className="mt-0.5 text-[10.5px] leading-relaxed text-faint">{body}</p>
                  </div>
                </li>
              ))}
            </ul>
          </div>
        </div>
      ) : (
        <div className="grid gap-3 md:grid-cols-2 xl:grid-cols-3">
          {brands.map((brand, index) => {
            const accent = CARD_ACCENTS[index % CARD_ACCENTS.length];
            return (
              <div key={brand.id} className="panel panel-hover group relative flex flex-col p-5">
                <div className="flex items-start justify-between gap-3">
                  <div className="flex items-center gap-3">
                    <span
                      className="flex size-10 items-center justify-center rounded-xl border text-[12px] font-semibold"
                      style={{
                        borderColor: `${accent}33`,
                        backgroundColor: `${accent}12`,
                        color: accent,
                      }}
                    >
                      {initials(brand.name)}
                    </span>
                    <div className="min-w-0">
                      <h2 className="truncate text-[13.5px] font-semibold tracking-[-0.015em] text-mist">
                        {brand.name}
                      </h2>
                      <p className="mt-0.5 text-[10.5px] text-faint">
                        {brand.target_audience || "Audience not set"}
                      </p>
                    </div>
                  </div>
                  <div className="flex items-center gap-1 opacity-0 transition-opacity group-hover:opacity-100">
                    <button
                      type="button"
                      onClick={() => openEdit(brand)}
                      aria-label={`Edit ${brand.name}`}
                      className="rounded-lg p-1.5 text-faint hover:bg-white/5 hover:text-mist"
                    >
                      <Pencil className="size-3.5" />
                    </button>
                    <button
                      type="button"
                      onClick={() => setDeleting(brand)}
                      aria-label={`Delete ${brand.name}`}
                      className="rounded-lg p-1.5 text-faint hover:bg-danger/10 hover:text-danger"
                    >
                      <Trash2 className="size-3.5" />
                    </button>
                  </div>
                </div>

                <p className="mt-4 line-clamp-3 min-h-[48px] text-[11.5px] leading-relaxed text-muted">
                  {brand.tone_description || "No tone description yet. Add one to anchor the writing."}
                </p>

                <div className="mt-4 flex flex-wrap gap-1.5">
                  {brand.banned_words.slice(0, 4).map((word) => (
                    <Badge key={word} tone="danger" className="px-2 py-0 text-[9.5px]">
                      <Ban className="size-2.5" />
                      {word}
                    </Badge>
                  ))}
                  {brand.banned_words.length > 4 ? (
                    <Badge tone="outline" className="px-2 py-0 text-[9.5px]">
                      +{brand.banned_words.length - 4}
                    </Badge>
                  ) : null}
                  {brand.banned_words.length === 0 ? (
                    <Badge tone="outline" className="px-2 py-0 text-[9.5px]">
                      No banned words
                    </Badge>
                  ) : null}
                </div>

                <div className="mt-4 grid grid-cols-2 gap-2 border-t border-line-soft pt-3">
                  <div className="flex items-center gap-1.5 text-[10px] text-faint">
                    <Check className="size-3 text-lime/70" />
                    {brand.voice_dos.length} do{brand.voice_dos.length === 1 ? "" : "s"}
                  </div>
                  <div className="flex items-center gap-1.5 text-[10px] text-faint">
                    <Ban className="size-3 text-danger/60" />
                    {brand.voice_donts.length} don&apos;t{brand.voice_donts.length === 1 ? "" : "s"}
                  </div>
                </div>
              </div>
            );
          })}

          <button
            type="button"
            onClick={openCreate}
            className="group flex min-h-[240px] flex-col items-center justify-center rounded-[1.15rem] border border-dashed border-line text-center transition-colors hover:border-[#414a3a] hover:bg-white/[0.018]"
          >
            <span className="flex size-10 items-center justify-center rounded-xl border border-line bg-raised text-faint transition-colors group-hover:border-lime/30 group-hover:text-lime">
              <Plus className="size-4" />
            </span>
            <p className="mt-3 text-[12.5px] font-medium text-muted group-hover:text-mist">New profile</p>
            <p className="mt-1 text-[10.5px] text-faint">One voice per audience</p>
          </button>
        </div>
      )}

      <BrandFormModal
        open={formOpen}
        onClose={() => setFormOpen(false)}
        brand={editing}
        onSaved={(saved) => {
          setBrands((current) => {
            const exists = current.some((brand) => brand.id === saved.id);
            return exists ? current.map((brand) => (brand.id === saved.id ? saved : brand)) : [...current, saved];
          });
          setFormOpen(false);
          toast({ title: editing ? "Brand profile updated" : "Brand profile created", tone: "success" });
        }}
      />

      <Modal
        open={Boolean(deleting)}
        onClose={() => setDeleting(null)}
        title="Delete brand profile?"
        description="Projects keep their generated content, but will no longer have this voice attached."
        size="sm"
        footer={
          <>
            <Button variant="ghost" onClick={() => setDeleting(null)} disabled={deleteLoading}>
              Cancel
            </Button>
            <Button variant="danger" onClick={remove} loading={deleteLoading}>
              <Trash2 className="size-3.5" />
              Delete profile
            </Button>
          </>
        }
      >
        <div className="rounded-xl border border-line bg-void/50 p-4">
          <p className="text-[12.5px] font-medium text-mist">{deleting?.name}</p>
          <p className="mt-1 text-[11px] text-faint">
            {deleting?.banned_words.length ?? 0} banned words · {deleting?.voice_dos.length ?? 0} voice rules
          </p>
        </div>
      </Modal>
    </div>
  );
}

function BrandFormModal({
  open,
  onClose,
  brand,
  onSaved,
}: {
  open: boolean;
  onClose: () => void;
  brand: BrandProfile | null;
  onSaved: (brand: BrandProfile) => void;
}) {
  const { toast } = useToast();
  const [form, setForm] = useState<BrandProfileInput>(EMPTY_FORM);
  const [saving, setSaving] = useState(false);
  const [errors, setErrors] = useState<string | null>(null);
  const [dosText, setDosText] = useState("");
  const [dontsText, setDontsText] = useState("");
  const [bannedText, setBannedText] = useState("");
  const [examplesText, setExamplesText] = useState("");

  useEffect(() => {
    if (!open) return;
    if (brand) {
      setForm({
        name: brand.name,
        tone_description: brand.tone_description,
        target_audience: brand.target_audience,
        voice_dos: brand.voice_dos,
        voice_donts: brand.voice_donts,
        banned_words: brand.banned_words,
        example_posts: brand.example_posts,
      });
      setDosText(brand.voice_dos.join("\n"));
      setDontsText(brand.voice_donts.join("\n"));
      setBannedText(brand.banned_words.join(", "));
      setExamplesText(brand.example_posts.join("\n\n"));
    } else {
      setForm(EMPTY_FORM);
      setDosText("");
      setDontsText("");
      setBannedText("");
      setExamplesText("");
    }
    setErrors(null);
  }, [open, brand]);

  const save = async () => {
    if (!form.name.trim()) {
      setErrors("Give the profile a name.");
      return;
    }
    setSaving(true);
    setErrors(null);
    const payload: BrandProfileInput = {
      ...form,
      name: form.name.trim(),
      tone_description: form.tone_description?.trim() ?? "",
      target_audience: form.target_audience?.trim() ?? "",
      voice_dos: dosText.split("\n").map((item) => item.trim()).filter(Boolean),
      voice_donts: dontsText.split("\n").map((item) => item.trim()).filter(Boolean),
      banned_words: bannedText.split(",").map((item) => item.trim()).filter(Boolean),
      example_posts: examplesText.split(/\n{2,}/).map((item) => item.trim()).filter(Boolean),
    };
    try {
      const saved = brand ? await api.updateBrand(brand.id, payload) : await api.createBrand(payload);
      onSaved(saved);
    } catch (reason) {
      const message = reason instanceof ApiError ? reason.detail : "Could not save the profile.";
      setErrors(message);
      toast({ title: "Could not save brand profile", description: message, tone: "error" });
    } finally {
      setSaving(false);
    }
  };

  return (
    <Modal
      open={open}
      onClose={onClose}
      title={brand ? "Edit brand profile" : "New brand profile"}
      description="These rules are injected into every copy prompt and enforced on manual edits."
      size="lg"
      footer={
        <>
          <Button variant="ghost" onClick={onClose} disabled={saving}>
            Cancel
          </Button>
          <Button variant="primary" onClick={save} loading={saving}>
            <Check className="size-3.5" />
            {brand ? "Save profile" : "Create profile"}
          </Button>
        </>
      }
    >
      <div className="space-y-4">
        <div className="grid gap-4 sm:grid-cols-2">
          <Field label="Profile name">
            <Input
              value={form.name}
              onChange={(event) => setForm((current) => ({ ...current, name: event.target.value }))}
              placeholder="e.g. Systems Studio"
              maxLength={120}
              autoFocus
            />
          </Field>
          <Field label="Target audience">
            <Input
              value={form.target_audience}
              onChange={(event) => setForm((current) => ({ ...current, target_audience: event.target.value }))}
              placeholder="e.g. Independent creators and operators"
            />
          </Field>
        </div>

        <Field label="Tone description" hint="A few concrete adjectives beat a paragraph of abstractions.">
          <Textarea
            value={form.tone_description}
            onChange={(event) => setForm((current) => ({ ...current, tone_description: event.target.value }))}
            placeholder="Direct, warm, practical. Short sentences. No hype. Name the constraint before the solution."
            rows={3}
            className="min-h-[84px] text-[12.5px]"
          />
        </Field>

        <div className="grid gap-4 sm:grid-cols-2">
          <Field label="Voice do's" hint="One per line.">
            <Textarea
              value={dosText}
              onChange={(event) => setDosText(event.target.value)}
              placeholder={"Be specific\nUse concrete numbers\nName the tradeoff"}
              rows={5}
              className="min-h-[120px] text-[12.5px]"
            />
          </Field>
          <Field label="Voice don'ts" hint="One per line.">
            <Textarea
              value={dontsText}
              onChange={(event) => setDontsText(event.target.value)}
              placeholder={"No hype\nNo fake urgency\nNo vague promises"}
              rows={5}
              className="min-h-[120px] text-[12.5px]"
            />
          </Field>
        </div>

        <Field label="Banned words" hint="Comma-separated. Matched as whole words, case-insensitive, and rejected on save.">
          <Input
            value={bannedText}
            onChange={(event) => setBannedText(event.target.value)}
            placeholder="revolutionary, guaranteed, hack, guru"
          />
        </Field>

        <Field label="Example posts" optional hint="Separate examples with a blank line. These anchor rhythm and vocabulary.">
          <Textarea
            value={examplesText}
            onChange={(event) => setExamplesText(event.target.value)}
            placeholder={"Most creators do not have a content problem. They have a system problem.\n\nStart with capture. Polish comes later."}
            rows={4}
            className="min-h-[100px] text-[12.5px]"
          />
        </Field>

        {errors ? (
          <div className="rounded-lg border border-danger/25 bg-danger/[0.055] px-3 py-2 text-[11.5px] text-danger">
            {errors}
          </div>
        ) : null}
      </div>
    </Modal>
  );
}
