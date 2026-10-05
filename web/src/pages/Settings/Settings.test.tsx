import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it } from "vitest";
import { useAuth } from "../../auth/AuthContext";
import { todayIso } from "../../format";
import { type MockServer, mockServer, renderPage } from "../../test/helpers";
import { THEME_KEY } from "../../theme";
import SettingsPage from "./index";

const EFFECTIVE = {
  kcal_floor: null,
  protein_floor_g_per_kg: 1.2,
  max_rate_kg_per_week: null,
  weight_floor_kg: null,
  bf_floor_pct: null,
  taper_weight_kg: 3,
  taper_bf_pct_points: 2,
  kcal_per_kg: 7700,
  use_katch_mcardle: false,
  tdee_calibration: true,
  reported_intake_kcal: null,
  day_type_weights: { rest: 0.95, easy: 1, moderate: 1.03, hard: 1.08 },
  slot_shares: { breakfast: 0.3, lunch: 0.3, dinner: 0.4 },
  slot_shares_weekend: null,
  single_meal_max_kcal: null,
  source_priority: ["manual", "apple_health_xml", "hae_zip"],
};

const GOAL = {
  id: 7,
  kind: "lose",
  rate_kg_per_week: 0.5,
  kcal_modifier_pct: null,
  protein_g_per_kg: 2,
  fat_pct: null,
  valid_from: "2026-09-01",
  note: "Testphase",
  created_at: "2026-09-01T08:00:00",
};

function settingsRoutes(stored: Record<string, unknown> = {}) {
  return {
    "GET /me/settings": { body: { effective: { ...EFFECTIVE, ...stored }, stored } },
    "PUT /me/settings": ({ body }: { body: unknown }) => ({
      body: { effective: { ...EFFECTIVE, ...(body as object) }, stored: body },
    }),
    "GET /me/goals": { body: [GOAL] },
    "GET /me/goals/active": { body: GOAL },
  };
}

function Gate() {
  const { state } = useAuth();
  return state.status === "authed" ? <SettingsPage /> : <p>Lädt …</p>;
}

async function open(server?: Parameters<typeof mockServer>[0]) {
  const s = mockServer(server ?? settingsRoutes());
  renderPage(<Gate />);
  await screen.findByRole("form", { name: "Sicherheitsgrenzen" });
  return s;
}

const form = (name: string) => within(screen.getByRole("form", { name }));
const calls = (s: MockServer, method: string, path: string) => s.calls.filter((c) => c.method === method && c.path === path);

beforeEach(() => {
  localStorage.clear();
  delete document.documentElement.dataset.theme;
});
afterEach(() => {
  localStorage.clear();
  delete document.documentElement.dataset.theme;
});

describe("Einstellungen: Laden", () => {
  it("zeigt zuerst einen Ladezustand und dann alle Abschnitte", async () => {
    mockServer(settingsRoutes());
    renderPage(<Gate />);
    expect(screen.getByText("Lädt …")).toBeInTheDocument();
    for (const name of ["Profil", "Neue Zielversion", "Sicherheitsgrenzen", "Energiebedarf", "Mahlzeiten-Verteilung", "Datenquellen"]) {
      expect(await screen.findByRole("form", { name })).toBeInTheDocument();
    }
    expect(screen.getByRole("heading", { name: "Darstellung" })).toBeInTheDocument();
  });

  it("füllt die Felder aus den gespeicherten Werten vor und zeigt Standardwerte als Platzhalter", async () => {
    await open(settingsRoutes({ kcal_floor: 1400, taper_weight_kg: 4.5 }));
    const f = form("Sicherheitsgrenzen");
    expect(f.getByLabelText("Untergrenze Energie pro Tag (kcal)")).toHaveValue("1400");
    expect(f.getByLabelText("Untergrenze Energie pro Tag (kcal)")).toHaveAttribute(
      "placeholder",
      "Standard: max. 1500/1200 kcal oder Grundumsatz",
    );
    expect(f.getByLabelText("Tempo-Auslauf vor der Gewichtsgrenze (kg)")).toHaveValue("4,5");
    expect(f.getByLabelText("Untergrenze Protein (g/kg Körpergewicht)")).toHaveValue("");
    expect(f.getByLabelText("Untergrenze Protein (g/kg Körpergewicht)")).toHaveAttribute("placeholder", "Standard: 1,2");
    expect(screen.getByText(/warnt nur \(ohne zu blockieren\)/)).toBeInTheDocument();
  });

  it("zeigt einen Ladefehler der Einstellungen", async () => {
    mockServer({ ...settingsRoutes(), "GET /me/settings": { status: 500, body: { detail: "Kaputt." } } });
    renderPage(<Gate />);
    expect(await screen.findByText("Kaputt.")).toBeInTheDocument();
  });
});

