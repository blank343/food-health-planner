import { act, fireEvent, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { mockServer, renderPage } from "../../test/helpers";
import { type ImportJob } from "./jobs";
import ImportsPage from "./index";

// Kleiner Ersatz für XMLHttpRequest: der Test löst Fortschritt und Antwort selbst aus.
class FakeXHR {
  static instances: FakeXHR[] = [];
  upload: { onprogress: ((e: { lengthComputable: boolean; loaded: number; total: number }) => void) | null } = {
    onprogress: null,
  };
  onload: (() => void) | null = null;
  onerror: (() => void) | null = null;
  status = 0;
  responseText = "";
  method = "";
  url = "";
  sent: FormData | null = null;
  open(method: string, url: string) {
    this.method = method;
    this.url = url;
  }
  setRequestHeader() {}
  send(body: FormData) {
    this.sent = body;
    FakeXHR.instances.push(this);
  }
  progress(loaded: number, total: number) {
    this.upload.onprogress?.({ lengthComputable: true, loaded, total });
  }
  respond(status: number, body: unknown) {
    this.status = status;
    this.responseText = JSON.stringify(body);
    this.onload?.();
  }
}

const now = () => new Date().toISOString().slice(0, 19);

function job(over: Partial<ImportJob> = {}): ImportJob {
  return {
    id: 5,
    kind: "apple_health",
    filename: "export.zip",
    status: "queued",
    progress: 0,
    message: null,
    stats: {},
    error: null,
    created_at: now(),
    started_at: null,
    finished_at: null,
    ...over,
  };
}

const HEALTH_STATS = {
  daily_new: 367,
  workout_new: 586,
  date_from: "2025-09-30",
  date_to: "2026-10-02",
  weight_placeholders_removed: 1,
  seconds: 12.3,
};

function lastXhr(): FakeXHR {
  const x = FakeXHR.instances.at(-1);
  if (!x) throw new Error("Es wurde kein Upload gestartet.");
  return x;
}

const advance = (ms: number) => act(async () => void (await vi.advanceTimersByTimeAsync(ms)));

function setup() {
  FakeXHR.instances = [];
  vi.stubGlobal("XMLHttpRequest", FakeXHR);
  return userEvent.setup({ applyAccept: false, advanceTimers: vi.advanceTimersByTime });
}

const input = (name: RegExp) => screen.getByLabelText(name) as HTMLInputElement;
const file = (name: string, size = 2048) => new File([new Uint8Array(size)], name);

beforeEach(() => {
  vi.useFakeTimers({ shouldAdvanceTime: true });
});
afterEach(() => {
  vi.useRealTimers();
});

describe("Importe", () => {
  it("zeigt drei Karten mit beschrifteten Dateifeldern und Hinweisen", async () => {
    mockServer({ "GET /me/imports": { body: [] } });
    renderPage(<ImportsPage />);
    expect(await screen.findByText("Noch keine Importe.")).toBeInTheDocument();
    expect(input(/Health Auto Export: Datei auswählen \(\.zip, \.csv\)/)).toBeInTheDocument();
    expect(input(/Apple Health.*Datei auswählen \(\.zip, \.xml\)/)).toBeInTheDocument();
    expect(input(/Laborbefund \(PDF\): Datei auswählen \(\.pdf\)/)).toBeInTheDocument();
    expect(screen.getByText(/Alle Gesundheitsdaten exportieren/)).toBeInTheDocument();
    expect(screen.getByText(/Große Dateien \(über 1 GB\)/)).toBeInTheDocument();
    expect(screen.getByText(/Der Name im Befund wird nicht gespeichert/)).toBeInTheDocument();
  });

  it("weist eine falsche Dateiendung ab, ohne hochzuladen", async () => {
    const user = setup();
    mockServer({ "GET /me/imports": { body: [] } });
    renderPage(<ImportsPage />);
    await screen.findByText("Noch keine Importe.");
    await user.upload(input(/Laborbefund.*Datei auswählen/), file("befund.zip"));
    expect(await screen.findByText("Dateityp nicht unterstützt. Erlaubt: .pdf.")).toBeInTheDocument();
    expect(FakeXHR.instances).toHaveLength(0);
    // Die Karte bleibt benutzbar
    expect(input(/Laborbefund.*Datei auswählen/)).toBeEnabled();
  });

  it("zeigt Fortschritt, fragt den Job ab und fasst das Ergebnis zusammen", async () => {
    const user = setup();
    const polls = [
      job({ status: "running", progress: 0.4, message: "Lese Datensätze" }),
      job({ status: "done", progress: 1, message: "Import abgeschlossen", stats: HEALTH_STATS }),
    ];
    let listCalls = 0;
    const server = mockServer({
      "GET /me/imports": () => {
        listCalls += 1;
        return { body: listCalls === 1 ? [] : [job({ status: "done", progress: 1, stats: HEALTH_STATS })] };
      },
      "GET /me/imports/5": () => ({ body: polls.shift() ?? polls[0] }),
    });
    renderPage(<ImportsPage />);
    await screen.findByText("Noch keine Importe.");

    await user.upload(input(/Apple Health.*Datei auswählen/), file("export.zip", 3 * 1024 * 1024));
    const xhr = lastXhr();
    expect(xhr.url).toBe("/api/me/imports/apple-health");
    expect(xhr.method).toBe("POST");
    const bar = screen.getByRole("progressbar", { name: "Hochladen …" });
    expect(bar).toHaveAttribute("aria-valuenow", "0");
    expect(screen.getByText(/export\.zip, 3,0 MB/)).toBeInTheDocument();
    expect(input(/Apple Health.*Datei auswählen/)).toBeDisabled();
    act(() => xhr.progress(50, 100));
    expect(screen.getByRole("progressbar", { name: "Hochladen …" })).toHaveAttribute("aria-valuenow", "50");

    act(() => xhr.respond(202, job()));
    expect(await screen.findByRole("progressbar", { name: "Wird verarbeitet …" })).toBeInTheDocument();
    expect(input(/Apple Health.*Datei auswählen/)).toBeDisabled();

    await advance(2000);
    expect(screen.getByText(/Wird verarbeitet … 40 % – Lese Datensätze/)).toBeInTheDocument();

    await advance(2000);
    expect(
      screen.getByText(
        /367 neue Tage, 586 Workouts importiert, Zeitraum 30\.09\.2025 bis 02\.10\.2026; 1 Platzhalter-Gewicht entfernt/,
      ),
    ).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Übersicht" })).toHaveAttribute("href", "/");
    expect(input(/Apple Health.*Datei auswählen/)).toBeEnabled();
    // Liste wurde nach dem Start und nach dem Ende neu geladen
    expect(server.calls.filter((c) => c.path === "/me/imports").length).toBeGreaterThanOrEqual(3);
    const table = screen.getByRole("table");
    expect(within(table).getByText("fertig")).toBeInTheDocument();
    expect(within(table).getByText("Apple Health")).toBeInTheDocument();
  });

  it("fasst einen Laborbefund mit ausstehenden Werten zusammen und verlinkt auf Labor", async () => {
    const user = setup();
    const done = job({ id: 8, kind: "labs", filename: "befund.pdf", status: "done", progress: 1, stats: { results_new: 56, pending: 9 } });
    mockServer({
      "GET /me/imports": { body: [] },
      "GET /me/imports/8": { body: done },
    });
    renderPage(<ImportsPage />);
    await screen.findByText("Noch keine Importe.");
    await user.upload(input(/Laborbefund.*Datei auswählen/), file("befund.pdf"));
    expect(lastXhr().url).toBe("/api/me/imports/labs");
    act(() => lastXhr().respond(202, job({ id: 8, kind: "labs", filename: "befund.pdf" })));
    await screen.findByRole("progressbar", { name: "Wird verarbeitet …" });
    await advance(2000);
    expect(screen.getByText(/56 Laborwerte, 9 stehen noch aus/)).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Labor" })).toHaveAttribute("href", "/labor");
  });

  it("zeigt den Fehlertext eines fehlgeschlagenen Jobs", async () => {
    const user = setup();
    mockServer({
      "GET /me/imports": { body: [] },
      "GET /me/imports/5": {
        body: job({
          kind: "labs",
          status: "failed",
          error: "Das Geburtsdatum im Befund passt nicht zu deinem Profil. Der Befund wurde nicht gespeichert.",
        }),
      },
    });
    renderPage(<ImportsPage />);
    await screen.findByText("Noch keine Importe.");
    await user.upload(input(/Laborbefund.*Datei auswählen/), file("befund.pdf"));
    act(() => lastXhr().respond(202, job({ kind: "labs" })));
    await screen.findByRole("progressbar", { name: "Wird verarbeitet …" });
    await advance(2000);
    const alert = screen.getByRole("alert");
    expect(alert).toHaveTextContent("Das Geburtsdatum im Befund passt nicht zu deinem Profil.");
    expect(input(/Laborbefund.*Datei auswählen/)).toBeEnabled();
  });

  it.each([
    [409, "Für diese Importart läuft bereits ein Import. Bitte warte, bis er fertig ist."],
    [413, "Die Datei ist zu groß (Limit 2048 MB)."],
    [415, "Dateityp nicht unterstützt. Erlaubt: .zip, .csv."],
    [422, "Die Datei ist keine gültige ZIP-Datei."],
  ])("zeigt bei Status %i die Meldung des Servers", async (status, detail) => {
    const user = setup();
    mockServer({ "GET /me/imports": { body: [] } });
    renderPage(<ImportsPage />);
    await screen.findByText("Noch keine Importe.");
    await user.upload(input(/Health Auto Export: Datei auswählen/), file("daten.zip"));
    act(() => lastXhr().respond(status, { detail }));
    expect(await screen.findByRole("alert")).toHaveTextContent(detail);
    expect(input(/Health Auto Export: Datei auswählen/)).toBeEnabled();
  });

  it("nimmt laufende Jobs aus der Liste beim Öffnen wieder auf", async () => {
    const running = job({ id: 9, kind: "hae", filename: "daten.csv", status: "running", progress: 0.3, message: "Lese Datei" });
    const finished = { ...running, status: "done", progress: 1, stats: { daily_new: 1, workout_new: 1 } };
    let polled = 0;
    const server = mockServer({
      "GET /me/imports": { body: [running] },
      "GET /me/imports/9": () => {
        polled += 1;
        return { body: finished };
      },
    });
    renderPage(<ImportsPage />);
    expect(await screen.findByRole("progressbar", { name: "Wird verarbeitet …" })).toBeInTheDocument();
    expect(input(/Health Auto Export: Datei auswählen/)).toBeDisabled();
    expect(input(/Laborbefund.*Datei auswählen/)).toBeEnabled();
    const table = screen.getByRole("table");
    expect(within(table).getByText("läuft")).toBeInTheDocument();
    expect(within(table).getByRole("progressbar", { name: "Fortschritt Health Auto Export" })).toHaveAttribute(
      "aria-valuenow",
      "30",
    );
    expect(polled).toBe(0);

    await advance(2000);
    expect(polled).toBe(1);
    expect(screen.getByText(/1 neuer Tag, 1 Workout importiert/)).toBeInTheDocument();
    expect(server.calls.filter((c) => c.path === "/me/imports/9")).toHaveLength(1);
  });

  it("beendet die Abfrage beim Verlassen der Seite", async () => {
    const running = job({ id: 9, kind: "hae", status: "running", progress: 0.3 });
    const server = mockServer({
      "GET /me/imports": { body: [running] },
      "GET /me/imports/9": { body: running },
    });
    const view = renderPage(<ImportsPage />);
    await screen.findByRole("progressbar", { name: "Wird verarbeitet …" });
    await advance(2000);
    const before = server.calls.filter((c) => c.path === "/me/imports/9").length;
    expect(before).toBe(1);
    view.unmount();
    await advance(10000);
    expect(server.calls.filter((c) => c.path === "/me/imports/9")).toHaveLength(before);
  });

  it("nimmt Dateien per Ziehen entgegen", async () => {
    setup();
    mockServer({ "GET /me/imports": { body: [] } });
    renderPage(<ImportsPage />);
    await screen.findByText("Noch keine Importe.");
    const zone = input(/Health Auto Export: Datei auswählen/).closest(".dropzone");
    expect(zone).not.toBeNull();
    fireEvent.drop(zone as Element, { dataTransfer: { files: [file("daten.csv")] } });
    expect(FakeXHR.instances).toHaveLength(1);
    expect(lastXhr().url).toBe("/api/me/imports/hae");
  });

  it("listet die letzten Importe mit deutschen Bezeichnungen", async () => {
    mockServer({
      "GET /me/imports": {
        body: [
          job({ id: 3, kind: "labs", filename: "a.pdf", status: "failed", error: "Die Datei ist leer.", created_at: "2026-10-02T08:05:00" }),
          job({ id: 2, kind: "hae", filename: "b.csv", status: "queued", created_at: "2026-10-01T10:00:00", started_at: null }),
          job({ id: 1, kind: "apple_health", filename: "export.zip", status: "done", progress: 1, created_at: "2026-09-30T07:30:00" }),
        ],
      },
    });
    renderPage(<ImportsPage />);
    const table = await screen.findByRole("table");
    expect(within(table).getByText("02.10.2026 08:05")).toBeInTheDocument();
    expect(within(table).getByText("Laborbefund")).toBeInTheDocument();
    expect(within(table).getByText("fehlgeschlagen")).toBeInTheDocument();
    expect(within(table).getByText("Die Datei ist leer.")).toBeInTheDocument();
    expect(within(table).getByText("wartet")).toBeInTheDocument();
    expect(within(table).getByText("fertig")).toBeInTheDocument();
    expect(within(table).getByText("b.csv")).toBeInTheDocument();
  });
});
