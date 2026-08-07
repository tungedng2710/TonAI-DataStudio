import {
  ChevronDown,
  LogIn,
  LogOut,
  Settings,
  UserRound,
  UserPlus,
  X,
} from "lucide-react";
import {
  type FormEvent,
  type ReactNode,
  useEffect,
  useRef,
  useState,
} from "react";
import { Link, useNavigate } from "react-router-dom";

import { api } from "../api";
import type { User } from "../types";
import { AuthContext, type AuthMode, useAuth } from "./auth-context";
import { UserAvatar } from "./UserAvatar";

function AuthDialog({
  initialMode,
  close,
  authenticated,
}: {
  initialMode: AuthMode;
  close: () => void;
  authenticated: (user: User) => void;
}) {
  const [mode, setMode] = useState<AuthMode>(initialMode);
  const [username, setUsername] = useState("");
  const [displayName, setDisplayName] = useState("");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState("");
  const [saving, setSaving] = useState(false);

  const submit = async (event: FormEvent) => {
    event.preventDefault();
    setSaving(true);
    setError("");
    try {
      const user = mode === "login"
        ? await api.login({ username, password })
        : await api.register({ username, display_name: displayName, email, password });
      authenticated(user);
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "Authentication failed.");
      setSaving(false);
    }
  };

  const switchMode = (next: AuthMode) => {
    setMode(next);
    setError("");
    setPassword("");
  };

  return (
    <div className="fixed inset-0 z-[60] grid place-items-center bg-slate-950/70 p-4 backdrop-blur-sm">
      <form
        className="modal-panel max-h-[calc(100vh-2rem)] max-w-md overflow-y-auto"
        onSubmit={(event) => void submit(event)}
        role="dialog"
        aria-modal="true"
        aria-labelledby="auth-title"
      >
        <div className="flex items-start justify-between gap-4">
          <div>
            <p className="eyebrow">Secure workspace</p>
            <h2 id="auth-title" className="mt-1 text-2xl font-semibold tracking-tight text-slate-950">
              {mode === "login" ? "Sign in" : "Create your account"}
            </h2>
            <p className="mt-2 text-sm leading-6 text-slate-600">
              {mode === "login"
                ? "Access your private datasets and manage repositories you own."
                : "The first account becomes the workspace administrator and adopts existing datasets."}
            </p>
          </div>
          <button className="icon-button" type="button" onClick={close} aria-label="Close authentication">
            <X className="size-4" />
          </button>
        </div>

        <div className="mt-6 space-y-4">
          <label className="field-label">
            Username
            <input
              className="field-input"
              autoFocus
              autoComplete="username"
              required
              minLength={mode === "register" ? 3 : 1}
              pattern={mode === "register" ? "[a-z0-9][a-z0-9_-]{2,63}" : undefined}
              placeholder="your-username"
              value={username}
              onChange={(event) => setUsername(event.target.value.toLowerCase())}
            />
          </label>
          {mode === "register" ? (
            <>
              <label className="field-label">
                Display name <span className="font-normal text-slate-400">(optional)</span>
                <input className="field-input" autoComplete="name" value={displayName} onChange={(event) => setDisplayName(event.target.value)} />
              </label>
              <label className="field-label">
                Email <span className="font-normal text-slate-400">(optional)</span>
                <input className="field-input" type="email" autoComplete="email" value={email} onChange={(event) => setEmail(event.target.value)} />
              </label>
            </>
          ) : null}
          <label className="field-label">
            Password
            <input
              className="field-input"
              type="password"
              autoComplete={mode === "login" ? "current-password" : "new-password"}
              required
              minLength={mode === "register" ? 8 : 1}
              value={password}
              onChange={(event) => setPassword(event.target.value)}
            />
          </label>
        </div>

        {error ? <p className="mt-4 rounded-xl bg-rose-50 px-4 py-3 text-sm font-medium text-rose-700">{error}</p> : null}
        <button className="button-primary mt-6 w-full" type="submit" disabled={saving}>
          {mode === "login" ? <LogIn className="size-4" /> : <UserPlus className="size-4" />}
          {saving ? "Please wait…" : mode === "login" ? "Sign in" : "Create account"}
        </button>
        <p className="mt-5 text-center text-sm text-slate-500">
          {mode === "login" ? "New to this Studio?" : "Already have an account?"}{" "}
          <button
            className="font-semibold text-indigo-600 hover:text-indigo-500"
            type="button"
            onClick={() => switchMode(mode === "login" ? "register" : "login")}
          >
            {mode === "login" ? "Create account" : "Sign in"}
          </button>
        </p>
      </form>
    </div>
  );
}

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<User | null>(null);
  const [loading, setLoading] = useState(true);
  const [dialogMode, setDialogMode] = useState<AuthMode | null>(null);

  useEffect(() => {
    void api.currentUser()
      .then(setUser)
      .catch(() => setUser(null))
      .finally(() => setLoading(false));
  }, []);

  const signOut = async () => {
    try {
      await api.logout();
    } finally {
      setUser(null);
    }
  };

  return (
    <AuthContext.Provider
      value={{
        user,
        loading,
        openAuth: (mode = "login") => setDialogMode(mode),
        signOut,
        updateUser: setUser,
        clearUser: () => setUser(null),
      }}
    >
      {children}
      {dialogMode ? (
        <AuthDialog
          initialMode={dialogMode}
          close={() => setDialogMode(null)}
          authenticated={(nextUser) => {
            setUser(nextUser);
            setDialogMode(null);
          }}
        />
      ) : null}
    </AuthContext.Provider>
  );
}

