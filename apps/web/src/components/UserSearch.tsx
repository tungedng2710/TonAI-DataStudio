import { Database, Search, UserRound, X } from "lucide-react";
import { type FormEvent, useEffect, useId, useRef, useState } from "react";
import { Link, useNavigate } from "react-router-dom";

import { api } from "../api";
import type { Dataset, PublicUser } from "../types";
import { UserAvatar } from "./UserAvatar";

export function UserSearch({ className = "" }: { className?: string }) {
  const navigate = useNavigate();
  const resultsId = useId();
  const rootRef = useRef<HTMLDivElement>(null);
  const [query, setQuery] = useState("");
  const [userResults, setUserResults] = useState<PublicUser[]>([]);
  const [datasetResults, setDatasetResults] = useState<Dataset[]>([]);
  const [loading, setLoading] = useState(false);
  const [focused, setFocused] = useState(false);

  useEffect(() => {
    const normalized = query.trim();
    if (!normalized) {
      setUserResults([]);
      setDatasetResults([]);
      setLoading(false);
      return;
    }
    let current = true;
    setLoading(true);
    const timer = window.setTimeout(() => {
      void Promise.all([api.searchUsers(normalized), api.searchDatasets(normalized)])
        .then(([users, datasets]) => {
          if (current) {
            setUserResults(users);
            setDatasetResults(datasets);
          }
        })
        .catch(() => {
          if (current) {
            setUserResults([]);
            setDatasetResults([]);
          }
        })
        .finally(() => {
          if (current) setLoading(false);
        });
    }, 250);
    return () => {
      current = false;
      window.clearTimeout(timer);
    };
  }, [query]);

  useEffect(() => {
    if (!focused) return;
    const close = (event: PointerEvent) => {
      if (!rootRef.current?.contains(event.target as Node)) setFocused(false);
    };
    document.addEventListener("pointerdown", close);
    return () => document.removeEventListener("pointerdown", close);
  }, [focused]);

  const submit = (event: FormEvent) => {
    event.preventDefault();
    const normalized = query.trim().toLowerCase();
    const exactUser = userResults.find(
      (candidate) => candidate.username.toLowerCase() === query.trim().toLowerCase(),
    );
    const exactDataset = datasetResults.find(
      (candidate) =>
        `${candidate.namespace}/${candidate.slug}`.toLowerCase() === normalized
        || candidate.slug.toLowerCase() === normalized,
    );
    if (exactUser) {
      setFocused(false);
      void navigate(`/users/${encodeURIComponent(exactUser.username)}`);
    } else if (exactDataset ?? datasetResults[0]) {
      const destination = exactDataset ?? datasetResults[0]!;
      setFocused(false);
      void navigate(
        `/datasets/${encodeURIComponent(destination.namespace)}/${encodeURIComponent(destination.slug)}`,
      );
    } else if (userResults[0]) {
      setFocused(false);
      void navigate(`/users/${encodeURIComponent(userResults[0].username)}`);
    }
  };

  const open = focused && query.trim().length > 0;

  return (
    <div className={`relative ${className}`} ref={rootRef}>
      <form onSubmit={submit} role="search">
        <Search className="pointer-events-none absolute top-1/2 left-3 size-4 -translate-y-1/2 text-slate-400" />
        <input
          aria-label="Search users and datasets"
          aria-expanded={open}
          aria-controls={resultsId}
          autoComplete="off"
          className="block h-9 w-full rounded-lg border border-slate-200 bg-slate-50 pr-9 pl-9 text-sm text-slate-900 shadow-xs outline-none transition placeholder:text-slate-400 focus:border-indigo-300 focus:bg-white focus:ring-3 focus:ring-indigo-500/10"
          placeholder="Search users or datasets"
          role="combobox"
          type="search"
          value={query}
          onChange={(event) => {
            setQuery(event.target.value);
            setFocused(true);
          }}
          onFocus={() => setFocused(true)}
          onKeyDown={(event) => {
            if (event.key === "Escape") setFocused(false);
          }}
        />
        {query ? (
          <button
            aria-label="Clear search"
            className="absolute top-1/2 right-2 grid size-6 -translate-y-1/2 place-items-center rounded-md text-slate-400 hover:bg-slate-100 hover:text-slate-700"
            type="button"
            onClick={() => {
              setQuery("");
              setUserResults([]);
              setDatasetResults([]);
            }}
          >
            <X className="size-3.5" />
          </button>
        ) : null}
      </form>

      {open ? (
        <div
          className="absolute top-full right-0 left-0 z-50 mt-2 overflow-hidden rounded-xl border border-slate-200 bg-white p-1.5 shadow-xl shadow-slate-950/10"
          id={resultsId}
        >
          {loading ? (
            <p className="px-3 py-3 text-sm text-slate-500">Searching people and datasets…</p>
          ) : userResults.length || datasetResults.length ? (
            <div className="max-h-[min(32rem,70vh)] overflow-y-auto">
              {userResults.length ? (
                <div>
                  <p className="px-3 pt-2 pb-1 text-[10px] font-bold tracking-[0.14em] text-slate-400 uppercase">
                    People
                  </p>
                  <ul aria-label="User search results" role="listbox">
                    {userResults.map((candidate) => (
                      <li key={candidate.username} role="option" aria-selected="false">
                        <Link
                          className="flex items-center gap-3 rounded-lg px-3 py-2.5 transition hover:bg-indigo-50"
                          to={`/users/${encodeURIComponent(candidate.username)}`}
                          onClick={() => {
                            setFocused(false);
                            setQuery("");
                          }}
                        >
                          <UserAvatar className="size-9" user={candidate} />
                          <span className="min-w-0">
                            <span className="block truncate text-sm font-semibold text-slate-900">
                              {candidate.display_name || candidate.username}
                            </span>
                            <span className="block truncate text-xs text-slate-500">
                              @{candidate.username}
                            </span>
                          </span>
                        </Link>
                      </li>
                    ))}
                  </ul>
                </div>
              ) : null}

              {datasetResults.length ? (
                <div className={userResults.length ? "mt-1 border-t border-slate-100 pt-1" : ""}>
                  <p className="px-3 pt-2 pb-1 text-[10px] font-bold tracking-[0.14em] text-slate-400 uppercase">
                    Datasets
                  </p>
                  <ul aria-label="Dataset search results" role="listbox">
                    {datasetResults.map((dataset) => (
                      <li key={dataset.id} role="option" aria-selected="false">
                        <Link
                          className="flex items-center gap-3 rounded-lg px-3 py-2.5 transition hover:bg-indigo-50"
                          to={`/datasets/${encodeURIComponent(dataset.namespace)}/${encodeURIComponent(dataset.slug)}`}
                          onClick={() => {
                            setFocused(false);
                            setQuery("");
                          }}
                        >
                          <span className="grid size-9 shrink-0 place-items-center rounded-lg bg-indigo-50 text-indigo-600 ring-1 ring-indigo-100">
                            <Database className="size-4" />
                          </span>
                          <span className="min-w-0">
                            <span className="block truncate text-sm font-semibold text-slate-900">
                              {dataset.namespace}/{dataset.slug}
                            </span>
                            <span className="block truncate text-xs text-slate-500">
                              {dataset.description || "No description yet."}
                            </span>
                          </span>
                          <span className="status-pill ml-auto shrink-0">{dataset.visibility}</span>
                        </Link>
                      </li>
                    ))}
                  </ul>
                </div>
              ) : null}
            </div>
          ) : (
            <div className="flex items-center gap-2 px-3 py-3 text-sm text-slate-500">
              <UserRound className="size-4" /> No users or datasets found
            </div>
          )}
        </div>
      ) : null}
    </div>
  );
}
