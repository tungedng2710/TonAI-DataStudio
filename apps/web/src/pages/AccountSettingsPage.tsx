import {
  ArrowLeft,
  Camera,
  Check,
  Copy,
  KeyRound,
  LockKeyhole,
  Mail,
  Plus,
  ShieldAlert,
  Trash2,
  UserRound,
} from "lucide-react";
import { type FormEvent, useEffect, useRef, useState } from "react";
import { Link, Navigate, useNavigate } from "react-router-dom";

import { api } from "../api";
import { AccountControls } from "../components/Auth";
import { useAuth } from "../components/auth-context";
import { Brand } from "../components/Brand";
import { UserSearch } from "../components/UserSearch";
import { LoadingState } from "../components/Feedback";
import { UserAvatar } from "../components/UserAvatar";
import type { ApiToken, ApiTokenCreated } from "../types";

function Message({ tone, children }: { tone: "success" | "error"; children: string }) {
  const classes = tone === "success"
    ? "bg-emerald-50 text-emerald-700"
    : "bg-rose-50 text-rose-700";
  return <p className={`mt-4 rounded-xl px-4 py-3 text-sm font-medium ${classes}`}>{children}</p>;
}

function ProfileSettings() {
  const { user, updateUser } = useAuth();
  const avatarInputRef = useRef<HTMLInputElement>(null);
  const [displayName, setDisplayName] = useState(user?.display_name ?? "");
  const [email, setEmail] = useState(user?.email ?? "");
  const [uploadingAvatar, setUploadingAvatar] = useState(false);
  const [avatarError, setAvatarError] = useState("");
  const [saving, setSaving] = useState(false);
  const [message, setMessage] = useState("");
  const [error, setError] = useState("");

  const submit = async (event: FormEvent) => {
    event.preventDefault();
    setSaving(true);
    setMessage("");
    setError("");
    try {
      const updated = await api.updateProfile({
        display_name: displayName,
        email: email.trim() || null,
      });
      updateUser(updated);
      setDisplayName(updated.display_name);
      setEmail(updated.email ?? "");
      setMessage("Profile saved.");
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "Could not save your profile.");
    } finally {
      setSaving(false);
    }
  };

  const changeAvatar = async (file: File | undefined) => {
    if (!file) return;
    setAvatarError("");
    if (file.size > 2 * 1024 * 1024) {
      setAvatarError("Avatar images must be 2 MB or smaller.");
      return;
    }
    setUploadingAvatar(true);
    try {
      updateUser(await api.uploadAvatar(file));
    } catch (caught) {
      setAvatarError(caught instanceof Error ? caught.message : "Could not update your avatar.");
    } finally {
      setUploadingAvatar(false);
      if (avatarInputRef.current) avatarInputRef.current.value = "";
    }
  };

  if (!user) return null;
  return (
    <section className="surface-panel p-5 lg:p-6">
      <div className="flex items-center gap-3">
        <span className="grid size-10 place-items-center rounded-xl bg-indigo-50 text-indigo-600">
          <UserRound className="size-5" />
        </span>
        <div>
          <h2 className="text-lg font-semibold text-slate-950">Profile</h2>
          <p className="mt-0.5 text-sm text-slate-500">Update how your account is identified.</p>
        </div>
      </div>
      <div className="mt-5 flex items-center gap-4 rounded-xl border border-slate-200 bg-slate-50/70 p-4">
        <UserAvatar user={user} className="size-16 text-xl" />
        <div>
          <input
            ref={avatarInputRef}
            className="hidden"
            type="file"
            accept="image/png,image/jpeg,image/webp"
            aria-label="Avatar image"
            onChange={(event) => void changeAvatar(event.target.files?.[0])}
          />
          <button
            className="button-secondary"
            type="button"
            disabled={uploadingAvatar}
            onClick={() => avatarInputRef.current?.click()}
          >
            <Camera className="size-4" />
            {uploadingAvatar ? "Uploading…" : "Change avatar"}
          </button>
          <p className="mt-1.5 text-xs text-slate-500">PNG, JPEG, or WebP. Maximum 2 MB.</p>
          {avatarError ? <p className="mt-1.5 text-xs font-medium text-rose-600">{avatarError}</p> : null}
        </div>
      </div>
      <form className="mt-6" onSubmit={(event) => void submit(event)}>
        <div className="grid gap-4 sm:grid-cols-2">
          <label className="field-label">
            Name
            <input
              className="field-input"
              autoComplete="name"
              required
              maxLength={120}
              value={displayName}
              onChange={(event) => setDisplayName(event.target.value)}
            />
          </label>
          <label className="field-label">
            Username
            <input
              className="field-input cursor-not-allowed bg-slate-50 text-slate-500"
              value={user.username}
              readOnly
              aria-describedby="username-help"
            />
            <span id="username-help" className="mt-1.5 block font-normal text-slate-400">
              Usernames cannot be changed.
            </span>
          </label>
        </div>
        <label className="field-label mt-4">
          <span className="inline-flex items-center gap-1.5"><Mail className="size-3.5" /> Email</span>
          <input
            className="field-input"
            type="email"
            autoComplete="email"
            maxLength={320}
            placeholder="you@example.com"
            value={email}
            onChange={(event) => setEmail(event.target.value)}
          />
        </label>
        {message ? <Message tone="success">{message}</Message> : null}
        {error ? <Message tone="error">{error}</Message> : null}
        <button className="button-primary mt-5" type="submit" disabled={saving}>
          <Check className="size-4" /> {saving ? "Saving…" : "Save profile"}
        </button>
      </form>
    </section>
  );
}

