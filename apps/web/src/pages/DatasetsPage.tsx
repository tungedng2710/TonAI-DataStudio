import {
  ArrowRight,
  Database,
  HardDrive,
  Plus,
  ShieldCheck,
  X,
} from "lucide-react";
import { type FormEvent, useEffect, useState } from "react";
import { Link, useNavigate } from "react-router-dom";

import { api } from "../api";
import { AccountControls } from "../components/Auth";
import { ApiGuideLink } from "../components/ApiGuideLink";
import { useAuth } from "../components/auth-context";
import { Brand } from "../components/Brand";
import { DatasetTags } from "../components/DatasetTags";
import { normalizeDatasetSlug } from "../dataset-slug";
import { EmptyState, ErrorState, LoadingState } from "../components/Feedback";
import { StudioSelect } from "../components/StudioSelect";
import { UserSearch } from "../components/UserSearch";
import type { Dataset, Visibility } from "../types";

const visibilityOptions = [
  {
    value: "private",
    label: "Private",
    description: "Only you and workspace administrators can access it.",
  },
  {
    value: "internal",
    label: "Internal",
    description: "Every signed-in Studio user can access it.",
  },
  {
    value: "public",
    label: "Public",
    description: "Anyone with the link can access it.",
  },
];

function CreateDatasetDialog({ close }: { close: () => void }) {
  const navigate = useNavigate();
  const { user } = useAuth();
  const [namespace, setNamespace] = useState(user?.username ?? "research");
  const [slug, setSlug] = useState("");
  const [description, setDescription] = useState("");
  const [visibility, setVisibility] = useState<Visibility>("private");
  const [error, setError] = useState("");
  const [saving, setSaving] = useState(false);

  const submit = async (event: FormEvent) => {
    event.preventDefault();
    const normalizedSlug = normalizeDatasetSlug(slug);
    if (!normalizedSlug) {
      setError("Enter a dataset name.");
      return;
    }
    setSaving(true);
    setError("");
    try {
      const dataset = await api.createDataset({
        namespace,
        slug: normalizedSlug,
        visibility,
        description,
      });
      await navigate(`/datasets/${dataset.namespace}/${dataset.slug}`);
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "Could not create the dataset.");
      setSaving(false);
    }
  };

  return (
    <div className="fixed inset-0 z-50 grid place-items-center bg-slate-950/65 p-4 backdrop-blur-sm">
      <form
        className="modal-panel max-h-[calc(100vh-2rem)] max-w-lg overflow-y-auto"
        onSubmit={(event) => void submit(event)}
      >
        <div className="flex items-start justify-between">
          <div>
            <p className="eyebrow">Repository</p>
            <h2 className="mt-1 text-2xl font-semibold tracking-tight">Create a dataset</h2>
          </div>
          <button className="icon-button" type="button" onClick={close} aria-label="Close">
            <X className="size-4" />
          </button>
        </div>
        <div className="mt-6 grid grid-cols-2 gap-4">
          <label className="field-label">
            Namespace
            <input
              className="field-input"
              required
              pattern="[a-z0-9][a-z0-9_-]*"
              value={namespace}
              onChange={(event) => setNamespace(event.target.value)}
            />
          </label>
          <label className="field-label">
            Dataset name
            <input
              className="field-input"
              required
              autoFocus
              placeholder="support-tickets"
              value={slug}
              onChange={(event) => setSlug(event.target.value)}
              onBlur={() => setSlug(normalizeDatasetSlug(slug))}
            />
            {slug ? (
              <span className="mt-1 text-xs font-normal text-slate-500">
                Saved as {normalizeDatasetSlug(slug)}
              </span>
            ) : null}
          </label>
        </div>
        <label className="field-label mt-4">
          Description
          <textarea
            className="field-input min-h-24 resize-none"
            placeholder="What is this dataset used for?"
            value={description}
            onChange={(event) => setDescription(event.target.value)}
          />
        </label>
        <div className="field-label mt-4">
          <span>Visibility</span>
          <StudioSelect
            ariaLabel="Dataset visibility"
            className="mt-1"
            value={visibility}
            options={visibilityOptions}
            onChange={(next) => setVisibility(next as Visibility)}
          />
        </div>
        {error ? <p className="mt-4 text-sm font-medium text-rose-700">{error}</p> : null}
        <div className="mt-6 flex justify-end gap-3">
          <button className="button-secondary" type="button" onClick={close}>Cancel</button>
          <button className="button-primary" type="submit" disabled={saving}>
            {saving ? "Creating…" : "Create dataset"}
          </button>
        </div>
      </form>
    </div>
  );
}

