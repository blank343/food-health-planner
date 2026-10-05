// Schnittstellen-Client: Token, JSON, deutsche Fehlermeldungen, Upload mit Fortschritt.

const TOKEN_KEY = "fhp.token";

export function getToken(): string | null {
  try {
    return localStorage.getItem(TOKEN_KEY);
  } catch {
    return null;
  }
}

export function setToken(token: string | null): void {
  try {
    if (token) localStorage.setItem(TOKEN_KEY, token);
    else localStorage.removeItem(TOKEN_KEY);
  } catch {
    /* Speicher gesperrt (z. B. privates Fenster): Anmeldung gilt dann nur bis zum Neuladen */
  }
}

export class ApiError extends Error {
  status: number;
  constructor(message: string, status: number) {
    super(message);
    this.name = "ApiError";
    this.status = status;
  }
}

/** Wird ausgelöst, wenn der Server 401 meldet: die Anmeldung ist ungültig. */
export const UNAUTHORIZED_EVENT = "fhp:unauthorized";

const STATUS_TEXT: Record<number, string> = {
  401: "Nicht angemeldet. Bitte Zugangstoken eingeben.",
  403: "Dafür fehlt die Berechtigung.",
  404: "Nicht gefunden.",
  409: "Das passt nicht zum aktuellen Stand. Bitte neu laden und erneut versuchen.",
  413: "Die Datei ist zu groß.",
  415: "Dieser Dateityp wird nicht unterstützt.",
  422: "Die Eingabe ist ungültig.",
  500: "Serverfehler. Bitte später erneut versuchen.",
};

type ValidationItem = { loc?: unknown[]; msg?: string };

/** Macht aus einer FastAPI-Fehlerantwort einen lesbaren deutschen Satz. */
export function errorMessage(body: unknown, status: number): string {
  const detail = (body as { detail?: unknown } | null)?.detail;
  if (typeof detail === "string" && detail.trim()) return detail;
  if (Array.isArray(detail) && detail.length > 0) {
    return (detail as ValidationItem[])
      .map((d) => {
        const field = (d.loc ?? []).filter((p) => p !== "body" && p !== "query").join(".");
        return field ? `${field}: ${d.msg ?? "ungültig"}` : (d.msg ?? "ungültig");
      })
      .join("; ");
  }
  return STATUS_TEXT[status] ?? `Fehler (${status}).`;
}

async function readBody(res: Response): Promise<unknown> {
  const text = await res.text();
  if (!text) return undefined;
  try {
    return JSON.parse(text);
  } catch {
    return undefined;
  }
}

function notifyIfUnauthorized(status: number): void {
  if (status === 401) window.dispatchEvent(new Event(UNAUTHORIZED_EVENT));
}

export async function api<T = unknown>(
  method: "GET" | "POST" | "PUT" | "PATCH" | "DELETE",
  path: string,
  body?: unknown,
): Promise<T> {
  const headers: Record<string, string> = { Accept: "application/json" };
  const token = getToken();
  if (token) headers.Authorization = `Bearer ${token}`;
  if (body !== undefined) headers["Content-Type"] = "application/json";
  let res: Response;
  try {
    res = await fetch(`/api${path}`, {
      method,
      headers,
      body: body === undefined ? undefined : JSON.stringify(body),
    });
  } catch {
    throw new ApiError("Der Server ist nicht erreichbar. Läuft die Verbindung (Tailscale)?", 0);
  }
  const data = await readBody(res);
  if (!res.ok) {
    notifyIfUnauthorized(res.status);
    throw new ApiError(errorMessage(data, res.status), res.status);
  }
  return data as T;
}

/** Datei-Upload (multipart, Feld `file`) mit Fortschritt 0..1. */
export function upload<T = unknown>(
  path: string,
  file: File,
  onProgress?: (fraction: number) => void,
): Promise<T> {
  return new Promise<T>((resolve, reject) => {
    const xhr = new XMLHttpRequest();
    xhr.open("POST", `/api${path}`);
    const token = getToken();
    if (token) xhr.setRequestHeader("Authorization", `Bearer ${token}`);
    xhr.setRequestHeader("Accept", "application/json");
    xhr.upload.onprogress = (e) => {
      if (e.lengthComputable && onProgress) onProgress(e.loaded / e.total);
    };
    xhr.onerror = () =>
      reject(new ApiError("Der Server ist nicht erreichbar. Läuft die Verbindung (Tailscale)?", 0));
    xhr.onload = () => {
      let data: unknown;
      try {
        data = xhr.responseText ? JSON.parse(xhr.responseText) : undefined;
      } catch {
        data = undefined;
      }
      if (xhr.status >= 200 && xhr.status < 300) resolve(data as T);
      else {
        notifyIfUnauthorized(xhr.status);
        reject(new ApiError(errorMessage(data, xhr.status), xhr.status));
      }
    };
    const form = new FormData();
    form.append("file", file);
    xhr.send(form);
  });
}