function PasswordSettings() {
  const [currentPassword, setCurrentPassword] = useState("");
  const [newPassword, setNewPassword] = useState("");
  const [confirmation, setConfirmation] = useState("");
  const [saving, setSaving] = useState(false);
  const [message, setMessage] = useState("");
  const [error, setError] = useState("");

  const submit = async (event: FormEvent) => {
    event.preventDefault();
    setMessage("");
    setError("");
    if (newPassword !== confirmation) {
      setError("New password and confirmation do not match.");
      return;
    }
    setSaving(true);
    try {
      await api.changePassword({
        current_password: currentPassword,
        new_password: newPassword,
      });
      setCurrentPassword("");
      setNewPassword("");
      setConfirmation("");
      setMessage("Password changed.");
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "Could not change your password.");
    } finally {
      setSaving(false);
    }
  };

  return (
    <section className="surface-panel p-5 lg:p-6">
      <div className="flex items-center gap-3">
        <span className="grid size-10 place-items-center rounded-xl bg-cyan-50 text-cyan-700">
          <LockKeyhole className="size-5" />
        </span>
        <div>
          <h2 className="text-lg font-semibold text-slate-950">Password</h2>
          <p className="mt-0.5 text-sm text-slate-500">Use at least eight characters.</p>
        </div>
      </div>
      <form className="mt-6 space-y-4" onSubmit={(event) => void submit(event)}>
        <label className="field-label">
          Current password
          <input
            className="field-input"
            type="password"
            autoComplete="current-password"
            required
            value={currentPassword}
            onChange={(event) => setCurrentPassword(event.target.value)}
          />
        </label>
        <div className="grid gap-4 sm:grid-cols-2">
          <label className="field-label">
            New password
            <input
              className="field-input"
              type="password"
              autoComplete="new-password"
              required
              minLength={8}
              value={newPassword}
              onChange={(event) => setNewPassword(event.target.value)}
            />
          </label>
          <label className="field-label">
            Confirm new password
            <input
              className="field-input"
              type="password"
              autoComplete="new-password"
              required
              minLength={8}
              value={confirmation}
              onChange={(event) => setConfirmation(event.target.value)}
            />
          </label>
        </div>
        {message ? <Message tone="success">{message}</Message> : null}
        {error ? <Message tone="error">{error}</Message> : null}
        <button className="button-primary" type="submit" disabled={saving}>
          <KeyRound className="size-4" /> {saving ? "Changing…" : "Change password"}
        </button>
      </form>
    </section>
  );
}

