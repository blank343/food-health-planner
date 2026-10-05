import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";
import type { components } from "../../api/schema";
import { todayIso } from "../../format";
import { mockServer, renderPage } from "../../test/helpers";
import TargetsPage from "./index";
import { validateManual } from "./ManualForm";

type Targets = components["schemas"]["TargetsOut"];

function targets(over: Partial<Targets> = {}): Targets {
  return {
    date: todayIso(),
    day_type: "moderate",
    target: { kcal: 2150, protein_g: 150, fat_g: 70, carb_g: 240 },
    slots: {
      snack: { kcal: 0, protein_g: 0, fat_g: 0, carb_g: 0 },
      dinner: { kcal: 750, protein_g: 55, fat_g: 25, carb_g: 80 },
      breakfast: { kcal: 500, protein_g: 35, fat_g: 15, carb_g: 60 },
      lunch: { kcal: 900, protein_g: 60, fat_g: 30, carb_g: 100 },
    },
    shares: { breakfast: 0.25, lunch: 0.4, dinner: 0.35, snack: 0 },
    tdee: {
      tdee_kcal: 2600,
      device_kcal: 2500,
      implied_kcal: 2700,
      confidence: 0.82,
      method: "calibrated",
      notes: ["Gerätewert und Gewichtstrend liegen nahe beieinander."],
    },
    body: {
      weight_kg: 80.5,
      weight_date: "2026-10-01",
      body_fat_pct: 18.5,
      lean_mass_kg: null,
      height_cm: 180,
      age_years: 35.2,
    },
    goal: { kind: "lose", rate_kg_per_week: -0.5, applied_rate_kg_per_week: -0.4, valid_from: "2026-09-01" },
    warnings: [],
    ...over,
  };
}

const NO_WEIGHT = {
  status: 422,
  body: { detail: "Es liegt kein Gewicht vor. Bitte zuerst Gesundheitsdaten importieren." },
};

