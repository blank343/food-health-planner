import { fireEvent, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";
import { todayIso } from "../../format";
import { type Handler, type MockServer, mockServer, renderPage } from "../../test/helpers";
import BreakfastPage from "./index";
import type { ComponentOut, MealIn, MealOut, SeedOut, TargetsOut } from "./types";

const PER100 = { kcal: 150, protein_g: 12, fat_g: 10, carb_g: 1, fiber_g: 0, salt_g: 0.3, micros: {} };

function comp(id: number, name: string, over: Partial<ComponentOut> = {}): ComponentOut {
  return {
    id,
    name,
    kind: "dairy",
    ingredient_id: 100 + id,
    ingredient_name: `Zutat ${name}`,
    min_g: 0,
    max_g: 400,
    step_g: 10,
    typical_g: 250,
    weekend_fixed: false,
    per100: PER100,
    variants: [],
    ...over,
  };
}

const EGG = comp(1, "Ei", {
  kind: "protein",
  ingredient_name: "Hühnerei",
  max_g: 360,
  step_g: 60,
  typical_g: 120,
  variants: [
    { id: 11, component_id: 1, name: "Stück", ingredient_id: 101, ingredient_name: "Hühnerei", grams_per_unit: 60, per100: PER100 },
  ],
});
const SKYR = comp(2, "Skyr");
const WEEKEND_BREAD = comp(3, "Brot (Wochenende)", { kind: "carb", weekend_fixed: true, max_g: 250, typical_g: 120 });

const TARGET = { kcal: 600, protein_g: 40, fat_g: 20, carb_g: 60 };

function targets(slots: Record<string, number> = { breakfast: 600, lunch: 0, dinner: 800, snack: 0 }): TargetsOut {
  const macro = (kcal: number) => ({ kcal, protein_g: kcal / 15, fat_g: kcal / 30, carb_g: kcal / 10 });
  return {
    date: todayIso(),
    day_type: "moderate",
    target: { kcal: 2000, protein_g: 150, fat_g: 70, carb_g: 200 },
    slots: Object.fromEntries(Object.entries(slots).map(([k, v]) => [k, macro(v)])),
    shares: {},
    tdee: { tdee_kcal: 2500, device_kcal: null, implied_kcal: null, confidence: 0.8, method: "formula", notes: [] },
    body: { weight_kg: 80, weight_date: "2026-10-01", body_fat_pct: null, lean_mass_kg: null, height_cm: 180, age_years: 35 },
    goal: { kind: "maintain", rate_kg_per_week: null, applied_rate_kg_per_week: null, valid_from: null },
    warnings: [],
  } as unknown as TargetsOut;
}

/** Baut eine Antwort aus der Anfrage: 1,5 kcal und 0,01 g Salz je Gramm. */
function mealFor(all: ComponentOut[], body: MealIn): MealOut {
  const lines = body.items.map((it) => {
    const c = all.find((x) => x.id === it.component_id)!;
    const v = c.variants.find((x) => x.id === it.variant_id);
    const grams = it.units !== undefined && it.units !== null ? it.units * (v?.grams_per_unit ?? 0) : (it.grams ?? 0);
    return {
      component_id: c.id,
      component_name: c.name,
      variant_id: v?.id ?? null,
      variant_name: v?.name ?? null,
      ingredient_id: c.ingredient_id,
      ingredient_name: c.ingredient_name,
      grams,
      units: it.units ?? null,
      nutrients: { kcal: grams * 1.5, protein_g: grams * 0.1, fat_g: grams * 0.05, carb_g: grams * 0.02, fiber_g: 0, salt_g: grams * 0.01, micros: {} },
    };
  });
  const sum = (f: (l: (typeof lines)[number]) => number) => lines.reduce((a, l) => a + f(l), 0);
  const total = {
    kcal: sum((l) => l.nutrients.kcal),
    protein_g: sum((l) => l.nutrients.protein_g),
    fat_g: sum((l) => l.nutrients.fat_g),
    carb_g: sum((l) => l.nutrients.carb_g),
    fiber_g: 0,
    salt_g: sum((l) => l.nutrients.salt_g),
    micros: {},
  };
  return {
    total,
    weight_g: sum((l) => l.grams),
    energy_density_kcal_per_100g: 150,
    satiety: { score: 64, parts: {} },
    coverage: 1,
    missing: [],
    lines,
    notes: [],
    fit: body.slot
      ? {
          slot: body.slot,
          date: body.date ?? todayIso(),
          target: TARGET,
          deviation_pct: {},
          fit_score: 82.5,
          notes: ["Protein liegt unter dem Ziel."],
          warnings: [{ code: "salt_high", severity: "warn", message: "Salz: 2,5 g liegt über dem Richtwert." }],
        }
      : null,
  };
}

type Opts = {
  components?: ComponentOut[];
  extra?: Record<string, Handler>;
  targetsHandler?: Handler;
};

function serverWith(opts: Opts = {}): MockServer {
  const all = opts.components ?? [EGG, SKYR, WEEKEND_BREAD];
  return mockServer({
    "GET /components": () => ({ body: all }),
    "GET /me/targets": opts.targetsHandler ?? { body: targets() },
    "POST /components/meal": ({ body }) => ({ body: mealFor(all, body as MealIn) }),
    ...opts.extra,
  });
}

const mealCalls = (s: MockServer) => s.calls.filter((c) => c.method === "POST" && c.path === "/components/meal");
const lastMeal = (s: MockServer) => mealCalls(s).at(-1)?.body as MealIn | undefined;
const calls = (s: MockServer, method: string, path: string) => s.calls.filter((c) => c.method === method && c.path === path);

async function openComposer() {
  await screen.findByRole("list", { name: "Komponenten wählen" });
}

describe("Frühstück: Standard-Komponenten", () => {
  it("zeigt den leeren Zustand und legt die Standard-Komponenten an", async () => {
    let list: ComponentOut[] = [];
    const seeded: SeedOut = {
      created: ["Ei", "Skyr"],
      skipped: ["Brot"],
      missing: [],
      variants_created: 1,
      missing_variants: [],
      matched: { Ei: "Hühnerei" },
    };
    const server = serverWith({
      extra: {
        "GET /components": () => ({ body: list }),
        "POST /components/seed-defaults": () => {
          list = [EGG, SKYR];
          return { body: seeded };
        },
      },
    });
    renderPage(<BreakfastPage />);
    expect(await screen.findByText(/Noch keine Komponenten: Standard-Komponenten anlegen/)).toBeInTheDocument();

    const empty = screen.getByText(/Noch keine Komponenten/).closest(".empty") as HTMLElement;
    await userEvent.click(within(empty).getByRole("button", { name: "Standard-Komponenten anlegen" }));

    const result = await screen.findByRole("region", { name: "Ergebnis: Standard-Komponenten" });
    expect(result).toHaveTextContent("2 Komponenten angelegt, 1 Varianten.");
    expect(result).toHaveTextContent("Übersprungen, weil sie schon vorhanden sind (1): Brot.");
    expect(within(result).queryByText(/fehlt noch etwas/)).not.toBeInTheDocument();
    expect(calls(server, "POST", "/components/seed-defaults")).toHaveLength(1);
    // Liste wurde neu geladen
    expect(await screen.findByRole("list", { name: "Komponenten wählen" })).toBeInTheDocument();
  });

  it("nennt fehlende Zutaten und verweist auf die Zutatenseite", async () => {
    serverWith({
      components: [],
      extra: {
        "POST /components/seed-defaults": {
          body: {
            created: ["Ei"],
            skipped: [],
            missing: ["Skyr", "Hummus"],
            variants_created: 0,
            missing_variants: ["Ei: Rührei"],
            matched: {},
          } satisfies SeedOut,
        },
      },
    });
    renderPage(<BreakfastPage />);
    const header = await screen.findByRole("heading", { name: "Frühstück" });
    await userEvent.click(within(header.closest("header")!).getByRole("button", { name: "Standard-Komponenten anlegen" }));
    const result = await screen.findByRole("region", { name: "Ergebnis: Standard-Komponenten" });
    expect(result).toHaveTextContent("Nicht gefundene Zutaten: Skyr, Hummus.");
    expect(result).toHaveTextContent("Ei: Rührei");
    expect(within(result).getByRole("link", { name: "Zutaten" })).toHaveAttribute("href", "/zutaten");
  });

  it("zeigt einen Fehler, wenn das Anlegen scheitert", async () => {
    serverWith({ components: [], extra: { "POST /components/seed-defaults": { status: 500, body: { detail: "Nicht möglich." } } } });
    renderPage(<BreakfastPage />);
    const header = await screen.findByRole("heading", { name: "Frühstück" });
    await userEvent.click(within(header.closest("header")!).getByRole("button", { name: "Standard-Komponenten anlegen" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("Nicht möglich.");
  });
});

describe("Frühstück: Rechner", () => {
  it("rechnet nichts, solange keine Komponente gewählt ist", async () => {
    const server = serverWith();
    renderPage(<BreakfastPage />);
    await openComposer();
    expect(screen.getByText(/Wähle mindestens eine Komponente/)).toBeInTheDocument();
    expect(mealCalls(server)).toHaveLength(0);
  });

  it("berechnet die Summe live, sendet Datum und Slot und hebt Salz hervor", async () => {
    const server = serverWith();
    renderPage(<BreakfastPage />);
    await openComposer();
    await userEvent.click(screen.getByLabelText("Skyr"));

    const sums = await screen.findByRole("region", { name: "Summen der Mahlzeit" });
    // 250 g × 1,5 kcal, Salz 2,5 g
    expect(within(sums).getByText("375 kcal")).toBeInTheDocument();
    expect(within(sums).getByText("2,50 g").closest(".stat")).toHaveClass("stat-salt");
    expect(within(sums).getByText("250 g")).toBeInTheDocument();
    expect(within(sums).getByText("64 von 100")).toBeInTheDocument();
    expect(within(sums).getByText("150 kcal/100 g")).toBeInTheDocument();
    expect(lastMeal(server)).toEqual({
      items: [{ component_id: 2, grams: 250 }],
      slot: "breakfast",
      date: todayIso(),
    });
  });

  it("rechnet bei geänderter Menge im Zahlenfeld neu (entprellt)", async () => {
    const server = serverWith();
    renderPage(<BreakfastPage />);
    await openComposer();
    await userEvent.click(screen.getByLabelText("Skyr"));
    await screen.findByRole("region", { name: "Summen der Mahlzeit" });
    const before = mealCalls(server).length;

    const input = screen.getByLabelText("Menge Skyr in Gramm");
    expect(input).toHaveValue(250);
    await userEvent.clear(input);
    await userEvent.type(input, "300");

    await waitFor(() => expect(lastMeal(server)?.items).toEqual([{ component_id: 2, grams: 300 }]));
    const sums = screen.getByRole("region", { name: "Summen der Mahlzeit" });
    await waitFor(() => expect(within(sums).getByText("450 kcal")).toBeInTheDocument());
    expect(within(sums).getByText("3,00 g")).toBeInTheDocument();
    // Eingabe Ziffer für Ziffer ergibt nicht eine Abfrage pro Tastendruck
    expect(mealCalls(server).length - before).toBeLessThanOrEqual(2);
  });

  it("rechnet bei Bewegung des Reglers neu und begrenzt Eingaben auf die Spanne", async () => {
    const server = serverWith();
    renderPage(<BreakfastPage />);
    await openComposer();
    await userEvent.click(screen.getByLabelText("Skyr"));
    const slider = await screen.findByLabelText("Menge Skyr (Regler)");
    expect(slider).toHaveAttribute("min", "0");
    expect(slider).toHaveAttribute("max", "400");
    expect(slider).toHaveAttribute("step", "10");
    expect(screen.getByText(/Spanne 0 bis 400 g, Schritt 10 g/)).toBeInTheDocument();

    fireEvent.change(slider, { target: { value: "120" } });
    await waitFor(() => expect(lastMeal(server)?.items).toEqual([{ component_id: 2, grams: 120 }]));
    expect(screen.getByLabelText("Menge Skyr in Gramm")).toHaveValue(120);

    const input = screen.getByLabelText("Menge Skyr in Gramm");
    await userEvent.clear(input);
    await userEvent.type(input, "900");
    await userEvent.tab();
    expect(input).toHaveValue(400);
    await waitFor(() => expect(lastMeal(server)?.items).toEqual([{ component_id: 2, grams: 400 }]));
  });

  it("rechnet bei Varianten mit Stückgewicht in Stück", async () => {
    const server = serverWith();
    renderPage(<BreakfastPage />);
    await openComposer();
    await userEvent.click(screen.getByLabelText("Ei"));
    await waitFor(() => expect(lastMeal(server)?.items).toEqual([{ component_id: 1, grams: 120 }]));

    await userEvent.selectOptions(screen.getByLabelText("Variante für Ei"), "Stück (60 g je Stück)");
    await waitFor(() => expect(lastMeal(server)?.items).toEqual([{ component_id: 1, variant_id: 11, units: 2 }]));
    expect(screen.getByText(/2 Stück = 120 g/, { selector: "small" })).toBeInTheDocument();
    const count = screen.getByLabelText("Anzahl Stück Ei");
    expect(count).toHaveValue(2);
    expect(screen.getByLabelText("Menge Ei (Regler)")).toHaveAttribute("max", "6");

    await userEvent.clear(count);
    await userEvent.type(count, "3");
    await waitFor(() => expect(lastMeal(server)?.items).toEqual([{ component_id: 1, variant_id: 11, units: 3 }]));
    const posten = (await screen.findByRole("heading", { name: "Beitrag je Komponente" })).closest("section")!;
    await waitFor(() => expect(within(posten).getByText("180 g")).toBeInTheDocument());
    expect(within(posten).getByText("3 Stück")).toBeInTheDocument();
  });

  it("belegt mit Werktag und Wochenende vor", async () => {
    serverWith();
    renderPage(<BreakfastPage />);
    await openComposer();
    await userEvent.click(screen.getByRole("button", { name: "Werktag" }));
    expect(screen.getByLabelText("Ei")).toBeChecked();
    expect(screen.getByLabelText("Skyr")).toBeChecked();
    expect(screen.getByLabelText("Brot (Wochenende)")).not.toBeChecked();

    await userEvent.click(screen.getByRole("button", { name: "Wochenende" }));
    expect(screen.getByLabelText("Ei")).not.toBeChecked();
    expect(screen.getByLabelText("Brot (Wochenende)")).toBeChecked();
    expect(screen.getByLabelText("Menge Brot (Wochenende) in Gramm")).toHaveValue(120);

    await userEvent.click(screen.getByRole("button", { name: "Alles abwählen" }));
    expect(screen.getByLabelText("Brot (Wochenende)")).not.toBeChecked();
  });

  it("zeigt die Posten-Tabelle mit dem Beitrag je Komponente", async () => {
    serverWith();
    renderPage(<BreakfastPage />);
    await openComposer();
    await userEvent.click(screen.getByRole("button", { name: "Werktag" }));
    const posten = (await screen.findByRole("heading", { name: "Beitrag je Komponente" })).closest("section")!;
    await waitFor(() => expect(within(posten).getAllByRole("row")).toHaveLength(3)); // Kopf + Ei + Skyr
    const egg = within(posten).getByRole("rowheader", { name: /^Ei/ }).closest("tr")!;
    expect(within(egg).getByText("180")).toBeInTheDocument(); // 120 g × 1,5 kcal
  });
});

describe("Frühstück: Passung zum Slot", () => {
  it("zeigt Balken je Makro, Fit-Score und Hinweise des Dienstes", async () => {
    const server = serverWith();
    renderPage(<BreakfastPage />);
    await openComposer();
    await userEvent.click(screen.getByLabelText("Skyr"));

    const heading = await screen.findByRole("heading", { name: /Passung zum Ziel: Frühstück/ });
    const card = heading.closest("section")!;
    expect(within(card).getByText("83 von 100")).toBeInTheDocument();
    // Ist 375 kcal von 600 kcal = 63 %
    const kcalBar = within(card).getByRole("progressbar", { name: "Kalorien: Anteil am Slot-Ziel" });
    expect(kcalBar).toHaveAttribute("aria-valuenow", "63");
    expect(kcalBar).toHaveAttribute("aria-valuetext", "63 % des Ziels");
    expect(within(card).getByText("375 kcal von 600 kcal (63 %)")).toBeInTheDocument();
    // Protein 25 g von 40 g
    expect(within(card).getByRole("progressbar", { name: "Protein: Anteil am Slot-Ziel" })).toHaveAttribute("aria-valuenow", "63");
    expect(within(card).getAllByRole("progressbar")).toHaveLength(4);
    expect(within(card).getByText("Salz: 2,5 g liegt über dem Richtwert.")).toBeInTheDocument();
    expect(within(card).getByText("Protein liegt unter dem Ziel.")).toBeInTheDocument();
    expect(lastMeal(server)?.slot).toBe("breakfast");
  });

  it("bietet nur Slots mit Ziel an und sendet den gewählten Slot", async () => {
    const server = serverWith();
    renderPage(<BreakfastPage />);
    await openComposer();
    const select = screen.getByLabelText("Slot");
    await waitFor(() => {
      const names = within(select).getAllByRole("option").map((o) => o.textContent);
      expect(names).toEqual(["Kein Slot (nur Summe)", "Frühstück", "Abendessen"]);
    });
    await userEvent.click(screen.getByLabelText("Skyr"));
    await userEvent.selectOptions(select, "Abendessen");
    await waitFor(() => expect(lastMeal(server)?.slot).toBe("dinner"));
    expect(await screen.findByRole("heading", { name: /Passung zum Ziel: Abendessen/ })).toBeInTheDocument();
  });

  it("fragt das Ziel für das gewählte Datum ab", async () => {
    const server = serverWith();
    renderPage(<BreakfastPage />);
    await openComposer();
    fireEvent.change(screen.getByLabelText("Datum"), { target: { value: "2026-12-24" } });
    await waitFor(() => expect(calls(server, "GET", "/me/targets?date=2026-12-24")).toHaveLength(1));
    await userEvent.click(screen.getByLabelText("Skyr"));
    await waitFor(() => expect(lastMeal(server)).toMatchObject({ date: "2026-12-24", slot: "breakfast" }));
  });

  it("zeigt ohne Slot nur die Summe", async () => {
    const server = serverWith();
    renderPage(<BreakfastPage />);
    await openComposer();
    await userEvent.selectOptions(screen.getByLabelText("Slot"), "Kein Slot (nur Summe)");
    await userEvent.click(screen.getByLabelText("Skyr"));
    await screen.findByRole("region", { name: "Summen der Mahlzeit" });
    expect(lastMeal(server)).toEqual({ items: [{ component_id: 2, grams: 250 }] });
    expect(screen.queryByRole("heading", { name: /Passung zum Ziel/ })).not.toBeInTheDocument();
    expect(screen.getByText(/Wähle einen Slot/)).toBeInTheDocument();
  });

  it("erklärt freundlich, wenn das Tagesziel nicht berechenbar ist (422), und rechnet ohne Passung weiter", async () => {
    const server = serverWith({
      targetsHandler: { status: 422, body: { detail: "Es liegt kein Gewicht vor. Bitte zuerst Gesundheitsdaten importieren." } },
    });
    renderPage(<BreakfastPage />);
    await openComposer();
    expect(await screen.findByText("Das Tagesziel kann noch nicht berechnet werden.")).toBeInTheDocument();
    expect(screen.getByText(/Es liegt kein Gewicht vor/)).toBeInTheDocument();
    await userEvent.click(screen.getByLabelText("Skyr"));
    const sums = await screen.findByRole("region", { name: "Summen der Mahlzeit" });
    expect(within(sums).getByText("375 kcal")).toBeInTheDocument();
    expect(lastMeal(server)).toEqual({ items: [{ component_id: 2, grams: 250 }] });
    expect(screen.queryByRole("heading", { name: /Passung zum Ziel/ })).not.toBeInTheDocument();
  });

  it("fällt bei 422 der Berechnung auf die Summe ohne Slot zurück und zeigt die Meldung", async () => {
    const all = [EGG, SKYR, WEEKEND_BREAD];
    const server = serverWith({
      extra: {
        "POST /components/meal": ({ body }) => {
          const b = body as MealIn;
          if (b.slot) return { status: 422, body: { detail: "Es liegt kein Gewicht vor." } };
          return { body: mealFor(all, b) };
        },
      },
    });
    renderPage(<BreakfastPage />);
    await openComposer();
    await userEvent.click(screen.getByLabelText("Skyr"));
    expect(await screen.findByText("Die Passung zum Tagesziel kann noch nicht berechnet werden.")).toBeInTheDocument();
    expect(screen.getByText(/Es liegt kein Gewicht vor./)).toBeInTheDocument();
    expect(within(screen.getByRole("region", { name: "Summen der Mahlzeit" })).getByText("375 kcal")).toBeInTheDocument();
    expect(mealCalls(server).map((c) => (c.body as MealIn).slot)).toEqual(["breakfast", undefined]);
  });

  it("zeigt andere Fehler der Berechnung als Fehler", async () => {
    serverWith({ extra: { "POST /components/meal": { status: 500, body: { detail: "Berechnung fehlgeschlagen." } } } });
    renderPage(<BreakfastPage />);
    await openComposer();
    await userEvent.click(screen.getByLabelText("Skyr"));
    expect(await screen.findByRole("alert")).toHaveTextContent("Berechnung fehlgeschlagen.");
  });

  it("zeigt Hinweise zur Mahlzeit und fehlende Nährwerte", async () => {
    const all = [EGG, SKYR, WEEKEND_BREAD];
    serverWith({
      extra: {
        "POST /components/meal": ({ body }) => ({
          body: { ...mealFor(all, body as MealIn), notes: ["Die Mahlzeit wiegt 1,4 kg."], missing: ["Marmelade"], coverage: 0.8 },
        }),
      },
    });
    renderPage(<BreakfastPage />);
    await openComposer();
    await userEvent.click(screen.getByLabelText("Skyr"));
    expect(await screen.findByText("Die Mahlzeit wiegt 1,4 kg.")).toBeInTheDocument();
    expect(screen.getByText(/Marmelade/)).toBeInTheDocument();
  });
});

describe("Frühstück: Komponenten verwalten", () => {
  async function openManager() {
    await openComposer();
    await userEvent.click(screen.getByRole("tab", { name: "Komponenten" }));
    return screen.findByRole("list", { name: "Komponenten" });
  }

  it("listet Komponenten mit Zutat, Spanne und Varianten", async () => {
    serverWith();
    renderPage(<BreakfastPage />);
    const list = await openManager();
    const egg = within(list).getByRole("heading", { name: "Ei" }).closest("li")!;
    expect(egg).toHaveTextContent("Hühnerei");
    expect(egg).toHaveTextContent("Menge: 0 bis 360 g, Schritt 60 g, üblich 120 g");
    expect(egg).toHaveTextContent("Stück");
    expect(egg).toHaveTextContent("60 g je Stück");
    const bread = within(list).getByRole("heading", { name: "Brot (Wochenende)" }).closest("li")!;
    expect(within(bread).getByText("Wochenende fest")).toBeInTheDocument();
  });

  it("behält die Auswahl im Rechner beim Wechsel der Reiter", async () => {
    serverWith();
    renderPage(<BreakfastPage />);
    await openComposer();
    await userEvent.click(screen.getByLabelText("Skyr"));
    await userEvent.click(screen.getByRole("tab", { name: "Komponenten" }));
    await screen.findByRole("list", { name: "Komponenten" });
    await userEvent.click(screen.getByRole("tab", { name: "Zusammenstellen" }));
    expect(screen.getByLabelText("Skyr")).toBeChecked();
  });

  it("legt eine Komponente an (Zutat per Suche)", async () => {
    const server = serverWith({
      extra: {
        "GET /ingredients": ({ path }) => {
          expect(path).toContain("q=h%C3%BChnerei");
          return {
            body: {
              items: [{ id: 55, name: "Hühnerei, Vollei", source: "bls" }],
              total: 1,
              limit: 10,
              offset: 0,
            },
          };
        },
        "POST /components": { status: 201, body: comp(9, "Rührei") },
      },
    });
    renderPage(<BreakfastPage />);
    await openManager();
    const header = screen.getByRole("heading", { name: "Frühstück" }).closest("header")!;
    await userEvent.click(within(header).getByRole("button", { name: "Komponente anlegen" }));

    await userEvent.type(screen.getByLabelText("Name"), "Rührei");
    await userEvent.selectOptions(screen.getByLabelText("Art"), "Eiweiß");
    await userEvent.type(screen.getByLabelText("Zutat"), "hühnerei");
    await userEvent.click(await screen.findByRole("button", { name: /Hühnerei, Vollei/ }));
    expect(screen.getByText("Hühnerei, Vollei")).toBeInTheDocument();

    const max = screen.getByLabelText("Höchstmenge (g)");
    await userEvent.clear(max);
    await userEvent.type(max, "360");
    const step = screen.getByLabelText("Schritt (g)");
    await userEvent.clear(step);
    await userEvent.type(step, "60");
    await userEvent.type(screen.getByLabelText("Übliche Menge (g)"), "120");
    await userEvent.click(screen.getByLabelText("Wochenende fest"));
    await userEvent.click(screen.getByRole("button", { name: "Anlegen" }));

    await waitFor(() => expect(calls(server, "POST", "/components")).toHaveLength(1));
    expect(calls(server, "POST", "/components")[0]?.body).toEqual({
      name: "Rührei",
      kind: "protein",
      ingredient_id: 55,
      min_g: 0,
      max_g: 360,
      step_g: 60,
      typical_g: 120,
      weekend_fixed: true,
    });
    await waitFor(() => expect(screen.queryByRole("button", { name: "Anlegen" })).not.toBeInTheDocument());
  });

  it("prüft das Formular vor dem Senden", async () => {
    const server = serverWith();
    renderPage(<BreakfastPage />);
    await openManager();
    await userEvent.click(screen.getByRole("button", { name: "Komponente anlegen" }));
    await userEvent.type(screen.getByLabelText("Name"), "Test");
    await userEvent.click(screen.getByRole("button", { name: "Anlegen" }));
    expect(await screen.findByText("Bitte die Art der Komponente wählen.")).toBeInTheDocument();
    await userEvent.selectOptions(screen.getByLabelText("Art"), "Obst");
    await userEvent.click(screen.getByRole("button", { name: "Anlegen" }));
    expect((await screen.findAllByText("Bitte eine Zutat wählen.")).length).toBeGreaterThan(0);
    expect(calls(server, "POST", "/components")).toHaveLength(0);
  });

  it("bearbeitet eine Komponente", async () => {
    const server = serverWith({
      extra: { "PATCH /components/2": ({ body }) => ({ body: { ...SKYR, ...(body as object) } }) },
    });
    renderPage(<BreakfastPage />);
    await openManager();
    await userEvent.click(screen.getByRole("button", { name: "Skyr bearbeiten" }));
    const name = screen.getByLabelText("Name");
    expect(name).toHaveValue("Skyr");
    expect(within(screen.getByRole("form", { name: "Komponente bearbeiten" })).getByText("Zutat Skyr")).toBeInTheDocument();
    await userEvent.clear(name);
    await userEvent.type(name, "Skyr natur");
    const typical = screen.getByLabelText("Übliche Menge (g)");
    await userEvent.clear(typical);
    await userEvent.click(screen.getByRole("button", { name: "Speichern" }));
    await waitFor(() => expect(calls(server, "PATCH", "/components/2")).toHaveLength(1));
    expect(calls(server, "PATCH", "/components/2")[0]?.body).toMatchObject({
      name: "Skyr natur",
      ingredient_id: 102,
      typical_g: null,
      min_g: 0,
      max_g: 400,
    });
  });

  it("löscht eine Komponente nach Bestätigung und zeigt den Konflikt (409)", async () => {
    let attempt = 0;
    const server = serverWith({
      extra: {
        "DELETE /components/2": () => {
          attempt += 1;
          return attempt === 1
            ? { status: 409, body: { detail: "Die Komponente wird noch verwendet." } }
            : { status: 204 };
        },
      },
    });
    renderPage(<BreakfastPage />);
    await openManager();
    await userEvent.click(screen.getByRole("button", { name: "Skyr löschen" }));
    expect(screen.getByRole("alertdialog")).toHaveTextContent("„Skyr“ wirklich löschen?");
    await userEvent.click(screen.getByRole("button", { name: "Ja, löschen" }));
    expect(await screen.findByRole("alertdialog")).toHaveTextContent("Die Komponente wird noch verwendet.");
    await userEvent.click(screen.getByRole("button", { name: "Ja, löschen" }));
    await waitFor(() => expect(calls(server, "DELETE", "/components/2")).toHaveLength(2));
    await waitFor(() => expect(screen.queryByRole("alertdialog")).not.toBeInTheDocument());
  });

  it("legt eine Variante an", async () => {
    const server = serverWith({
      extra: {
        "POST /components/2/variants": {
          status: 201,
          body: { id: 21, component_id: 2, name: "Becher", ingredient_id: 102, ingredient_name: "Zutat Skyr", grams_per_unit: 150, per100: PER100 },
        },
      },
    });
    renderPage(<BreakfastPage />);
    await openManager();
    await userEvent.click(screen.getByRole("button", { name: "Variante für Skyr hinzufügen" }));
    await userEvent.type(screen.getByLabelText("Name der Variante"), "Becher");
    await userEvent.type(screen.getByLabelText("Gramm je Einheit (g)"), "150");
    await userEvent.click(screen.getByRole("button", { name: "Anlegen" }));
    await waitFor(() => expect(calls(server, "POST", "/components/2/variants")).toHaveLength(1));
    expect(calls(server, "POST", "/components/2/variants")[0]?.body).toEqual({ name: "Becher", grams_per_unit: 150 });
  });

  it("bearbeitet und löscht eine Variante", async () => {
    const server = serverWith({
      extra: {
        "PATCH /components/1/variants/11": { body: EGG.variants[0] },
        "DELETE /components/1/variants/11": { status: 204 },
      },
    });
    renderPage(<BreakfastPage />);
    await openManager();
    await userEvent.click(screen.getByRole("button", { name: "Variante Stück von Ei bearbeiten" }));
    const gpu = screen.getByLabelText("Gramm je Einheit (g)");
    expect(gpu).toHaveValue(60);
    await userEvent.clear(gpu);
    await userEvent.type(gpu, "55");
    await userEvent.click(screen.getByRole("button", { name: "Speichern" }));
    await waitFor(() => expect(calls(server, "PATCH", "/components/1/variants/11")).toHaveLength(1));
    expect(calls(server, "PATCH", "/components/1/variants/11")[0]?.body).toMatchObject({ name: "Stück", ingredient_id: 101, grams_per_unit: 55 });

    await userEvent.click(await screen.findByRole("button", { name: "Variante Stück von Ei löschen" }));
    expect(screen.getByRole("alertdialog")).toHaveTextContent("„Stück (Ei)“ wirklich löschen?");
    await userEvent.click(screen.getByRole("button", { name: "Ja, löschen" }));
    await waitFor(() => expect(calls(server, "DELETE", "/components/1/variants/11")).toHaveLength(1));
  });

  it("zeigt im Fehlerfall eine Meldung statt der Liste", async () => {
    serverWith({ extra: { "GET /components": { status: 500, body: { detail: "Datenbank nicht erreichbar." } } } });
    renderPage(<BreakfastPage />);
    expect(await screen.findByRole("alert")).toHaveTextContent("Datenbank nicht erreichbar.");
  });
});