describe("Einstellungen: Profil", () => {
  it("sendet nur geänderte Felder und lädt das Profil neu", async () => {
    const s = await open({ ...settingsRoutes(), "PATCH /me": { body: { id: 1, name: "Test A", sex: "m", birth_date: "1990-01-01", height_cm: 182 } } });
    const f = form("Profil");
    expect(f.getByLabelText("Name")).toHaveValue("Test A");
    expect(f.getByLabelText("Geburtsdatum")).toHaveValue("1990-01-01");
    expect(f.getByLabelText("Körpergröße (cm)")).toHaveValue("180");
    const before = calls(s, "GET", "/me").length;
    await userEvent.clear(f.getByLabelText("Körpergröße (cm)"));
    await userEvent.type(f.getByLabelText("Körpergröße (cm)"), "182");
    await userEvent.click(f.getByRole("button", { name: "Speichern" }));
    expect(await f.findByText("Gespeichert.")).toBeInTheDocument();
    expect(calls(s, "PATCH", "/me")).toEqual([{ method: "PATCH", path: "/me", body: { height_cm: 182 } }]);
    await waitFor(() => expect(calls(s, "GET", "/me").length).toBeGreaterThan(before));
  });

  it("sendet nichts, wenn nichts geändert wurde", async () => {
    const s = await open();
    await userEvent.click(form("Profil").getByRole("button", { name: "Speichern" }));
    expect(await screen.findByText("Es gibt keine Änderungen zu speichern.")).toBeInTheDocument();
    expect(calls(s, "PATCH", "/me")).toHaveLength(0);
  });

  it("zeigt die Servermeldung bei doppeltem Namen (409)", async () => {
    await open({ ...settingsRoutes(), "PATCH /me": { status: 409, body: { detail: "Dieser Name ist bereits vergeben." } } });
    const f = form("Profil");
    await userEvent.clear(f.getByLabelText("Name"));
    await userEvent.type(f.getByLabelText("Name"), "Test B");
    await userEvent.click(f.getByRole("button", { name: "Speichern" }));
    expect(await f.findByText("Dieser Name ist bereits vergeben.")).toBeInTheDocument();
  });

  it("prüft die Körpergröße vor dem Senden", async () => {
    const s = await open();
    const f = form("Profil");
    await userEvent.clear(f.getByLabelText("Körpergröße (cm)"));
    await userEvent.type(f.getByLabelText("Körpergröße (cm)"), "20");
    await userEvent.click(f.getByRole("button", { name: "Speichern" }));
    expect(await f.findByText(/nicht kleiner als 50/)).toBeInTheDocument();
    expect(calls(s, "PATCH", "/me")).toHaveLength(0);
  });
});