function TokenSettings() {
  const [tokens, setTokens] = useState<ApiToken[] | null>(null);
  const [name, setName] = useState("");
  const [created, setCreated] = useState<ApiTokenCreated | null>(null);
  const [copied, setCopied] = useState(false);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState("");

  const load = () => {
    setError("");
    void api.listTokens()
      .then(setTokens)
      .catch((caught: unknown) => {
        setError(caught instanceof Error ? caught.message : "Could not load API tokens.");
      });
  };
  useEffect(load, []);

  const create = async (event: FormEvent) => {
    event.preventDefault();
    setSaving(true);
    setError("");
    setCreated(null);
    setCopied(false);
    try {
      const token = await api.createToken({ name, scopes: ["read", "write"] });
      setCreated(token);
      setTokens((current) => current ? [token, ...current] : [token]);
      setName("");
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "Could not create an API token.");
    } finally {
      setSaving(false);
    }
  };

  const copy = async () => {
    if (!created) return;
    try {
      await navigator.clipboard.writeText(created.token);
      setCopied(true);
    } catch {
      setError("Could not copy the token. Select and copy it manually.");
    }
  };

  const revoke = async (token: ApiToken) => {
    if (!window.confirm(`Revoke the token “${token.name}”?`)) return;
    setError("");
    try {
      await api.revokeToken(token.id);
      setTokens((current) => current?.filter((item) => item.id !== token.id) ?? []);
      if (created?.id === token.id) setCreated(null);
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "Could not revoke the API token.");
    }
  };

  return (
    <section className="surface-panel p-5 lg:p-6">
      <div className="flex items-center gap-3">
        <span className="grid size-10 place-items-center rounded-xl bg-violet-50 text-violet-600">
          <KeyRound className="size-5" />
        </span>
        <div>
          <h2 className="text-lg font-semibold text-slate-950">Personal API tokens</h2>
          <p className="mt-0.5 text-sm text-slate-500">Generate credentials for CLI and API access.</p>
        </div>
      </div>
      <form className="mt-6 flex flex-col gap-3 sm:flex-row" onSubmit={(event) => void create(event)}>
        <label className="field-label flex-1">
          Token name
          <input
            className="field-input"
            required
            maxLength={120}
            placeholder="My CLI"
            value={name}
            onChange={(event) => setName(event.target.value)}
          />
        </label>
        <button className="button-primary sm:mt-5" type="submit" disabled={saving}>
          <Plus className="size-4" /> {saving ? "Generating…" : "Generate token"}
        </button>
      </form>
      {created ? (
        <div className="mt-5 rounded-2xl border border-amber-200 bg-amber-50 p-4">
          <p className="text-sm font-semibold text-amber-950">Copy this token now. It will not be shown again.</p>
          <div className="mt-3 flex items-center gap-2">
            <input
              className="min-h-10 min-w-0 flex-1 rounded-xl border border-amber-200 bg-white px-3 font-mono text-xs text-slate-800"
              value={created.token}
              readOnly
              aria-label="New API token"
              onFocus={(event) => event.currentTarget.select()}
            />
            <button className="button-secondary shrink-0" type="button" onClick={() => void copy()}>
              {copied ? <Check className="size-4" /> : <Copy className="size-4" />}
              {copied ? "Copied" : "Copy"}
            </button>
          </div>
        </div>
      ) : null}
      {error ? <Message tone="error">{error}</Message> : null}
      <div className="mt-6 border-t border-slate-100 pt-2">
        {tokens === null && !error ? <LoadingState label="Loading tokens…" /> : null}
        {tokens?.length === 0 ? (
          <p className="py-6 text-center text-sm text-slate-500">No personal tokens yet.</p>
        ) : null}
        {tokens?.map((token) => (
          <div className="flex flex-wrap items-center justify-between gap-3 border-b border-slate-100 py-4 last:border-0" key={token.id}>
            <div>
              <p className="text-sm font-semibold text-slate-900">{token.name}</p>
              <p className="mt-1 font-mono text-xs text-slate-400">
                {token.token_prefix}… · {token.scopes.join(", ")}
              </p>
            </div>
            <button className="button-secondary min-h-9 px-3 text-rose-600 hover:border-rose-200 hover:bg-rose-50 hover:text-rose-700" type="button" onClick={() => void revoke(token)}>
              <Trash2 className="size-4" /> Revoke
            </button>
          </div>
        ))}
      </div>
    </section>
  );
}

