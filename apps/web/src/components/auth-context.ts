import { createContext, useContext } from "react";

import type { User } from "../types";

export type AuthMode = "login" | "register";

export interface AuthContextValue {
  user: User | null;
  loading: boolean;
  openAuth: (mode?: AuthMode) => void;
  signOut: () => Promise<void>;
  updateUser: (user: User) => void;
  clearUser: () => void;
}

export const AuthContext = createContext<AuthContextValue | null>(null);

export function useAuth(): AuthContextValue {
  const context = useContext(AuthContext);
  if (!context) throw new Error("useAuth must be used inside AuthProvider");
  return context;
}
