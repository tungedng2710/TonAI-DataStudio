import { AlertTriangle, DatabaseZap, LoaderCircle } from "lucide-react";

export function LoadingState({ label = "Loading dataset…" }: { label?: string }) {
  return (
    <div className="grid min-h-52 place-items-center rounded-2xl border border-dashed border-slate-300/80 bg-white/70 shadow-xs shadow-slate-900/5">
      <div className="flex flex-col items-center gap-3 text-sm font-medium text-slate-500">
        <span className="grid size-12 place-items-center rounded-2xl bg-indigo-50 text-indigo-600">
          <LoaderCircle className="size-6 animate-spin" aria-hidden="true" />
        </span>
        {label}
      </div>
    </div>
  );
}

export function ErrorState({ message, retry }: { message: string; retry?: () => void }) {
  return (
    <div className="rounded-2xl border border-rose-200 bg-rose-50/80 p-5 text-rose-950 shadow-xs">
      <div className="flex items-start gap-3">
        <AlertTriangle className="mt-0.5 size-5 shrink-0" aria-hidden="true" />
        <div>
          <h2 className="font-semibold">Something needs attention</h2>
          <p className="mt-1 text-sm text-rose-800">{message}</p>
          {retry ? (
            <button className="button-secondary mt-4" type="button" onClick={retry}>
              Try again
            </button>
          ) : null}
        </div>
      </div>
    </div>
  );
}

export function EmptyState({
  title,
  description,
  action,
}: {
  title: string;
  description: string;
  action?: React.ReactNode;
}) {
  return (
    <div className="grid min-h-56 place-items-center rounded-2xl border border-dashed border-slate-300 bg-white/75 px-5 text-center shadow-xs shadow-slate-900/5">
      <div className="max-w-md">
        <div className="mx-auto grid size-12 place-items-center rounded-2xl bg-indigo-50 text-indigo-600 ring-1 ring-indigo-100">
          <DatabaseZap className="size-6" aria-hidden="true" />
        </div>
        <h2 className="mt-4 text-lg font-semibold text-slate-950">{title}</h2>
        <p className="mt-2 text-sm leading-6 text-slate-600">{description}</p>
        {action ? <div className="mt-5">{action}</div> : null}
      </div>
    </div>
  );
}