describe("Einstellungen: Ziel", () => {
  it("zeigt aktives Ziel und Historie", async () => {
    await open();
    expect(await screen.findByText(/seit 01\.09\.2026/)).toBeInTheDocument();
    expect(screen.getByRole("columnheader", { name: "Gültig ab" })).toBeInTheDocument();
    expect(screen.getByRole("cell", { name: "Testphase" })).toBeInTheDocument();
    expect(screen.getAllByText("0,50 kg/Woche").length).toBeGreaterThan(0);
    expect(screen.getByText(/ältere bleiben unverändert in der Historie/)).toBeInTheDocument();
  });

  it("zeigt bei 404 „Noch kein Ziel hinterlegt“", async () => {
    await open({
      ...settingsRoutes(),
      "GET /me/goals/active": { status: 404, body: { detail: "Für den 2026-10-05 ist kein Ziel hinterlegt." } },
      "GET /me/goals": { body: [] },
    });
    expect(await screen.findByText("Noch kein Ziel hinterlegt")).toBeInTheDocument();
    expect(screen.getByText("Noch keine Ziele gespeichert.")).toBeInTheDocument();
  });

  it("legt ein Abnehmen-Ziel mit Tempo an", async () => {
    const s = await open({ ...settingsRoutes(), "POST /me/goals": { status: 201, body: GOAL } });
    const f = form("Neue Zielversion");
    expect(f.getByText("Zum Beispiel 0,5")).toBeInTheDocument();
    await userEvent.type(f.getByLabelText("Gewünschtes Tempo (kg/Woche)"), "0,5");
    await userEvent.type(f.getByLabelText("Protein (g/kg Körpergewicht)"), "2");
    await userEvent.type(f.getByLabelText("Notiz"), "Start");
    await userEvent.click(f.getByRole("button", { name: "Speichern" }));
    expect(await f.findByText("Neue Zielversion gespeichert.")).toBeInTheDocument();
    expect(calls(s, "POST", "/me/goals")[0]?.body).toEqual({
      kind: "lose",
      rate_kg_per_week: 0.5,
      protein_g_per_kg: 2,
      valid_from: todayIso(),
      note: "Start",
    });
    // Aktives Ziel und Historie werden neu geladen.
    await waitFor(() => expect(calls(s, "GET", "/me/goals").length).toBeGreaterThan(1));
  });

  it("legt „Gewicht halten“ ohne Tempo an", async () => {
    const s = await open({ ...settingsRoutes(), "POST /me/goals": { status: 201, body: GOAL } });
    const f = form("Neue Zielversion");
    await userEvent.type(f.getByLabelText("Gewünschtes Tempo (kg/Woche)"), "0.5");
    await userEvent.selectOptions(f.getByLabelText("Art"), "maintain");
    expect(f.queryByLabelText("Gewünschtes Tempo (kg/Woche)")).not.toBeInTheDocument();
    await userEvent.click(f.getByRole("button", { name: "Speichern" }));
    await f.findByText("Neue Zielversion gespeichert.");
    expect(calls(s, "POST", "/me/goals")[0]?.body).toEqual({ kind: "maintain", valid_from: todayIso() });
  });

  it("verlangt entweder Tempo oder Prozent", async () => {
    const s = await open();
    const f = form("Neue Zielversion");
    await userEvent.type(f.getByLabelText("Gewünschtes Tempo (kg/Woche)"), "0.5");
    await userEvent.type(f.getByLabelText("Energieanpassung (%)"), "-10");
    await userEvent.click(f.getByRole("button", { name: "Speichern" }));
    expect(await f.findByText(/nicht beides/)).toBeInTheDocument();
    expect(calls(s, "POST", "/me/goals")).toHaveLength(0);
  });

  it("sendet die Energieanpassung in Prozent", async () => {
    const s = await open({ ...settingsRoutes(), "POST /me/goals": { status: 201, body: GOAL } });
    const f = form("Neue Zielversion");
    await userEvent.type(f.getByLabelText("Energieanpassung (%)"), "-10");
    await userEvent.click(f.getByRole("button", { name: "Speichern" }));
    await f.findByText("Neue Zielversion gespeichert.");
    expect(calls(s, "POST", "/me/goals")[0]?.body).toEqual({ kind: "lose", kcal_modifier_pct: -10, valid_from: todayIso() });
  });

  it("zeigt Serverfehler beim Anlegen", async () => {
    await open({ ...settingsRoutes(), "POST /me/goals": { status: 422, body: { detail: "Ziel ungültig." } } });
    const f = form("Neue Zielversion");
    await userEvent.click(f.getByRole("button", { name: "Speichern" }));
    expect(await f.findByText("Ziel ungültig.")).toBeInTheDocument();
  });
});