function DeleteAccountSettings() {
  const navigate = useNavigate();
  const { user, clearUser } = useAuth();
  const [confirmation, setConfirmation] = useState("");
  const [password, setPassword] = useState("");
  const [deleting, setDeleting] = useState(false);
  const [error, setError] = useState("");

  const submit = async (event: FormEvent) => {
    event.preventDefault();
    if (!user || confirmation !== user.username) return;
    setDeleting(true);
    setError("");
    try {
      await api.deleteAccount(password);
      clearUser();
      await navigate("/", { replace: true });
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "Could not delete your account.");
      setDeleting(false);
    }
  };

  if (!user) return null;
  return (
    <section className="rounded-2xl border border-rose-200 bg-white p-5 shadow-xs shadow-rose-950/5 lg:p-6">
      <div className="flex items-center gap-3">
        <span className="grid size-10 place-items-center rounded-xl bg-rose-50 text-rose-600">
          <ShieldAlert className="size-5" />
        </span>
        <div>
          <h2 className="text-lg font-semibold text-slate-950">Delete account</h2>
          <p className="mt-0.5 text-sm text-slate-500">This permanently deletes your owned datasets and tokens.</p>
        </div>
      </div>
      <form className="mt-6" onSubmit={(event) => void submit(event)}>
        <div className="grid gap-4 sm:grid-cols-2">
          <label className="field-label">
            Type <span className="font-mono text-rose-600">{user.username}</span> to confirm
            <input
              className="field-input"
              required
              autoComplete="off"
              value={confirmation}
              onChange={(event) => setConfirmation(event.target.value)}
            />
          </label>
          <label className="field-label">
            Current password
            <input
              className="field-input"
              type="password"
              autoComplete="current-password"
              required
              value={password}
              onChange={(event) => setPassword(event.target.value)}
            />
          </label>
        </div>
        {error ? <Message tone="error">{error}</Message> : null}
        <button
          className="mt-5 inline-flex min-h-10 items-center justify-center gap-2 rounded-xl bg-rose-600 px-4 text-sm font-semibold text-white shadow-sm transition hover:bg-rose-500"
          type="submit"
          disabled={deleting || confirmation !== user.username || !password}
        >
          <Trash2 className="size-4" /> {deleting ? "Deleting…" : "Permanently delete account"}
        </button>
      </form>
    </section>
  );
}

export function AccountSettingsPage() {
  const { user, loading } = useAuth();
  if (loading) return <div className="page-shell py-16"><LoadingState label="Loading account…" /></div>;
  if (!user) return <Navigate to="/" replace />;

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
        <div className="mb-5">
          <p className="eyebrow">Personal settings</p>
          <h1 className="mt-2 text-3xl font-semibold tracking-[-0.04em] text-slate-950">Account settings</h1>
          <p className="mt-2 text-sm text-slate-500">Manage your profile, password, and API access.</p>
        </div>
        <div className="grid items-start gap-4 xl:grid-cols-2">
          <ProfileSettings />
          <PasswordSettings />
          <div className="xl:col-span-2"><TokenSettings /></div>
          <div className="xl:col-span-2"><DeleteAccountSettings /></div>
        </div>
      </main>
    </div>
  );
}
