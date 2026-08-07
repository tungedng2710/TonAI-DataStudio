import {
  ArrowLeft,
  BookOpenText,
  Braces,
  Check,
  Copy,
  Download,
  KeyRound,
  ListTree,
  UploadCloud,
} from "lucide-react";
import { useState } from "react";
import { Link } from "react-router-dom";

import { AccountControls } from "../components/Auth";
import { Brand } from "../components/Brand";
import { UserSearch } from "../components/UserSearch";

function CodeBlock({ children, label }: { children: string; label?: string }) {
  const [copied, setCopied] = useState(false);
  const code = children.trim();

  const copy = async () => {
    try {
      await navigator.clipboard.writeText(code);
      setCopied(true);
      window.setTimeout(() => setCopied(false), 2_000);
    } catch {
      setCopied(false);
    }
  };

  return (
    <div className="mt-3 overflow-hidden rounded-xl border border-slate-800 bg-slate-950 shadow-inner">
      {label ? (
        <div className="border-b border-white/8 bg-white/4 px-4 py-2 text-[10px] font-bold tracking-[0.14em] text-slate-400 uppercase">
          {label}
        </div>
      ) : null}
      <div className="relative">
        <pre className="max-w-full overflow-x-auto p-4 pr-24 font-mono text-[12px] leading-5 text-cyan-100">
          <code>{code}</code>
        </pre>
        <button
          className="absolute top-2.5 right-2.5 inline-flex min-h-7 items-center gap-1.5 rounded-md border border-white/10 bg-white/8 px-2 text-[11px] font-semibold text-slate-300 transition hover:bg-white/15 hover:text-white"
          type="button"
          onClick={() => void copy()}
          aria-label="Copy code"
        >
          {copied ? <Check className="size-3.5" /> : <Copy className="size-3.5" />}
          {copied ? "Copied" : "Copy"}
        </button>
      </div>
    </div>
  );
}

function InlineCode({ children }: { children: string }) {
  return <code className="rounded bg-slate-100 px-1.5 py-0.5">{children}</code>;
}

const apiRoot = `${window.location.origin}/api/v1`;