describe("Einstellungen: Sicherheitsgrenzen und Energiebedarf", () => {
  it("sendet nur gesetzte Felder und behält übrige gespeicherte Werte", async () => {
    const s = await open(settingsRoutes({ source_priority: ["hae_zip", "manual"] }));
    const f = form("Sicherheitsgrenzen");
    await userEvent.type(f.getByLabelText("Gewichtsgrenze (kg)"), "70,5");
    await userEvent.click(f.getByRole("button", { name: "Speichern" }));
    expect(await f.findByText("Gespeichert.")).toBeInTheDocument();
    expect(calls(s, "PUT", "/me/settings")[0]?.body).toEqual({
      source_priority: ["hae_zip", "manual"],
      weight_floor_kg: 70.5,
    });
  });

  it("sendet bei leeren Feldern ein leeres Objekt", async () => {
    const s = await open();
    await userEvent.click(form("Sicherheitsgrenzen").getByRole("button", { name: "Speichern" }));
    await screen.findAllByText("Gespeichert.");
    expect(calls(s, "PUT", "/me/settings")[0]?.body).toEqual({});
  });

  it("prüft Werte wie der Server", async () => {
    const s = await open();
    const f = form("Sicherheitsgrenzen");
    await userEvent.type(f.getByLabelText("Körperfett-Grenze (%)"), "80");
    await userEvent.type(f.getByLabelText("Gewichtsgrenze (kg)"), "0");
    await userEvent.click(f.getByRole("button", { name: "Speichern" }));
    expect(await f.findByText(/nicht größer als 60/)).toBeInTheDocument();
    expect(f.getByText(/muss größer als 0 sein/)).toBeInTheDocument();
    expect(calls(s, "PUT", "/me/settings")).toHaveLength(0);
  });

  it("setzt den Abschnitt zurück und behält andere Abschnitte", async () => {
    const s = await open(settingsRoutes({ kcal_floor: 1400, taper_weight_kg: 4, source_priority: ["manual"] }));
    const f = form("Sicherheitsgrenzen");
    await userEvent.click(f.getByRole("button", { name: "Auf Standard zurücksetzen" }));
    await f.findByText("Gespeichert.");
    expect(calls(s, "PUT", "/me/settings")[0]?.body).toEqual({ source_priority: ["manual"] });
    expect(f.getByLabelText("Untergrenze Energie pro Tag (kcal)")).toHaveValue("");
    expect(f.getByLabelText("Tempo-Auslauf vor der Gewichtsgrenze (kg)")).toHaveValue("");
  });

  it("zeigt Serverfehler beim Speichern", async () => {
    await open({ ...settingsRoutes(), "PUT /me/settings": { status: 422, body: { detail: "kcal_floor: Wert zu klein" } } });
    const f = form("Sicherheitsgrenzen");
    await userEvent.type(f.getByLabelText("Untergrenze Energie pro Tag (kcal)"), "1200");
    await userEvent.click(f.getByRole("button", { name: "Speichern" }));
    expect(await f.findByText("kcal_floor: Wert zu klein")).toBeInTheDocument();
    expect(f.queryByText("Gespeichert.")).not.toBeInTheDocument();
  });

  it("Energiebedarf: Schalter nur bei Abweichung vom Standard, Zahlen werden gesendet", async () => {
    const s = await open();
    const f = form("Energiebedarf");
    expect(f.getByLabelText("Kalibrierung am Gewichtstrend")).toBeChecked();
    expect(f.getByLabelText("Grundumsatz nach Katch-McArdle")).not.toBeChecked();
    expect(f.getByLabelText("Energie pro kg Körpermasse (kcal)")).toHaveAttribute("placeholder", "Standard: 7.700");
    await userEvent.type(f.getByLabelText("Aktuelle Aufnahme (kcal pro Tag, grob)"), "2200");
    await userEvent.click(f.getByLabelText("Grundumsatz nach Katch-McArdle"));
    await userEvent.click(f.getByRole("button", { name: "Speichern" }));
    await f.findByText("Gespeichert.");
    expect(calls(s, "PUT", "/me/settings")[0]?.body).toEqual({ reported_intake_kcal: 2200, use_katch_mcardle: true });
  });

  it("Energiebedarf: Kalibrierung ausschalten wird gespeichert", async () => {
    const s = await open();
    const f = form("Energiebedarf");
    await userEvent.click(f.getByLabelText("Kalibrierung am Gewichtstrend"));
    await userEvent.click(f.getByRole("button", { name: "Speichern" }));
    await f.findByText("Gespeichert.");
    expect(calls(s, "PUT", "/me/settings")[0]?.body).toEqual({ tdee_calibration: false });
  });
});