describe("Tagesziel", () => {
  it("zeigt zuerst einen Ladehinweis", () => {
    mockServer({ "GET /me/targets": { body: targets() } });
    renderPage(<TargetsPage />);
    expect(screen.getByRole("status")).toHaveTextContent("Berechne Tagesziel");
  });

  it("fragt standardmäßig den heutigen Tag ab", async () => {
    const server = mockServer({ "GET /me/targets": { body: targets() } });
    renderPage(<TargetsPage />);
    await screen.findByText("2.150 kcal");
    expect(server.calls.find((c) => c.path.startsWith("/me/targets"))?.path).toBe(`/me/targets?date=${todayIso()}`);
    expect(screen.getByLabelText("Datum für das Tagesziel")).toHaveValue(todayIso());
  });

  it("zeigt Kennzahlen und Mahlzeiten ohne leere Slots in fester Reihenfolge", async () => {
    mockServer({ "GET /me/targets": { body: targets() } });
    renderPage(<TargetsPage />);
    expect(await screen.findByText("2.150 kcal")).toBeInTheDocument();
    expect(screen.getByText("150 g")).toBeInTheDocument();
    expect(screen.getByText("70 g")).toBeInTheDocument();
    expect(screen.getByText("240 g")).toBeInTheDocument();
    expect(screen.getByText("Mittlerer Trainingstag")).toBeInTheDocument();

    const card = screen.getByRole("heading", { name: "Verteilung auf Mahlzeiten" }).closest("section")!;
    const rows = within(card)
      .getAllByRole("row")
      .slice(1)
      .map((r) => within(r).getAllByRole("rowheader")[0]?.textContent);
    expect(rows).toEqual(["Frühstück", "Mittagessen", "Abendessen"]);
    expect(within(card).queryByText("Snack")).not.toBeInTheDocument();
  });

  it("erklärt den Energiebedarf", async () => {
    mockServer({ "GET /me/targets": { body: targets() } });
    renderPage(<TargetsPage />);
    const card = (await screen.findByRole("heading", { name: "Energiebedarf" })).closest("section")!;
    expect(within(card).getByText("Kalibriert am Gewichtstrend")).toBeInTheDocument();
    expect(within(card).getByText("2.500 kcal")).toBeInTheDocument();
    expect(within(card).getByText("2.700 kcal")).toBeInTheDocument();
    expect(within(card).getByText("82 %")).toBeInTheDocument();
    expect(within(card).getByText(/liegen nahe beieinander/)).toBeInTheDocument();
  });

  it.each([
    ["device", "Gerät"],
    ["formula", "Formel"],
  ])("benennt die Methode %s als %s", async (method, label) => {
    const base = targets();
    mockServer({ "GET /me/targets": { body: targets({ tdee: { ...base.tdee, method } }) } });
    renderPage(<TargetsPage />);
    const card = (await screen.findByRole("heading", { name: "Energiebedarf" })).closest("section")!;
    expect(within(card).getByText(label)).toBeInTheDocument();
  });

  it("zeigt Körperdaten und Ziel", async () => {
    mockServer({ "GET /me/targets": { body: targets() } });
    renderPage(<TargetsPage />);
    const body = (await screen.findByRole("heading", { name: "Verwendete Körperdaten" })).closest("section")!;
    expect(within(body).getByText("80,5 kg (vom 01.10.2026)")).toBeInTheDocument();
    expect(within(body).getByText("18,5 %")).toBeInTheDocument();
    expect(within(body).getByText("180 cm")).toBeInTheDocument();
    expect(within(body).getByText("35,2 Jahre")).toBeInTheDocument();
    const goal = screen.getByRole("heading", { name: "Ziel" }).closest("section")!;
    expect(within(goal).getByText("Abnehmen")).toBeInTheDocument();
    expect(within(goal).getByText("-0,50 kg/Woche")).toBeInTheDocument();
    expect(within(goal).getByText("-0,40 kg/Woche")).toBeInTheDocument();
    expect(within(goal).getByText("01.09.2026")).toBeInTheDocument();
  });

  it("stellt Warnungen nach Schweregrad dar", async () => {
    mockServer({
      "GET /me/targets": {
        body: targets({
          warnings: [
            { code: "a", severity: "info", message: "Nur ein Hinweis." },
            { code: "b", severity: "warn", message: "Bitte vorsichtig sein." },
            { code: "c", severity: "block", message: "Das ist nicht zulässig." },
          ],
        }),
      },
    });
    renderPage(<TargetsPage />);
    expect((await screen.findByText("Nur ein Hinweis.")).closest(".alert")).toHaveClass("info");
    expect(screen.getByText("Bitte vorsichtig sein.").closest(".alert")).toHaveClass("warn");
    const block = screen.getByText("Das ist nicht zulässig.").closest(".alert");
    expect(block).toHaveClass("error");
    expect(block).toHaveAttribute("role", "alert");
  });

  it("lädt bei Datumswechsel neu", async () => {
    const server = mockServer({ "GET /me/targets": { body: targets() } });
    renderPage(<TargetsPage />);
    await screen.findByText("2.150 kcal");
    const input = screen.getByLabelText("Datum für das Tagesziel");
    await userEvent.clear(input);
    await userEvent.type(input, "2026-09-15");
    await waitFor(() =>
      expect(server.calls.some((c) => c.path === "/me/targets?date=2026-09-15")).toBe(true),
    );
  });

  it("erklärt einen 422-Fehler und zeigt das Formular direkt darunter", async () => {
    mockServer({ "GET /me/targets": NO_WEIGHT });
    renderPage(<TargetsPage />);
    expect(await screen.findByText("Das Tagesziel kann noch nicht berechnet werden.")).toBeInTheDocument();
    expect(screen.getByText(/Es liegt kein Gewicht vor/)).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Einstellungen" })).toHaveAttribute("href", "/einstellungen");
    expect(screen.getByLabelText("Gewicht (kg)")).toBeInTheDocument();
    expect(screen.queryByText("Verteilung auf Mahlzeiten")).not.toBeInTheDocument();
  });

  it("zeigt andere Serverfehler als Fehler", async () => {
    mockServer({ "GET /me/targets": { status: 500, body: {} } });
    renderPage(<TargetsPage />);
    expect(await screen.findByRole("alert")).toHaveTextContent("Serverfehler");
  });
});

