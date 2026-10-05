import { describe, expect, it, vi } from "vitest";
import { ApiError, UNAUTHORIZED_EVENT, api, errorMessage, getToken, setToken } from "./client";

describe("errorMessage", () => {
  it("nimmt einen Text-Detail unverändert", () => {
    expect(errorMessage({ detail: "Eintrag nicht gefunden." }, 404)).toBe("Eintrag nicht gefunden.");
  });
  it("fasst Validierungsfehler zusammen", () => {
    const body = { detail: [{ loc: ["body", "weight_kg"], msg: "zu klein" }, { loc: ["query", "from"], msg: "ungültig" }] };
    expect(errorMessage(body, 422)).toBe("weight_kg: zu klein; from: ungültig");
  });
  it("fällt auf deutsche Standardtexte zurück", () => {
    expect(errorMessage(undefined, 401)).toContain("Nicht angemeldet");
    expect(errorMessage(undefined, 500)).toContain("Serverfehler");
    expect(errorMessage(undefined, 418)).toBe("Fehler (418).");
  });
});

describe("api", () => {
  it("sendet Token und JSON und liefert die Antwort", async () => {
    setToken("abc");
    const fetchMock = vi.fn(async () => new Response(JSON.stringify({ ok: 1 }), { status: 200 }));
    vi.stubGlobal("fetch", fetchMock);
    const out = await api<{ ok: number }>("POST", "/me/goals", { kind: "lose" });
    expect(out).toEqual({ ok: 1 });
    const [url, init] = fetchMock.mock.calls[0] as unknown as [string, RequestInit];
    expect(url).toBe("/api/me/goals");
    expect((init.headers as Record<string, string>).Authorization).toBe("Bearer abc");
    expect(init.body).toBe(JSON.stringify({ kind: "lose" }));
  });

  it("liefert bei 204 undefined", async () => {
    vi.stubGlobal("fetch", vi.fn(async () => new Response(null, { status: 204 })));
    await expect(api("DELETE", "/me/supplements/1")).resolves.toBeUndefined();
  });

  it("wirft ApiError mit Servertext und meldet 401", async () => {
    vi.stubGlobal("fetch", vi.fn(async () => new Response(JSON.stringify({ detail: "Nicht angemeldet." }), { status: 401 })));
    const heard = vi.fn();
    window.addEventListener(UNAUTHORIZED_EVENT, heard);
    await expect(api("GET", "/me")).rejects.toMatchObject({ status: 401, message: "Nicht angemeldet." });
    expect(heard).toHaveBeenCalledOnce();
    window.removeEventListener(UNAUTHORIZED_EVENT, heard);
  });

  it("meldet fehlende Verbindung verständlich", async () => {
    vi.stubGlobal("fetch", vi.fn(async () => Promise.reject(new TypeError("fail"))));
    const err = await api("GET", "/me").catch((e: unknown) => e);
    expect(err).toBeInstanceOf(ApiError);
    expect((err as ApiError).status).toBe(0);
    expect((err as ApiError).message).toContain("nicht erreichbar");
  });

  it("speichert und löscht das Token", () => {
    setToken("t1");
    expect(getToken()).toBe("t1");
    setToken(null);
    expect(getToken()).toBeNull();
  });
});