describe("Einstellungen: Mahlzeiten-Verteilung", () => {
  const week = () => within(screen.getByRole("group", { name: "Montag bis Freitag" }));

  it("zeigt die normalisierte Vorschau", async () => {
    await open();
    expect(week().getByText("Keine eigene Verteilung: Der Standard wird verwendet.")).toBeInTheDocument();
    expect(week().getByLabelText("Frühstück")).toHaveAttribute("placeholder", "Standard: 0,3");
    await userEvent.type(week().getByLabelText("Frühstück"), "1");
    await userEvent.type(week().getByLabelText("Mittagessen"), "1");
    await userEvent.type(week().getByLabelText("Abendessen"), "2");
    expect(week().getByLabelText("Frühstück")).toHaveAccessibleDescription("Anteil: 25 %");
    expect(week().getByLabelText("Abendessen")).toHaveAccessibleDescription("Anteil: 50 %");
    expect(week().getByLabelText("Snack")).toHaveAccessibleDescription("Anteil: 0 %");
  });

  it("Vorlage „Nur Frühstück“ speichert nur das Frühstück", async () => {
    const s = await open();
    await userEvent.click(week().getByRole("button", { name: "Nur Frühstück (100 %)" }));
    expect(week().getByLabelText("Frühstück")).toHaveAccessibleDescription("Anteil: 100 %");
    await userEvent.click(form("Mahlzeiten-Verteilung").getByRole("button", { name: "Speichern" }));
    await screen.findAllByText("Gespeichert.");
    expect(calls(s, "PUT", "/me/settings")[0]?.body).toEqual({ slot_shares: { breakfast: 1 } });
  });

  it("verhindert negative Werte und Summe 0", async () => {
    const s = await open();
    const f = form("Mahlzeiten-Verteilung");
    await userEvent.type(week().getByLabelText("Frühstück"), "-1");
    await userEvent.click(f.getByRole("button", { name: "Speichern" }));
    expect(await screen.findByText("Darf nicht negativ sein.")).toBeInTheDocument();
    await userEvent.clear(week().getByLabelText("Frühstück"));
    await userEvent.type(week().getByLabelText("Frühstück"), "0");
    await userEvent.click(f.getByRole("button", { name: "Speichern" }));
    expect(await screen.findByText("Mindestens ein Anteil muss größer als 0 sein.")).toBeInTheDocument();
    expect(calls(s, "PUT", "/me/settings")).toHaveLength(0);
  });

  it("Wochenende: eigene Verteilung nur ohne „wie unter der Woche“", async () => {
    const s = await open();
    expect(screen.queryByRole("group", { name: "Samstag und Sonntag" })).not.toBeInTheDocument();
    await userEvent.click(screen.getByLabelText("Samstag und Sonntag wie unter der Woche"));
    const weekend = within(screen.getByRole("group", { name: "Samstag und Sonntag" }));
    await userEvent.type(weekend.getByLabelText("Frühstück"), "2");
    await userEvent.type(weekend.getByLabelText("Abendessen"), "2");
    expect(weekend.getByLabelText("Frühstück")).toHaveAccessibleDescription("Anteil: 50 %");
    await userEvent.click(form("Mahlzeiten-Verteilung").getByRole("button", { name: "Speichern" }));
    await screen.findAllByText("Gespeichert.");
    expect(calls(s, "PUT", "/me/settings")[0]?.body).toEqual({ slot_shares_weekend: { breakfast: 2, dinner: 2 } });
  });

  it("füllt gespeicherte Werte vor und setzt zurück", async () => {
    const s = await open(settingsRoutes({ slot_shares: { breakfast: 1, lunch: 3 }, slot_shares_weekend: { dinner: 1 } }));
    expect(week().getByLabelText("Mittagessen")).toHaveValue("3");
    expect(week().getByLabelText("Mittagessen")).toHaveAccessibleDescription("Anteil: 75 %");
    expect(screen.getByLabelText("Samstag und Sonntag wie unter der Woche")).not.toBeChecked();
    await userEvent.click(form("Mahlzeiten-Verteilung").getByRole("button", { name: "Auf Standard zurücksetzen" }));
    await screen.findAllByText("Gespeichert.");
    expect(calls(s, "PUT", "/me/settings")[0]?.body).toEqual({});
    expect(week().getByLabelText("Mittagessen")).toHaveValue("");
    expect(screen.getByLabelText("Samstag und Sonntag wie unter der Woche")).toBeChecked();
  });
});