describe("Manuelles Formular", () => {
  it("sendet nur ausgefüllte Werte, meldet Erfolg und lädt die Ziele neu", async () => {
    let saved = false;
    const server = mockServer({
      "GET /me/targets": () => (saved ? { body: targets() } : NO_WEIGHT),
      "POST /me/health/manual": () => {
        saved = true;
        return {
          status: 201,
          body: { day: todayIso(), weight_kg: 80.5, body_fat_pct: 18.5, lean_mass_kg: null },
        };
      },
    });
    renderPage(<TargetsPage />);
    await screen.findByText("Das Tagesziel kann noch nicht berechnet werden.");

    await userEvent.type(screen.getByLabelText("Gewicht (kg)"), "80.5");
    await userEvent.type(screen.getByLabelText("Körperfett (%)"), "18.5");
    await userEvent.click(screen.getByRole("button", { name: "Speichern" }));

    expect(await screen.findByText(/Gespeichert für den .*Gewicht 80,5 kg, Körperfett 18,5 %/)).toBeInTheDocument();
    const post = server.calls.find((c) => c.method === "POST");
    expect(post?.path).toBe("/me/health/manual");
    expect(post?.body).toEqual({ day: todayIso(), weight_kg: 80.5, body_fat_pct: 18.5 });

    expect(await screen.findByText("2.150 kcal")).toBeInTheDocument();
    expect(server.calls.filter((c) => c.method === "GET" && c.path.startsWith("/me/targets"))).toHaveLength(2);
    expect(screen.getByLabelText("Gewicht (kg)")).toHaveValue(null);
  });

  it("sendet das gewählte Datum und optional die Magermasse", async () => {
    const server = mockServer({
      "GET /me/targets": NO_WEIGHT,
      "POST /me/health/manual": { status: 201, body: { day: "2026-09-20", weight_kg: null, body_fat_pct: null, lean_mass_kg: 62 } },
    });
    renderPage(<TargetsPage />);
    await screen.findByLabelText("Magermasse (kg)");
    const day = screen.getByLabelText("Datum der Messung");
    await userEvent.clear(day);
    await userEvent.type(day, "2026-09-20");
    await userEvent.type(screen.getByLabelText("Magermasse (kg)"), "62");
    await userEvent.click(screen.getByRole("button", { name: "Speichern" }));
    await screen.findByText(/Magermasse 62,0 kg/);
    expect(server.calls.find((c) => c.method === "POST")?.body).toEqual({ day: "2026-09-20", lean_mass_kg: 62 });
  });

  it("verlangt mindestens einen Wert und sendet dann nichts", async () => {
    const server = mockServer({ "GET /me/targets": NO_WEIGHT });
    renderPage(<TargetsPage />);
    await userEvent.click(await screen.findByRole("button", { name: "Speichern" }));
    expect(await screen.findByText("Bitte mindestens einen Wert angeben.")).toBeInTheDocument();
    expect(server.calls.some((c) => c.method === "POST")).toBe(false);
  });

  it("prüft Grenzen auf Deutsch", async () => {
    const server = mockServer({ "GET /me/targets": NO_WEIGHT });
    renderPage(<TargetsPage />);
    await userEvent.type(await screen.findByLabelText("Gewicht (kg)"), "5");
    await userEvent.click(screen.getByRole("button", { name: "Speichern" }));
    expect(await screen.findByText("Das Gewicht muss zwischen 30 und 300 kg liegen.")).toBeInTheDocument();
    expect(server.calls.some((c) => c.method === "POST")).toBe(false);
  });

  it("zeigt Fehlermeldungen des Servers", async () => {
    mockServer({
      "GET /me/targets": NO_WEIGHT,
      "POST /me/health/manual": { status: 422, body: { detail: "Das Datum liegt in der Zukunft." } },
    });
    renderPage(<TargetsPage />);
    await userEvent.type(await screen.findByLabelText("Gewicht (kg)"), "80");
    await userEvent.click(screen.getByRole("button", { name: "Speichern" }));
    expect(await screen.findByText("Das Datum liegt in der Zukunft.")).toBeInTheDocument();
    expect(screen.queryByText(/Gespeichert/)).not.toBeInTheDocument();
  });

  it("validateManual meldet ein Datum in der Zukunft", () => {
    const e = validateManual({ day: "2030-01-01", weight: 80, fat: null, lean: null, today: "2026-10-05" });
    expect(e.day).toBe("Das Datum liegt in der Zukunft.");
  });
});
