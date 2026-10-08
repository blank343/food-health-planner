import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";
import { type MockResponse, mockServer, renderPage } from "../../test/helpers";
import IngredientsPage from "./index";
import type { IngredientDetail, IngredientOut, PreferenceOut } from "./labels";

const NUT = {
  kcal: 63,
  protein_g: 11,
  fat_g: 0.2,
  carb_g: 4,
  fiber_g: 0,
  salt_g: 0.1,
  micros: { zinc_mg: 0.5, iron_mg: 0.1, potassium_mg: 150, calcium_mg: 120, iodine_ug: 12, vit_d_ug: 0 },
};

function ing(id: number, name: string, over: Partial<IngredientOut> = {}): IngredientOut {
  return {
    id,
    name,
    category: "Milchprodukte",
    source: "bls",
    source_code: `B${id}`,
    nutrients: NUT,
    density_g_per_ml: null,
    piece_g: null,
    is_fish: false,
    is_potassium_salt: false,
    shelf_days: null,
    hidden: false,
    ...over,
  };
}

const detail = (i: IngredientOut, synonyms: string[] = []): IngredientDetail => ({ ...i, synonyms });

const SKYR = ing(1, "Skyr natur");
const MY_MUESLI = ing(7, "Mein Müsli", { source: "manual", source_code: null, category: null });

function query(path: string) {
  return new URL(`http://x${path}`).searchParams;
}

/** Server mit Suche (seitenweise), Detail, Vorlieben und Synonymen; Zustand lebt in den Variablen. */
function serverWith(opts: { items?: IngredientOut[]; prefs?: PreferenceOut[]; extra?: Record<string, MockResponse | ((r: { method: string; path: string; body: unknown }) => MockResponse)> } = {}) {
  const items = opts.items ?? [SKYR, MY_MUESLI];
  let prefs = [...(opts.prefs ?? [])];
  const synonyms: Record<number, string[]> = {};
  return mockServer({
    "GET /ingredients": ({ path }) => {
      const p = query(path);
      const q = (p.get("q") ?? "").toLowerCase();
      const source = p.get("source");
      const limit = Number(p.get("limit") ?? 25);
      const offset = Number(p.get("offset") ?? 0);
      const all = items.filter((i) => i.name.toLowerCase().includes(q) && (!source || i.source === source));
      return { body: { items: all.slice(offset, offset + limit), total: all.length, limit, offset } };
    },
    "GET /me/ingredient-preferences": ({ path }) => {
      const level = query(path).get("level");
      return { body: prefs.filter((x) => !level || x.level === level) };
    },
    ...Object.fromEntries(
      items.flatMap((i) => [
        [`GET /ingredients/${i.id}`, () => ({ body: detail(i, synonyms[i.id] ?? []) })],
        [
          `PUT /me/ingredient-preferences/${i.id}`,
          ({ body }: { body: unknown }) => {
            const level = (body as { level: string }).level;
            prefs = [...prefs.filter((x) => x.ingredient_id !== i.id), { ingredient_id: i.id, ingredient_name: i.name, level }];
            return { body: prefs.find((x) => x.ingredient_id === i.id) };
          },
        ],
        [
          `DELETE /me/ingredient-preferences/${i.id}`,
          () => {
            prefs = prefs.filter((x) => x.ingredient_id !== i.id);
            return { status: 204 };
          },
        ],
        [
          `POST /ingredients/${i.id}/synonyms`,
          ({ body }: { body: unknown }) => {
            synonyms[i.id] = [...(synonyms[i.id] ?? []), (body as { alias: string }).alias];
            return { status: 201, body: detail(i, synonyms[i.id]) };
          },
        ],
        [
          `DELETE /ingredients/${i.id}/synonyms/quark`,
          () => {
            synonyms[i.id] = (synonyms[i.id] ?? []).filter((s) => s !== "quark");
            return { status: 204 };
          },
        ],
      ]),
    ),
    ...opts.extra,
  });
}

