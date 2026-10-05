import { type ReactNode, createContext, useCallback, useContext, useEffect, useMemo, useState } from "react";
import { ApiError, UNAUTHORIZED_EVENT, api, getToken, setToken } from "../api/client";

export type Person = {
  id: number;
  name: string;
  sex: "m" | "f";
  birth_date: string;
  height_cm: number | null;
};

type AuthState =
  | { status: "loading" }
  | { status: "anon"; error: string | null }
  | { status: "authed"; person: Person };

type AuthApi = {
  state: AuthState;
  /** Prüft das Token am Server. Liefert `true` bei Erfolg. */
  login: (token: string) => Promise<boolean>;
  logout: () => void;
  /** Lädt das Profil neu (z. B. nach Änderung der Größe). */
  refresh: () => Promise<void>;
};

const Ctx = createContext<AuthApi | null>(null);

export function AuthProvider({ children }: { children: ReactNode }) {
  const [state, setState] = useState<AuthState>(getToken() ? { status: "loading" } : { status: "anon", error: null });

  const logout = useCallback(() => {
    setToken(null);
    setState({ status: "anon", error: null });
  }, []);

  const refresh = useCallback(async () => {
    try {
      const person = await api<Person>("GET", "/me");
      setState({ status: "authed", person });
    } catch (e) {
      setToken(null);
      setState({ status: "anon", error: e instanceof ApiError && e.status !== 401 ? e.message : null });
    }
  }, []);

  useEffect(() => {
    if (getToken()) void refresh();
  }, [refresh]);

  useEffect(() => {
    const onUnauthorized = () => logout();
    window.addEventListener(UNAUTHORIZED_EVENT, onUnauthorized);
    return () => window.removeEventListener(UNAUTHORIZED_EVENT, onUnauthorized);
  }, [logout]);

  const login = useCallback(async (token: string) => {
    setToken(token.trim());
    try {
      const person = await api<Person>("GET", "/me");
      setState({ status: "authed", person });
      return true;
    } catch (e) {
      setToken(null);
      const message =
        e instanceof ApiError && e.status === 401
          ? "Das Zugangstoken ist ungültig. Bitte prüfen und erneut eingeben."
          : e instanceof ApiError
            ? e.message
            : "Anmeldung fehlgeschlagen.";
      setState({ status: "anon", error: message });
      return false;
    }
  }, []);

  const value = useMemo(() => ({ state, login, logout, refresh }), [state, login, logout, refresh]);
  return <Ctx.Provider value={value}>{children}</Ctx.Provider>;
}

export function useAuth(): AuthApi {
  const v = useContext(Ctx);
  if (!v) throw new Error("useAuth braucht einen AuthProvider.");
  return v;
}

/** Die angemeldete Person. Nur innerhalb geschützter Seiten verwenden. */
export function usePerson(): Person {
  const { state } = useAuth();
  if (state.status !== "authed") throw new Error("usePerson nur für angemeldete Nutzer.");
  return state.person;
}