export function DatasetsPage() {
  const { user, openAuth } = useAuth();
  const [datasets, setDatasets] = useState<Dataset[] | null>(null);
  const [error, setError] = useState("");
  const [creating, setCreating] = useState(false);

  const load = () => {
    setError("");
    void api.listDatasets().then(setDatasets).catch((caught: unknown) => {
      setError(caught instanceof Error ? caught.message : "Could not load datasets.");
    });
  };
  useEffect(load, [user?.id]);

  return (
    <div className="min-h-screen">
      <header className="app-header">
        <div className="app-header-bar page-shell">
          <Brand />
          <UserSearch className="mx-4 hidden min-w-0 max-w-md flex-1 md:block" />
          <div className="flex items-center gap-2">
            <ApiGuideLink />
            <button className="button-primary" type="button" onClick={() => user ? setCreating(true) : openAuth("register")}>
              <Plus className="size-4" /> <span className="hidden sm:inline">New dataset</span><span className="sm:hidden">New</span>
            </button>
            <AccountControls />
          </div>
        </div>
      </header>
      <main className="page-shell py-5 lg:py-6">
        <UserSearch className="mb-4 md:hidden" />
        <section className="hero-panel px-6 py-5 sm:px-7 lg:py-6">
          <div className="pointer-events-none absolute -top-36 -right-28 size-96 rounded-full bg-indigo-200/40 blur-3xl" />
          <div className="pointer-events-none absolute -bottom-40 left-1/3 size-80 rounded-full bg-cyan-200/30 blur-3xl" />
          <div className="relative grid gap-5 lg:grid-cols-[1.45fr_0.55fr] lg:items-center">
            <div>
              <p className="flex items-center gap-2 text-[10px] font-bold tracking-[0.18em] text-indigo-600 uppercase">
                Dataset workspace
              </p>
              <h1 className="mt-2 max-w-3xl text-3xl font-semibold tracking-[-0.045em] text-slate-950">
                Datasets, clearly versioned.
              </h1>
              <p className="mt-2 max-w-2xl text-sm leading-6 text-slate-600">
                Upload, inspect, and share data from one focused workspace.
              </p>
            </div>
            <div className="grid grid-cols-2 gap-3">
              <div className="metric-card">
                <Database className="size-5 text-indigo-500" />
                <p className="mt-3 text-2xl font-semibold text-slate-950">{datasets?.length ?? "—"}</p>
                <p className="mt-0.5 text-xs font-medium text-slate-500">Repositories</p>
              </div>
              <div className="metric-card">
                <ShieldCheck className="size-5 text-cyan-600" />
                <p className="mt-3 text-sm font-semibold text-slate-900">Source preserved</p>
                <p className="mt-0.5 text-xs leading-5 text-slate-500">Immutable revisions</p>
              </div>
            </div>
          </div>
        </section>

        <section className="mt-5">
          <h2 className="text-xl font-semibold tracking-tight text-slate-950">Repositories</h2>
          <div className="mt-4">
            {error ? <ErrorState message={error} retry={load} /> : null}
            {!error && datasets === null ? <LoadingState label="Loading repositories…" /> : null}
            {!error && datasets !== null && !datasets.length ? (
              <EmptyState
                title="Create your first dataset"
                description={user ? "Create a repository, then upload a dataset folder." : "Sign in to create a dataset, or browse public repositories here."}
                action={<button className="button-primary" type="button" onClick={() => user ? setCreating(true) : openAuth("register")}><Plus className="size-4" /> {user ? "New dataset" : "Create account"}</button>}
              />
            ) : null}
            {datasets?.length ? (
              <div className="grid gap-3 md:grid-cols-2 xl:grid-cols-3 2xl:grid-cols-4">
                {datasets.map((dataset) => (
                  <Link
                    className="group relative flex h-full flex-col overflow-hidden rounded-2xl border border-slate-200/80 bg-white p-4 shadow-xs shadow-slate-900/5 transition hover:-translate-y-0.5 hover:border-indigo-200 hover:shadow-md hover:shadow-indigo-950/5"
                    to={`/datasets/${dataset.namespace}/${dataset.slug}`}
                    key={dataset.id}
                  >
                    <div className="flex items-start justify-between gap-4">
                      <span className="grid size-10 place-items-center rounded-xl bg-gradient-to-br from-indigo-50 to-cyan-50 text-indigo-600 ring-1 ring-indigo-100">
                        <Database className="size-5" />
                      </span>
                      <span className="status-pill">{dataset.visibility}</span>
                    </div>
                    <p className="mt-4 flex items-center gap-1.5 text-xs font-medium text-slate-400">
                      <HardDrive className="size-3" /> {dataset.owner ?? dataset.namespace}
                    </p>
                    <h3 className="mt-1 text-lg font-semibold tracking-tight text-slate-950">{dataset.slug}</h3>
                    <p className="mt-2 line-clamp-2 min-h-10 text-sm leading-5 text-slate-500">
                      {dataset.description || "No description yet."}
                    </p>
                    <DatasetTags
                      className="mt-3"
                      dataStage={dataset.data_stage}
                      tags={dataset.tags}
                    />
                    <div className="mt-auto flex items-center justify-between border-t border-slate-100 pt-3 text-xs text-slate-500">
                      <span>{dataset.latest_revision ? `rev ${dataset.latest_revision.revision_id}` : "No revisions"}</span>
                      <span className="grid size-7 place-items-center rounded-lg bg-slate-50 text-slate-500 transition group-hover:bg-indigo-50 group-hover:text-indigo-600">
                        <ArrowRight className="size-4 transition group-hover:translate-x-0.5" />
                      </span>
                    </div>
                  </Link>
                ))}
              </div>
            ) : null}
          </div>
        </section>
      </main>
      {creating && user ? <CreateDatasetDialog close={() => setCreating(false)} /> : null}
    </div>
  );
}
