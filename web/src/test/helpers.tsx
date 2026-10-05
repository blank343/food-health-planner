// Testhilfen: Server-Antworten festlegen und Seiten innerhalb von Router/Anmeldung rendern.
import { render } from "@testing-library/react";
import type { ReactElement } from "react";
import { MemoryRouter } from "react-router-dom";
import { vi } from "vitest";
import { setToken } from "../api/client";
import { AuthProvider, type Person } from "../auth/AuthContext";

export type MockResponse = { status?: number; body?: unknown };
export type Handler = MockResponse | ((req: { method: string; path: string; body: unknown }) => MockResponse);

export type MockServer = { calls: { method: string; path: string; body: unknown }[] };

export const TEST_PERSON: Person = { id: 1, name: "Test A", sex: "m", birth_date: "1990-01-01", height_cm: 180 };

/**
 * Ersetzt `fetch`. Schlüssel: `"GET /me/dashboard"` (ohne `/api`, Query-Parameter gehören zum Pfad).
 * Nicht definierte Routen liefern 404, `GET /me` liefert `TEST_PERSON`.
 */
export function mockServer(routes: Record<string, Handler>): MockServer {
  const server: MockServer = { calls: [] };
  const table: Record<string, Handler> = { "GET /me": { body: TEST_PERSON }, ...routes };
  vi.stubGlobal(
    "fetch",
    vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      const url = String(input).replace(/^\/api/, "");
      const method = (init?.method ?? "GET").toUpperCase();
      const body = init?.body ? JSON.parse(String(init.body)) : undefined;
      server.calls.push({ method, path: url, body });
      const h = table[`${method} ${url}`] ?? table[`${method} ${url.split("?")[0]}`];
      if (!h) return new Response(JSON.stringify({ detail: "Nicht gefunden." }), { status: 404 });
      const res = typeof h === "function" ? h({ method, path: url, body }) : h;
      const status = res.status ?? 200;
      // Antworten mit Status 204 dürfen laut Fetch-Standard keinen Inhalt haben (auch keinen leeren)
      const text = status === 204 || res.body === undefined ? null : JSON.stringify(res.body);
      return new Response(text, { status });
    }),
  );
  return server;
}

/** Rendert eine Seite als angemeldete Person (Token gesetzt, `GET /me` gemockt). */
export function renderPage(ui: ReactElement, { route = "/" }: { route?: string } = {}) {
  setToken("test-token");
  return render(
    <MemoryRouter initialEntries={[route]}>
      <AuthProvider>{ui}</AuthProvider>
    </MemoryRouter>,
  );
}