const callsTo = (server: ReturnType<typeof mockServer>, method: string, prefix: string) =>
  server.calls.filter((c) => c.method === method && c.path.startsWith(prefix));

describe("Zutaten: Katalog", () => {
  it("zeigt Treffer mit Nährwerten je 100 g und der Quelle", async () => {
    serverWith();
    renderPage(<IngredientsPage />);
    const list = await screen.findByRole("list", { name: "Zutaten" });
    expect(within(list).getByRole("button", { name: "Skyr natur" })).toBeInTheDocument();
    const grid = within(list).getByLabelText("Nährwerte je 100 g: Skyr natur");
    expect(within(grid).getByText("63")).toBeInTheDocument();
    expect(within(grid).getByText("11,0 g")).toBeInTheDocument();
    expect(within(grid).getByText("0,10 g")).toBeInTheDocument();
    expect(screen.getByText("2 von 2 Zutaten angezeigt.")).toBeInTheDocument();
  });

  it("sucht entprellt und filtert nach Quelle", async () => {
    const server = serverWith();
    renderPage(<IngredientsPage />);
    await screen.findByRole("list", { name: "Zutaten" });

    await userEvent.type(screen.getByLabelText("Zutat suchen"), "müs");
    await waitFor(() => expect(screen.queryByRole("button", { name: "Skyr natur" })).not.toBeInTheDocument());
    expect(await screen.findByRole("button", { name: "Mein Müsli" })).toBeInTheDocument();
    const searched = callsTo(server, "GET", "/ingredients?").map((c) => query(c.path).get("q"));
    expect(searched).toContain("müs");
    // nicht bei jedem Tastendruck eine Abfrage
    expect(searched.filter((q) => q === "m" || q === "mü")).toHaveLength(0);

    await userEvent.clear(screen.getByLabelText("Zutat suchen"));
    await userEvent.selectOptions(screen.getByLabelText("Quelle"), "BLS");
    await waitFor(() => expect(screen.queryByRole("button", { name: "Mein Müsli" })).not.toBeInTheDocument());
    expect(await screen.findByRole("button", { name: "Skyr natur" })).toBeInTheDocument();
    expect(callsTo(server, "GET", "/ingredients?").some((c) => query(c.path).get("source") === "bls")).toBe(true);
  });

  it("lädt weitere Seiten nach", async () => {
    const many = Array.from({ length: 30 }, (_, i) => ing(100 + i, `Zutat ${String(i + 1).padStart(2, "0")}`));
    const server = serverWith({ items: many });
    renderPage(<IngredientsPage />);
    expect(await screen.findByText("25 von 30 Zutaten angezeigt.")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Zutat 30" })).not.toBeInTheDocument();

    await userEvent.click(screen.getByRole("button", { name: "Mehr laden" }));
    expect(await screen.findByText("30 von 30 Zutaten angezeigt.")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Zutat 30" })).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Mehr laden" })).not.toBeInTheDocument();
    expect(callsTo(server, "GET", "/ingredients?").map((c) => query(c.path).get("offset"))).toEqual(["0", "25"]);
  });

  it("zeigt einen leeren Zustand und Fehler", async () => {
    serverWith({ items: [] });
    renderPage(<IngredientsPage />);
    expect(await screen.findByText(/Noch keine Zutaten im Katalog/)).toBeInTheDocument();
  });

  it("zeigt einen Fehler der Suche", async () => {
    serverWith({ extra: { "GET /ingredients": { status: 500, body: { detail: "Kaputt." } } } });
    renderPage(<IngredientsPage />);
    expect(await screen.findByRole("alert")).toHaveTextContent("Kaputt.");
  });
});