export function AccountControls() {
  const { user, loading, openAuth, signOut } = useAuth();
  const [open, setOpen] = useState(false);
  const rootRef = useRef<HTMLDivElement>(null);
  const navigate = useNavigate();

  useEffect(() => {
    if (!open) return;
    const close = (event: PointerEvent) => {
      if (!rootRef.current?.contains(event.target as Node)) setOpen(false);
    };
    document.addEventListener("pointerdown", close);
    return () => document.removeEventListener("pointerdown", close);
  }, [open]);

  if (loading) return <span className="h-8 w-24 animate-pulse rounded-lg bg-slate-100" />;
  if (!user) {
    return (
      <button className="header-action" type="button" onClick={() => openAuth("login")}>
        <LogIn className="size-4" /> Sign in
      </button>
    );
  }
  return (
    <div className="relative" ref={rootRef}>
      <button
        className="flex items-center gap-1 rounded-full p-0.5 text-slate-500 outline-none transition hover:bg-indigo-50 focus-visible:ring-2 focus-visible:ring-indigo-500"
        type="button"
        aria-expanded={open}
        aria-haspopup="menu"
        aria-label="Open user menu"
        onClick={() => setOpen((current) => !current)}
      >
        <UserAvatar user={user} className="size-8" />
        <ChevronDown className="mr-1 size-3.5" />
      </button>
      {open ? (
        <div
          className="absolute top-full right-0 z-50 mt-2 w-64 overflow-hidden rounded-xl border border-slate-200 bg-white p-1.5 shadow-xl shadow-slate-950/10"
          role="menu"
        >
          <div className="flex items-center gap-3 border-b border-slate-100 px-3 py-3">
            <UserAvatar user={user} className="size-10" />
            <div className="min-w-0">
              <p className="truncate text-sm font-semibold text-slate-900">
                {user.display_name || user.username}
              </p>
              <p className="truncate text-xs text-slate-500">@{user.username}</p>
            </div>
          </div>
          <Link
            className="mt-1 flex items-center gap-3 rounded-lg px-3 py-2.5 text-sm font-medium text-slate-700 hover:bg-indigo-50 hover:text-indigo-700"
            to={`/users/${encodeURIComponent(user.username)}`}
            role="menuitem"
            onClick={() => setOpen(false)}
          >
            <UserRound className="size-4" /> Your profile
          </Link>
          <Link
            className="flex items-center gap-3 rounded-lg px-3 py-2.5 text-sm font-medium text-slate-700 hover:bg-indigo-50 hover:text-indigo-700"
            to="/settings"
            role="menuitem"
            onClick={() => setOpen(false)}
          >
            <Settings className="size-4" /> User settings
          </Link>
          <button
            className="flex w-full items-center gap-3 rounded-lg px-3 py-2.5 text-left text-sm font-medium text-rose-600 hover:bg-rose-50"
            type="button"
            role="menuitem"
            onClick={() => {
              setOpen(false);
              void signOut().then(() => navigate("/"));
            }}
          >
            <LogOut className="size-4" /> Log out
          </button>
        </div>
      ) : null}
    </div>
  );
}