export function ApiDocsPage() {
  return (
    <div className="min-h-screen">
      <header className="app-header">
        <div className="app-header-bar page-shell">
          <Brand />
          <UserSearch className="mx-4 hidden min-w-0 max-w-md flex-1 md:block" />
          <div className="flex items-center gap-2">
            <Link
              className="header-action"
              to="/"
            >
              <ArrowLeft className="size-4" /> <span className="hidden sm:inline">All datasets</span>
            </Link>
            <AccountControls />
          </div>
        </div>
      </header>

      <main className="page-shell py-5 lg:py-6">
        <section className="hero-panel px-6 py-5 sm:px-7 lg:py-6">
          <div className="pointer-events-none absolute -top-32 right-0 size-80 rounded-full bg-indigo-200/45 blur-3xl" />
          <div className="relative max-w-4xl">
            <p className="flex items-center gap-2 text-[10px] font-bold tracking-[0.18em] text-indigo-600 uppercase">
              <BookOpenText className="size-3.5" /> Friendly API recipes
            </p>
            <h1 className="mt-2 text-3xl font-semibold tracking-[-0.04em] text-slate-950">
              Start using the API in minutes
            </h1>
            <p className="mt-2 max-w-3xl text-sm leading-6 text-slate-600">
              Set up a token once, then use short, copy-pasteable commands to create, upload,
              inspect, and download a dataset.
            </p>
            <div className="mt-4 inline-flex rounded-lg border border-indigo-100 bg-white/80 px-3 py-2 font-mono text-xs text-indigo-700 shadow-xs">
              {apiRoot}
            </div>
          </div>
        </section>

        <div className="mt-5 grid items-start gap-4 xl:grid-cols-[210px_minmax(0,1fr)]">
          <nav className="surface-panel hidden p-3 xl:sticky xl:top-16 xl:block" aria-label="API guide sections">
            <p className="px-3 pb-2 text-[10px] font-bold tracking-[0.16em] text-slate-400 uppercase">Quick recipes</p>
            {[
              ["setup", "One-time setup"],
              ["create", "Create a dataset"],
              ["upload", "Upload files"],
              ["browse", "Browse data"],
              ["download", "Download"],
              ["tips", "Useful tips"],
            ].map(([id, label]) => (
              <a className="block rounded-xl px-3 py-2 text-sm font-medium text-slate-600 hover:bg-indigo-50 hover:text-indigo-700" href={`#${id}`} key={id}>{label}</a>
            ))}
          </nav>

          <article className="space-y-4">
            <section className="surface-panel p-5 lg:p-6" id="setup">
              <div className="flex items-center gap-3">
                <KeyRound className="size-5 text-indigo-600" />
                <h2 className="text-xl font-semibold">1. One-time setup</h2>
              </div>
              <ol className="mt-4 list-decimal space-y-2 pl-5 text-sm leading-6 text-slate-600">
                <li>Sign in, open <Link className="font-semibold text-indigo-600 hover:text-indigo-500" to="/settings">Account settings</Link>, and generate a personal API token.</li>
                <li>Copy the token when it appears—it is shown only once.</li>
                <li>Paste it below and choose the dataset path you want to use.</li>
              </ol>
              <CodeBlock>{String.raw`export API=${apiRoot}
export TOKEN='ds_pat_paste_your_token_here'
export DATASET=owner/sentiment-demo

ds() {
  curl \
    --fail-with-body \
    --silent \
    --show-error \
    --header "Authorization: Bearer $TOKEN" \
    "$@"
}

ds_json() {
  ds \
    --header 'Content-Type: application/json' \
    "$@"
}`}</CodeBlock>
              <p className="mt-4 text-sm leading-6 text-slate-500">
                The <InlineCode>ds</InlineCode> helper adds your token automatically.
                <InlineCode>ds_json</InlineCode> also marks a request as JSON. The examples use
                <InlineCode>jq</InlineCode> only to make responses easier to read.
              </p>
            </section>

            <section className="surface-panel p-5 lg:p-6" id="create">
              <div className="flex items-center gap-3">
                <Braces className="size-5 text-indigo-600" />
                <h2 className="text-xl font-semibold">2. Create a dataset</h2>
              </div>
              <p className="mt-3 text-sm leading-6 text-slate-600">
                The namespace is usually your username. Visibility can be
                <InlineCode>private</InlineCode>, <InlineCode>internal</InlineCode>, or
                <InlineCode>public</InlineCode>.
              </p>
              <p className="mt-2 text-sm leading-6 text-slate-600">
                Dataset names are lowercased automatically, and spaces between words become
                <InlineCode>-</InlineCode>. For example, <InlineCode>License plate</InlineCode>
                becomes <InlineCode>license-plate</InlineCode>.
              </p>
              <CodeBlock>{String.raw`ds_json \
  --data '{
    "namespace": "owner",
    "slug": "sentiment-demo",
    "visibility": "private",
    "description": "Sentiment examples"
  }' \
  "$API/datasets" \
  | jq`}</CodeBlock>
            </section>

            <section className="surface-panel p-5 lg:p-6" id="upload">
              <div className="flex items-center gap-3">
                <UploadCloud className="size-5 text-indigo-600" />
                <h2 className="text-xl font-semibold">3. Upload and publish</h2>
              </div>
              <p className="mt-3 text-sm leading-6 text-slate-600">
                An upload has three small steps. This example sends a Dataset Card and one Parquet
                file while preserving their repository paths.
              </p>
              <p className="mt-2 text-sm leading-6 text-slate-600">
                When <InlineCode>commit_message</InlineCode> is omitted, the published revision uses
                its generated revision ID as the message. Include the field in step 1 to provide a
                custom message instead. The optional <InlineCode>data_stage</InlineCode> records the
                lifecycle stage on the first revision.
              </p>
              <CodeBlock label="Step 1 · Open an upload">{String.raw`UPLOAD=$(
  ds_json \
    --data '{"data_stage":"raw"}' \
    "$API/datasets/$DATASET/uploads" \
  | jq --raw-output '.id'
)`}</CodeBlock>
              <CodeBlock label="Step 2 · Send files">{String.raw`ds \
  --form 'files=@README.md' \
  --form 'paths=README.md' \
  --form 'files=@data/train.parquet' \
  --form 'paths=data/train.parquet' \
  "$API/uploads/$UPLOAD/files" \
  | jq`}</CodeBlock>
              <CodeBlock label="Step 3 · Publish">{String.raw`REVISION=$(
  ds_json \
    --data '{"expected_file_count":2}' \
    "$API/uploads/$UPLOAD/complete?include_files=false" \
  | jq --raw-output '.revision_id'
)

echo "Published revision: $REVISION"`}</CodeBlock>
              <CodeBlock label="Create a stage revision">{String.raw`ds_json \
  --data '{
    "data_stage": "raw_validated",
    "commit_message": "Validated the raw collection"
  }' \
  "$API/datasets/$DATASET/stage" \
  | jq`}</CodeBlock>
              <p className="mt-4 text-sm leading-6 text-slate-500">
                Every <InlineCode>files</InlineCode> value needs a matching
                <InlineCode>paths</InlineCode> value. Send large folders in several requests, then
                publish once. Later stage changes require a message and create metadata-only
                immutable revisions without re-uploading the source files.
              </p>
            </section>

            <section className="surface-panel p-5 lg:p-6" id="browse">
              <div className="flex items-center gap-3">
                <ListTree className="size-5 text-indigo-600" />
                <h2 className="text-xl font-semibold">4. Browse datasets and rows</h2>
              </div>
              <p className="mt-3 text-sm leading-6 text-slate-600">
                List what you can access, inspect the detected configs and splits, then fetch ten
                preview rows.
              </p>
              <CodeBlock label="Visible datasets">{String.raw`ds \
  "$API/datasets" \
  | jq '.items[] | {
      name: (.namespace + "/" + .slug),
      visibility
    }'`}</CodeBlock>
              <CodeBlock label="Configs and splits">{String.raw`ds \
  --get \
  --data-urlencode 'revision=main' \
  "$API/datasets/$DATASET/configs" \
  | jq`}</CodeBlock>
              <CodeBlock label="First 10 preview rows">{String.raw`ds \
  --get \
  --data-urlencode 'revision=main' \
  --data-urlencode 'limit=10' \
  "$API/datasets/$DATASET/viewer/default/train" \
  | jq '.rows'`}</CodeBlock>
            </section>

            <section className="surface-panel p-5 lg:p-6" id="download">
              <div className="flex items-center gap-3">
                <Download className="size-5 text-indigo-600" />
                <h2 className="text-xl font-semibold">5. Download a repository</h2>
              </div>
              <p className="mt-3 text-sm leading-6 text-slate-600">
                Use <InlineCode>main</InlineCode> for the latest version, or replace it with an
                immutable revision ID for a reproducible download.
              </p>
              <CodeBlock>{String.raw`ds \
  --location \
  --output sentiment-demo.zip \
  "$API/datasets/$DATASET/archive/main"

unzip -l sentiment-demo.zip`}</CodeBlock>
              <p className="mt-4 text-sm leading-6 text-slate-500">
                The ZIP keeps the original Hugging Face-compatible folder layout. This REST
                workflow replaces <InlineCode>hf download</InlineCode>, which is not supported by
                this Studio.
              </p>
            </section>

            <section className="surface-panel p-5 lg:p-6" id="tips">
              <div className="flex items-center gap-3">
                <BookOpenText className="size-5 text-indigo-600" />
                <h2 className="text-xl font-semibold">Useful tips</h2>
              </div>
              <ul className="mt-4 list-disc space-y-2 pl-5 text-sm leading-6 text-slate-600">
                <li>Public datasets can be read with ordinary <InlineCode>curl</InlineCode>; no token is needed.</li>
                <li>Use a read-only token for scripts that never upload or change data.</li>
                <li>
                  Dataset settings support a lifecycle stage and optional custom tags.
                </li>
                <li>Keep tokens out of shell history, source code, screenshots, and Git.</li>
                <li>API errors include a readable <InlineCode>detail</InlineCode> and stable <InlineCode>code</InlineCode>.</li>
              </ul>
              <div className="mt-5 rounded-xl border border-indigo-100 bg-indigo-50/60 p-4">
                <p className="text-sm font-semibold text-indigo-950">Repository compatibility</p>
                <p className="mt-1.5 text-sm leading-6 text-indigo-900/75">
                  Uploads accept Hugging Face-compatible dataset repository layouts, including
                  Dataset Cards, configs, conventional splits, shards, metadata files, and
                  ImageFolder structures. Source paths and bytes are preserved.
                </p>
              </div>
              <p className="mt-5 text-sm leading-6 text-slate-500">
                For filtering, individual file downloads, updates, deletion, and cookie-based
                login, see <InlineCode>docs/API_USAGE.md</InlineCode> in the repository.
              </p>
            </section>
          </article>
        </div>
      </main>
    </div>
  );
}