describe("Zutaten: Detail", () => {
  it("zeigt alle Nährwerte inklusive Mikros und Synonymen", async () => {
    serverWith();
    renderPage(<IngredientsPage />);
    await userEvent.click(await screen.findByRole("button", { name: "Skyr natur" }));
    expect(await screen.findByRole("heading", { name: "Skyr natur" })).toBeInTheDocument();
    const card = screen.getByRole("heading", { name: "Nährwerte je 100 g" }).closest("section")!;
    for (const label of ["Zink (mg)", "Eisen (mg)", "Kalium (mg)", "Calcium (mg)", "Jod (µg)", "Vitamin D (µg)"]) {
      expect(within(card).getByRole("rowheader", { name: label })).toBeInTheDocument();
    }
    expect(within(card).getByRole("rowheader", { name: "Kalium (mg)" }).nextElementSibling).toHaveTextContent("150");
    expect(screen.getByText("Noch keine Synonyme.")).toBeInTheDocument();
  });

  it("leitet Salz aus Natrium ab, wenn kein Salzwert vorliegt", async () => {
    const noSalt = ing(3, "Salzlos", { nutrients: { ...NUT, salt_g: null, micros: { sodium_mg: 400 } } });
    serverWith({ items: [noSalt] });
    renderPage(<IngredientsPage />);
    await userEvent.click(await screen.findByRole("button", { name: "Salzlos" }));
    const row = await screen.findByRole("rowheader", { name: "Salz (aus Natrium)" });
    expect(row.nextElementSibling).toHaveTextContent("1,00 g");
  });

  it("fügt ein Synonym hinzu und entfernt es wieder", async () => {
    const server = serverWith();
    renderPage(<IngredientsPage />);
    await userEvent.click(await screen.findByRole("button", { name: "Skyr natur" }));
    await userEvent.type(await screen.findByLabelText("Neues Synonym"), "quark");
    await userEvent.click(screen.getByRole("button", { name: "Hinzufügen" }));

    const chips = await screen.findByRole("list", { name: "Synonyme" });
    expect(within(chips).getByText("quark")).toBeInTheDocument();
    expect(callsTo(server, "POST", "/ingredients/1/synonyms")[0]?.body).toEqual({ alias: "quark" });
    expect(screen.getByLabelText("Neues Synonym")).toHaveValue("");

    await userEvent.click(screen.getByRole("button", { name: "Synonym „quark“ entfernen" }));
    await waitFor(() => expect(screen.getByText("Noch keine Synonyme.")).toBeInTheDocument());
    expect(callsTo(server, "DELETE", "/ingredients/1/synonyms/quark")).toHaveLength(1);
  });

  it("zeigt den Fehler beim Hinzufügen eines vergebenen Synonyms", async () => {
    serverWith({
      extra: { "POST /ingredients/1/synonyms": { status: 409, body: { detail: "Das Synonym gehört schon zu einer anderen Zutat." } } },
    });
    renderPage(<IngredientsPage />);
    await userEvent.click(await screen.findByRole("button", { name: "Skyr natur" }));
    await userEvent.type(await screen.findByLabelText("Neues Synonym"), "quark");
    await userEvent.click(screen.getByRole("button", { name: "Hinzufügen" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("gehört schon zu einer anderen Zutat");
  });

  it("speichert Einstellungen einer BLS-Zutat (Kaliumsalz, Stückgewicht)", async () => {
    const server = serverWith({
      extra: { "PATCH /ingredients/1": ({ body }) => ({ body: detail({ ...SKYR, ...(body as object) } as IngredientOut) }) },
    });
    renderPage(<IngredientsPage />);
    await userEvent.click(await screen.findByRole("button", { name: "Skyr natur" }));
    await userEvent.click(await screen.findByRole("button", { name: "Einstellungen ändern" }));
    expect(screen.getByText(/Name und Nährwerte importierter Zutaten lassen sich nicht ändern/)).toBeInTheDocument();
    expect(screen.queryByLabelText("Name")).not.toBeInTheDocument();

    await userEvent.click(screen.getByLabelText("Kaliumsalz (Salzersatz)"));
    await userEvent.type(screen.getByLabelText("Stückgewicht (g)"), "150");
    await userEvent.click(screen.getByRole("button", { name: "Speichern" }));

    await waitFor(() => expect(callsTo(server, "PATCH", "/ingredients/1")).toHaveLength(1));
    expect(callsTo(server, "PATCH", "/ingredients/1")[0]?.body).toEqual({
      hidden: false,
      is_potassium_salt: true,
      density_g_per_ml: null,
      piece_g: 150,
      shelf_days: null,
    });
    await waitFor(() => expect(screen.queryByRole("button", { name: "Speichern" })).not.toBeInTheDocument());
  });

  it("bietet bei BLS-Zutaten kein Löschen an", async () => {
    serverWith();
    renderPage(<IngredientsPage />);
    await userEvent.click(await screen.findByRole("button", { name: "Skyr natur" }));
    await screen.findByRole("button", { name: "Einstellungen ändern" });
    expect(screen.queryByRole("button", { name: "Löschen" })).not.toBeInTheDocument();
  });

  it("bearbeitet eine manuelle Zutat vollständig", async () => {
    const server = serverWith({
      extra: { "PATCH /ingredients/7": ({ body }) => ({ body: detail({ ...MY_MUESLI, name: (body as { name: string }).name }) }) },
    });
    renderPage(<IngredientsPage />);
    await userEvent.click(await screen.findByRole("button", { name: "Mein Müsli" }));
    await userEvent.click(await screen.findByRole("button", { name: "Bearbeiten" }));
    const name = screen.getByLabelText("Name");
    expect(name).toHaveValue("Mein Müsli");
    await userEvent.clear(name);
    await userEvent.type(name, "Müsli ohne Zucker");
    await userEvent.click(screen.getByRole("button", { name: "Speichern" }));
    await waitFor(() => expect(callsTo(server, "PATCH", "/ingredients/7")).toHaveLength(1));
    const body = callsTo(server, "PATCH", "/ingredients/7")[0]?.body as Record<string, unknown>;
    expect(body.name).toBe("Müsli ohne Zucker");
    expect(body.kcal_100).toBe(63);
    expect(body.micros).toMatchObject({ zinc_mg: 0.5 });
  });
});

describe("Zutaten: anlegen und löschen", () => {
  it("legt eine manuelle Zutat an und öffnet sie", async () => {
    const created = detail(ing(99, "Lidl Skyr", { source: "manual", source_code: null }));
    const server = serverWith({
      extra: {
        "POST /ingredients": { status: 201, body: created },
        "GET /ingredients/99": { body: created },
      },
    });
    renderPage(<IngredientsPage />);
    await screen.findByRole("list", { name: "Zutaten" });
    await userEvent.click(screen.getByRole("button", { name: "Zutat anlegen" }));

    await userEvent.type(screen.getByLabelText("Name"), "Lidl Skyr");
    await userEvent.type(screen.getByLabelText("Kategorie"), "Milchprodukte");
    await userEvent.type(screen.getByLabelText("Kalorien (kcal)"), "63");
    await userEvent.type(screen.getByLabelText("Protein (g)"), "11.5");
    await userEvent.type(screen.getByLabelText("Salz (g)"), "0.1");
    await userEvent.type(screen.getByLabelText("Stückgewicht (g)"), "150");
    await userEvent.click(screen.getByRole("button", { name: "Anlegen" }));

    expect(await screen.findByRole("heading", { name: "Lidl Skyr" })).toBeInTheDocument();
    const body = callsTo(server, "POST", "/ingredients")[0]?.body as Record<string, unknown>;
    expect(body).toMatchObject({
      name: "Lidl Skyr",
      category: "Milchprodukte",
      kcal_100: 63,
      protein_100: 11.5,
      fat_100: null,
      salt_100: 0.1,
      piece_g: 150,
      density_g_per_ml: null,
      is_potassium_salt: false,
    });
  });

  it("prüft Pflichtfelder vor dem Senden", async () => {
    const server = serverWith();
    renderPage(<IngredientsPage />);
    await screen.findByRole("list", { name: "Zutaten" });
    await userEvent.click(screen.getByRole("button", { name: "Zutat anlegen" }));
    await userEvent.click(screen.getByRole("button", { name: "Anlegen" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("Bitte einen Namen angeben.");
    expect(callsTo(server, "POST", "/ingredients")).toHaveLength(0);
  });

  it("zeigt die Serverantwort, wenn der Name schon vergeben ist", async () => {
    serverWith({
      extra: { "POST /ingredients": { status: 409, body: { detail: "Eine eigene Zutat mit diesem Namen gibt es schon." } } },
    });
    renderPage(<IngredientsPage />);
    await screen.findByRole("list", { name: "Zutaten" });
    await userEvent.click(screen.getByRole("button", { name: "Zutat anlegen" }));
    await userEvent.type(screen.getByLabelText("Name"), "Mein Müsli");
    await userEvent.click(screen.getByRole("button", { name: "Anlegen" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("gibt es schon");
  });

  it("löscht eine manuelle Zutat nach Bestätigung", async () => {
    const server = serverWith({ extra: { "DELETE /ingredients/7": { status: 204 } } });
    renderPage(<IngredientsPage />);
    await userEvent.click(await screen.findByRole("button", { name: "Mein Müsli" }));
    await userEvent.click(await screen.findByRole("button", { name: "Löschen" }));
    expect(screen.getByRole("alertdialog")).toHaveTextContent("„Mein Müsli“ wirklich löschen?");
    expect(callsTo(server, "DELETE", "/ingredients/7")).toHaveLength(0);
    await userEvent.click(screen.getByRole("button", { name: "Ja, löschen" }));
    await waitFor(() => expect(callsTo(server, "DELETE", "/ingredients/7")).toHaveLength(1));
    expect(await screen.findByRole("list", { name: "Zutaten" })).toBeInTheDocument();
  });

  it("erklärt den Konflikt, wenn die Zutat noch verwendet wird (409)", async () => {
    serverWith({
      extra: {
        "DELETE /ingredients/7": {
          status: 409,
          body: { detail: "Die Zutat wird noch in Rezepten oder im Baukasten verwendet und kann nicht gelöscht werden." },
        },
      },
    });
    renderPage(<IngredientsPage />);
    await userEvent.click(await screen.findByRole("button", { name: "Mein Müsli" }));
    await userEvent.click(await screen.findByRole("button", { name: "Löschen" }));
    await userEvent.click(screen.getByRole("button", { name: "Ja, löschen" }));
    expect(await screen.findByRole("alertdialog")).toHaveTextContent("noch in Rezepten oder im Baukasten verwendet");
    expect(screen.getByRole("heading", { name: "Mein Müsli" })).toBeInTheDocument();
  });
});

describe("Zutaten: Meine Vorlieben", () => {
  it("setzt, ändert und entfernt die Vorliebe in der Detailansicht", async () => {
    const server = serverWith();
    renderPage(<IngredientsPage />);
    await userEvent.click(await screen.findByRole("button", { name: "Skyr natur" }));
    const group = await screen.findByRole("group", { name: "Vorliebe für Skyr natur" });
    expect(within(group).getByRole("radio", { name: "Keine Angabe" })).toBeChecked();
    expect(screen.getByText(/„Nie“ ist eine harte Grenze/)).toBeInTheDocument();

    await userEvent.click(within(group).getByRole("radio", { name: "Nie" }));
    await waitFor(() => expect(within(group).getByRole("radio", { name: "Nie" })).toBeChecked());
    expect(callsTo(server, "PUT", "/me/ingredient-preferences/1")[0]?.body).toEqual({ level: "never" });
    expect(screen.getByText(/Der Planer verwendet diese Zutat später nie/)).toBeInTheDocument();

    await userEvent.click(within(group).getByRole("radio", { name: "Mag ich nicht" }));
    await waitFor(() => expect(callsTo(server, "PUT", "/me/ingredient-preferences/1")).toHaveLength(2));
    expect(callsTo(server, "PUT", "/me/ingredient-preferences/1")[1]?.body).toEqual({ level: "dislike" });

    await userEvent.click(within(group).getByRole("radio", { name: "Keine Angabe" }));
    await waitFor(() => expect(callsTo(server, "DELETE", "/me/ingredient-preferences/1")).toHaveLength(1));
    await waitFor(() => expect(within(group).getByRole("radio", { name: "Keine Angabe" })).toBeChecked());
  });

  it("zeigt die Vorliebe als Marke in der Trefferliste", async () => {
    serverWith({ prefs: [{ ingredient_id: 1, ingredient_name: "Skyr natur", level: "like" }] });
    renderPage(<IngredientsPage />);
    const list = await screen.findByRole("list", { name: "Zutaten" });
    await waitFor(() => expect(within(list).getByText("Mag ich")).toBeInTheDocument());
  });

  it("listet die Vorlieben und filtert nach Stufe", async () => {
    const server = serverWith({
      prefs: [
        { ingredient_id: 1, ingredient_name: "Skyr natur", level: "like" },
        { ingredient_id: 7, ingredient_name: "Mein Müsli", level: "never" },
      ],
    });
    renderPage(<IngredientsPage />);
    await userEvent.click(await screen.findByRole("tab", { name: "Meine Vorlieben" }));
    const list = await screen.findByRole("list", { name: "Meine Vorlieben" });
    expect(within(list).getAllByRole("listitem")).toHaveLength(2);
    expect(screen.getByText(/„Nie“ ist eine harte Grenze/)).toBeInTheDocument();

    await userEvent.selectOptions(screen.getByLabelText("Nach Stufe filtern"), "Nie");
    await waitFor(() => expect(within(screen.getByRole("list", { name: "Meine Vorlieben" })).getAllByRole("listitem")).toHaveLength(1));
    expect(screen.getByRole("button", { name: "Mein Müsli" })).toBeInTheDocument();
    expect(callsTo(server, "GET", "/me/ingredient-preferences?level=never")).toHaveLength(1);
  });

  it("entfernt eine Vorliebe aus der Übersicht", async () => {
    const server = serverWith({ prefs: [{ ingredient_id: 1, ingredient_name: "Skyr natur", level: "dislike" }] });
    renderPage(<IngredientsPage />);
    await userEvent.click(await screen.findByRole("tab", { name: "Meine Vorlieben" }));
    await userEvent.click(await screen.findByRole("button", { name: "Vorliebe für Skyr natur entfernen" }));
    await waitFor(() => expect(callsTo(server, "DELETE", "/me/ingredient-preferences/1")).toHaveLength(1));
    expect(await screen.findByText(/Noch keine Vorlieben/)).toBeInTheDocument();
  });

  it("öffnet eine Zutat aus der Übersicht", async () => {
    serverWith({ prefs: [{ ingredient_id: 1, ingredient_name: "Skyr natur", level: "like" }] });
    renderPage(<IngredientsPage />);
    await userEvent.click(await screen.findByRole("tab", { name: "Meine Vorlieben" }));
    await userEvent.click(await screen.findByRole("button", { name: "Skyr natur" }));
    expect(await screen.findByRole("heading", { name: "Nährwerte je 100 g" })).toBeInTheDocument();
    const group = screen.getByRole("group", { name: "Vorliebe für Skyr natur" });
    await waitFor(() => expect(within(group).getByRole("radio", { name: "Mag ich" })).toBeChecked());
  });
});