describe("Einstellungen: Datenquellen", () => {
  const names = () => screen.getAllByRole("listitem").map((li) => li.textContent ?? "").filter((t) => /^\d\./.test(t));

  it("zeigt deutsche Namen und ändert die Reihenfolge", async () => {
    const s = await open();
    expect(names().map((t) => t.replace(/Nach oben|Nach unten/g, ""))).toEqual([
      "1. Manuell",
      "2. Apple Health",
      "3. Health Auto Export",
    ]);
    expect(screen.getByRole("button", { name: "Manuell nach oben" })).toBeDisabled();
    expect(screen.getByRole("button", { name: "Health Auto Export nach unten" })).toBeDisabled();
    await userEvent.click(screen.getByRole("button", { name: "Health Auto Export nach oben" }));
    await userEvent.click(form("Datenquellen").getByRole("button", { name: "Speichern" }));
    await screen.findAllByText("Gespeichert.");
    expect(calls(s, "PUT", "/me/settings")[0]?.body).toEqual({
      source_priority: ["manual", "hae_zip", "apple_health_xml"],
    });
  });

  it("behält unbekannte Quellnamen und sendet ohne Änderung nichts", async () => {
    const s = await open();
    await userEvent.click(form("Datenquellen").getByRole("button", { name: "Speichern" }));
    await screen.findAllByText("Gespeichert.");
    expect(calls(s, "PUT", "/me/settings")[0]?.body).toEqual({});
  });

  it("zeigt unbekannte Quellen unverändert", async () => {
    await open(settingsRoutes({ source_priority: ["manual", "waage_xyz"] }));
    expect(screen.getByText("2. waage_xyz")).toBeInTheDocument();
  });

  it("setzt die Reihenfolge zurück", async () => {
    const s = await open(settingsRoutes({ source_priority: ["hae_zip", "manual", "apple_health_xml"] }));
    await userEvent.click(form("Datenquellen").getByRole("button", { name: "Auf Standard zurücksetzen" }));
    await screen.findAllByText("Gespeichert.");
    expect(calls(s, "PUT", "/me/settings")[0]?.body).toEqual({});
    expect(screen.getByText("1. Manuell")).toBeInTheDocument();
  });
});

describe("Einstellungen: Darstellung", () => {
  it("speichert das Farbschema und setzt data-theme", async () => {
    await open();
    const select = screen.getByLabelText("Farbschema");
    await userEvent.selectOptions(select, "dark");
    expect(localStorage.getItem(THEME_KEY)).toBe("dark");
    expect(document.documentElement.dataset.theme).toBe("dark");
    await userEvent.selectOptions(select, "light");
    expect(document.documentElement.dataset.theme).toBe("light");
    await userEvent.selectOptions(select, "system");
    expect(localStorage.getItem(THEME_KEY)).toBeNull();
    expect(document.documentElement.dataset.theme).toBeUndefined();
  });

  it("wendet das gespeicherte Schema beim Öffnen an", async () => {
    localStorage.setItem(THEME_KEY, "dark");
    await open();
    expect(document.documentElement.dataset.theme).toBe("dark");
    expect(screen.getByLabelText("Farbschema")).toHaveValue("dark");
  });
});
