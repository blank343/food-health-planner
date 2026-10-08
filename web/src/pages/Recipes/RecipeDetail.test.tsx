import { fireEvent, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { mockServer, renderPage } from "../../test/helpers";
import { NO_TARGETS, TODAY, card, detail, fit, line, list, targets } from "./fixtures";
import RecipesPage from "./index";
import { buildLines } from "./RecipeForm";
import type { RecipeDetail } from "./types";

beforeEach(() => {
  vi.useFakeTimers({ toFake: ["Date"] });
  vi.setSystemTime(new Date(2026, 9, 6, 12, 0, 0));
});
afterEach(() => vi.useRealTimers());

const ROUTE = { route: "/?rezept=7" };

function serverFor(recipe: () => RecipeDetail, extra: Parameters<typeof mockServer>[0] = {}) {
  return mockServer({
    "GET /me/targets": { body: targets() },
    "GET /recipes/7": () => ({ body: recipe() }),
    "GET /recipes": { body: list([card()]) },
    "GET /ingredients": { body: { items: [], total: 0, limit: 8, offset: 0 } },
    ...extra,
  });
}

describe("Rezeptdetail", () => {
  it("lädt das Rezept mit dem gewählten Slot (fit_slot, fit_date)", async () => {
    const server = serverFor(() => detail());
    renderPage(<RecipesPage />, ROUTE);
    expect(await screen.findByRole("heading", { level: 1, name: "Hafer-Bowl" })).toBeInTheDocument();
    expect(server.calls.find((c) => c.path.startsWith("/recipes/7"))?.path).toBe(`/recipes/7?fit_slot=lunch&fit_date=${TODAY}`);
  });

  it("zeigt Quelle, Zeiten, Portionen, Anleitung und Bewertungen beider Personen", async () => {
    serverFor(() => detail());
    renderPage(<RecipesPage />, ROUTE);
    await screen.findByRole("heading", { level: 1, name: "Hafer-Bowl" });
    expect(screen.getByRole("link", { name: "beispiel.de" })).toHaveAttribute("href", "https://beispiel.de/hafer-bowl");
    expect(screen.getByRole("link", { name: "beispiel.de" })).toHaveAttribute("rel", "noopener noreferrer");
    expect(screen.getByText(/2 Portionen · Zeit 45 Min\. \(10 Min\. Vorbereitung, 35 Min\. Kochen\)/)).toBeInTheDocument();
    expect(screen.getByText(/Haferflocken kochen\./)).toBeInTheDocument();
    const ratings = screen.getByRole("list", { name: "Bewertungen" });
    expect(within(ratings).getByText("Test A: 4 von 5 Sternen")).toBeInTheDocument();
    expect(within(ratings).getByText("Test B: 2 von 5 Sternen")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "← Alle Rezepte" })).toHaveAttribute("href", "/");
  });

  it("zeigt Nährwerte je Portion und gesamt, wichtige Mikros und die Datenabdeckung", async () => {
    serverFor(() => detail());
    renderPage(<RecipesPage />, ROUTE);
    const card_ = (await screen.findByRole("heading", { name: "Nährwerte" })).closest("section")!;
    const row = (name: string) => within(card_).getByRole("row", { name: new RegExp(`^${name}`) });
    expect(within(row("Kalorien")).getAllByRole("cell").map((c) => c.textContent)).toEqual(["900 kcal", "1.200 kcal"]);
    expect(within(row("Protein")).getAllByRole("cell").map((c) => c.textContent)).toEqual(["54,0 g", "72,0 g"]);
    expect(within(row("Salz")).getAllByRole("cell").map((c) => c.textContent)).toEqual(["0,90 g", "1,20 g"]);
    expect(within(row("Zink")).getAllByRole("cell").map((c) => c.textContent)).toEqual(["4,5 mg", "6,0 mg"]);
    expect(within(card_).getByRole("row", { name: /^Eisen/ })).toBeInTheDocument();
    expect(within(card_).getByRole("row", { name: /^Kalium/ })).toBeInTheDocument();
    expect(within(card_).getByRole("row", { name: /^Magnesium/ })).toBeInTheDocument();
    expect(within(card_).getByText(/Datenabdeckung 83 %/)).toBeInTheDocument();
    expect(within(card_).getByText(/Es fehlen: 1 Prise Zimt/)).toBeInTheDocument();
  });

  it("zeigt die Sättigung mit Teilwerten", async () => {
    serverFor(() => detail());
    renderPage(<RecipesPage />, ROUTE);
    const section = (await screen.findByRole("heading", { name: "Sättigung" })).closest("section")!;
    expect(within(section).getByText("Sättigung 72 von 100 (hoch)")).toBeInTheDocument();
    const parts = within(section).getByRole("list", { name: "Teilwerte der Sättigung" });
    expect(within(parts).getByText("Energiedichte (niedrig ist gut)")).toBeInTheDocument();
    expect(within(parts).getByText("80 %")).toBeInTheDocument();
    expect(within(parts).getByRole("progressbar", { name: "Warm serviert" })).toHaveAttribute("aria-valuenow", "0");
  });

  it("zeigt den Fit-Block mit Balken, Abweichung und Hinweisen des Dienstes", async () => {
    serverFor(() => detail());
    renderPage(<RecipesPage />, ROUTE);
    const section = (await screen.findByRole("heading", { name: "Passt ins Tagesziel: Mittagessen" })).closest("section")!;
    expect(within(section).getByText("Passung 87 von 100: sehr gut")).toBeInTheDocument();
    expect(within(section).getByText("1,5-fache Portion")).toBeInTheDocument();
    expect(within(section).getByRole("meter", { name: "Protein: 90 % des Ziels" })).toBeInTheDocument();
    expect(within(section).getByRole("meter", { name: "Kohlenhydrate: 120 % des Ziels" })).toBeInTheDocument();
    expect(within(section).getByText("Protein 6 g unter Ziel.")).toBeInTheDocument();
    expect(within(section).getByText(/06\.10\.2026/)).toBeInTheDocument();
  });

  it("zeigt ohne Tagesziel (422) den Hinweis, aber weiterhin das Rezept", async () => {
    mockServer({
      "GET /me/targets": NO_TARGETS,
      "GET /recipes/7": { body: detail({ fit: null, fit_score: null, fit_factor: null }) },
    });
    renderPage(<RecipesPage />, ROUTE);
    expect(await screen.findByRole("heading", { level: 1, name: "Hafer-Bowl" })).toBeInTheDocument();
    expect(screen.getByText("Das Tagesziel kann noch nicht berechnet werden.")).toBeInTheDocument();
    expect(screen.queryByText(/Passt ins Tagesziel:/)).not.toBeInTheDocument();
    // Portionsregler arbeitet mit Faktor 1
    expect(screen.getByLabelText("Portionsfaktor")).toHaveValue("1");
  });

  it("markiert nicht zugeordnete Zeilen und weist darauf hin", async () => {
    serverFor(() => detail({ status: "needs_review" }));
    renderPage(<RecipesPage />, ROUTE);
    const section = (await screen.findByRole("heading", { name: "Zutaten" })).closest("section")!;
    const rows = within(section).getAllByRole("row");
    const zimt = rows.find((r) => within(r).queryByText("1 Prise Zimt"))!;
    expect(zimt).toHaveClass("rc-unassigned");
    expect(within(zimt).getByText("Nicht zugeordnet")).toBeInTheDocument();
    expect(within(zimt).getByText("unbekannt")).toBeInTheDocument();
    const oats = rows.find((r) => within(r).queryByText("200 g Haferflocken"))!;
    expect(oats).not.toHaveClass("rc-unassigned");
    expect(within(oats).getByText("Haferflocken")).toBeInTheDocument();
    expect(screen.getByText(/1 Zutat ist noch keiner Zutat aus dem Katalog zugeordnet/)).toBeInTheDocument();
    expect(screen.getByText("Prüfen")).toBeInTheDocument();
  });

  it("ordnet eine Zeile über die Zutatensuche zu (mit Zuordnung merken) und lädt neu", async () => {
    let assigned = false;
    const server = serverFor(
      () =>
        detail({
          lines: [
            line(),
            assigned
              ? line({ id: 12, position: 1, raw_text: "1 Prise Zimt", grams: 0.4, ingredient: { id: 9, name: "Zimt", source: "bls" } })
              : line({ id: 12, position: 1, raw_text: "1 Prise Zimt", grams: null, ingredient: null }),
          ],
        }),
      {
        "GET /ingredients": () => ({
          body: {
            items: [{ id: 9, name: "Zimt", category: "Gewürze", source: "bls" }],
            total: 1,
            limit: 8,
            offset: 0,
          },
        }),
        "POST /recipe-lines/12/assign": () => {
          assigned = true;
          return { body: { line: line({ id: 12 }), assigned_line_ids: [12, 40], recipe_ids: [7, 8], synonym: "zimt" } };
        },
      },
    );
    renderPage(<RecipesPage />, ROUTE);
    await userEvent.click(await screen.findByRole("button", { name: "Zutat zuordnen: 1 Prise Zimt" }));
    const group = screen.getByRole("group", { name: "Zuordnung für 1 Prise Zimt" });
    // Startwert der Suche wird aus der Zeile geraten
    expect(within(group).getByLabelText("Andere Zutat suchen")).toHaveValue("Zimt");
    expect(within(group).getByLabelText("Zuordnung merken")).toBeChecked();
    await userEvent.click(await within(group).findByRole("button", { name: "Zimt zuordnen" }));
    expect(server.calls.some((c) => c.path === "/ingredients?q=Zimt&limit=8")).toBe(true);

    const post = server.calls.find((c) => c.method === "POST");
    expect(post?.path).toBe("/recipe-lines/12/assign");
    expect(post?.body).toEqual({ ingredient_id: 9, save_synonym: true });
    expect(await screen.findByText(/Zugeordnet\. 1 gleichlautende Zeile wurde ebenfalls zugeordnet\./)).toBeInTheDocument();
    await waitFor(() => expect(screen.queryByText("Nicht zugeordnet")).not.toBeInTheDocument());
    expect(screen.getByText("Zimt")).toBeInTheDocument();
    expect(screen.queryByRole("group", { name: "Zuordnung für 1 Prise Zimt" })).not.toBeInTheDocument();
  });

  it("sendet save_synonym=false, wenn „Zuordnung merken“ abgewählt ist, und zeigt Fehler im Panel", async () => {
    const server = serverFor(() => detail(), {
      "GET /ingredients": {
        body: { items: [{ id: 9, name: "Zimt", category: null, source: "bls" }], total: 1, limit: 8, offset: 0 },
      },
      "POST /recipe-lines/12/assign": { status: 404, body: { detail: "Zutat nicht gefunden." } },
    });
    renderPage(<RecipesPage />, ROUTE);
    await userEvent.click(await screen.findByRole("button", { name: "Zutat zuordnen: 1 Prise Zimt" }));
    const group = screen.getByRole("group", { name: "Zuordnung für 1 Prise Zimt" });
    await userEvent.click(within(group).getByLabelText("Zuordnung merken"));
    await userEvent.click(await within(group).findByRole("button", { name: "Zimt zuordnen" }));
    expect(await within(group).findByText("Zutat nicht gefunden.")).toBeInTheDocument();
    expect(server.calls.find((c) => c.method === "POST")?.body).toEqual({ ingredient_id: 9, save_synonym: false });
  });

  describe("Portionsregler", () => {
    it("startet mit dem Faktor der Passung und rechnet die Nährwerte live um", async () => {
      serverFor(() => detail());
      renderPage(<RecipesPage />, ROUTE);
      const section = (await screen.findByRole("heading", { name: "Nährwerte" })).closest("section")!;
      const slider = within(section).getByLabelText("Portionsfaktor");
      expect(slider).toHaveValue("1.5");
      expect(within(section).getByText(/1,5-fache Portion · 570 g/)).toBeInTheDocument();

      fireEvent.change(slider, { target: { value: "2" } });
      expect(within(section).getByText(/2-fache Portion · 760 g/)).toBeInTheDocument();
      expect(within(section).getByRole("row", { name: /^Kalorien/ })).toHaveTextContent("1.200 kcal");
      expect(within(section).getByRole("columnheader", { name: /Je Portion \(2-fache Portion\)/ })).toBeInTheDocument();

      fireEvent.change(slider, { target: { value: "0.5" } });
      expect(within(section).getByRole("row", { name: /^Kalorien/ })).toHaveTextContent("300 kcal");
      expect(within(section).getByRole("row", { name: /^Protein/ })).toHaveTextContent("18,0 g");
      // die Balken im Fit-Block folgen dem Regler: 300 von 900 kcal
      expect(screen.getByRole("meter", { name: "Kalorien: 33 % des Ziels" })).toBeInTheDocument();
      expect(screen.getByText(/gelten für die 1,5-fache Portion/)).toBeInTheDocument();

      await userEvent.click(within(section).getByRole("button", { name: "Eine Portion" }));
      expect(within(section).getByRole("row", { name: /^Kalorien/ })).toHaveTextContent("600 kcal");
      await userEvent.click(within(section).getByRole("button", { name: "Auf Mahlzeit abstimmen" }));
      expect(within(section).getByRole("row", { name: /^Kalorien/ })).toHaveTextContent("900 kcal");
    });

    it("hält den Wert der Schaltfläche „Eine Portion“ im Rahmen 0,5 bis 2", async () => {
      serverFor(() => detail({ fit: fit({ factor: 1 }) }));
      renderPage(<RecipesPage />, ROUTE);
      const slider = await screen.findByLabelText("Portionsfaktor");
      expect(slider).toHaveAttribute("min", "0.5");
      expect(slider).toHaveAttribute("max", "2");
      expect(screen.getByRole("button", { name: "Eine Portion" })).toBeDisabled();
    });
  });

  it("setzt die eigene Bewertung (PUT) und lädt neu", async () => {
    let mine = 4;
    const server = serverFor(() => detail({ my_rating: mine }), {
      "PUT /recipes/7/rating": ({ body }) => {
        mine = (body as { rating: number }).rating;
        return { body: { recipe_id: 7, person_id: 1, rating: mine } };
      },
    });
    renderPage(<RecipesPage />, ROUTE);
    const group = await screen.findByRole("group", { name: "Eigene Bewertung" });
    await userEvent.click(within(group).getByRole("button", { name: "5 von 5 Sternen" }));
    await waitFor(() =>
      expect(within(screen.getByRole("group", { name: "Eigene Bewertung" })).getByRole("button", { name: "5 von 5 Sternen" })).toHaveAttribute(
        "aria-pressed",
        "true",
      ),
    );
    expect(server.calls.find((c) => c.method === "PUT")?.body).toEqual({ rating: 5 });
  });

  it("schaltet den Favoriten per PATCH", async () => {
    const server = serverFor(() => detail(), { "PATCH /recipes/7": { body: {} } });
    renderPage(<RecipesPage />, ROUTE);
    await userEvent.click(await screen.findByRole("button", { name: "Als Favorit markieren: Hafer-Bowl" }));
    await waitFor(() => expect(server.calls.some((c) => c.method === "PATCH")).toBe(true));
    expect(server.calls.find((c) => c.method === "PATCH")?.body).toEqual({ favorite: true });
  });

  it("bearbeitet das Rezept: Felder, Tags und Zutaten als Text (unveränderte Zeilen behalten ihre id)", async () => {
    const server = serverFor(() => detail({ tag: { ...detail().tag, slot_types: ["breakfast"], warm: false, cuisine: "deutsch" } }), {
      "PATCH /recipes/7": { body: detail() },
    });
    renderPage(<RecipesPage />, ROUTE);
    await userEvent.click(await screen.findByRole("button", { name: "Bearbeiten" }));
    const form = screen.getByRole("form", { name: "Rezept bearbeiten" });
    const f = within(form);
    expect(f.getByLabelText("Titel")).toHaveValue("Hafer-Bowl");
    expect(f.getByLabelText("Portionen")).toHaveValue(2);
    expect(f.getByLabelText("Vorbereitung (Min.)")).toHaveValue(10);
    expect(f.getByLabelText("Frühstück")).toBeChecked();
    expect(f.getByLabelText("Mittagessen")).not.toBeChecked();
    expect(f.getByLabelText("Küche")).toHaveValue("deutsch");
    expect(f.getByLabelText("Zutaten (eine pro Zeile)")).toHaveValue("200 g Haferflocken\n1 Prise Zimt");

    await userEvent.clear(f.getByLabelText("Titel"));
    await userEvent.type(f.getByLabelText("Titel"), "  Hafer-Bowl mit Obst ");
    await userEvent.clear(f.getByLabelText("Portionen"));
    await userEvent.type(f.getByLabelText("Portionen"), "3");
    await userEvent.click(f.getByLabelText("Mittagessen"));
    await userEvent.click(f.getByLabelText("Warm"));
    await userEvent.click(f.getByLabelText("Vorkochbar"));
    await userEvent.clear(f.getByLabelText("Küche"));
    await userEvent.type(f.getByLabelText("Hauptzutat"), "Hafer");
    fireEvent.change(f.getByLabelText("Zutaten (eine pro Zeile)"), {
      target: { value: "200 g Haferflocken\n\n1 Banane\n1 Prise Zimt" },
    });
    await userEvent.type(f.getByLabelText("Notizen"), "Schmeckt kalt");
    await userEvent.click(f.getByLabelText("Favorit"));
    await userEvent.click(f.getByRole("button", { name: "Speichern" }));

    await waitFor(() => expect(server.calls.some((c) => c.method === "PATCH")).toBe(true));
    const patch = server.calls.find((c) => c.method === "PATCH");
    expect(patch?.path).toBe("/recipes/7");
    expect(patch?.body).toEqual({
      title: "Hafer-Bowl mit Obst",
      servings: 3,
      prep_min: 10,
      cook_min: 35,
      instructions: "Haferflocken kochen.\nObst dazugeben.",
      notes: "Schmeckt kalt",
      favorite: true,
      tag: {
        slot_types: ["breakfast", "lunch"],
        warm: true,
        transportable: false,
        batch_cookable: true,
        cuisine: null,
        main_ingredient: "Hafer",
      },
      lines: [
        { id: 11, raw_text: "200 g Haferflocken" },
        { raw_text: "1 Banane" },
        { id: 12, raw_text: "1 Prise Zimt" },
      ],
    });
    await waitFor(() => expect(screen.queryByRole("form")).not.toBeInTheDocument());
  });

  it("prüft das Formular vor dem Senden und zeigt Fehler des Servers", async () => {
    const server = serverFor(() => detail(), {
      "PATCH /recipes/7": { status: 422, body: { detail: "Der Titel darf nicht leer sein." } },
    });
    renderPage(<RecipesPage />, ROUTE);
    await userEvent.click(await screen.findByRole("button", { name: "Bearbeiten" }));
    const form = screen.getByRole("form", { name: "Rezept bearbeiten" });
    await userEvent.clear(within(form).getByLabelText("Titel"));
    await userEvent.click(within(form).getByRole("button", { name: "Speichern" }));
    expect(within(form).getByRole("alert")).toHaveTextContent("Bitte einen Titel angeben.");
    expect(server.calls.some((c) => c.method === "PATCH")).toBe(false);

    await userEvent.type(within(form).getByLabelText("Titel"), "X");
    await userEvent.click(within(form).getByRole("button", { name: "Speichern" }));
    expect(await within(form).findByText("Der Titel darf nicht leer sein.")).toBeInTheDocument();
    expect(screen.getByRole("form", { name: "Rezept bearbeiten" })).toBeInTheDocument();
  });

  it("bricht das Bearbeiten ab", async () => {
    serverFor(() => detail());
    renderPage(<RecipesPage />, ROUTE);
    await userEvent.click(await screen.findByRole("button", { name: "Bearbeiten" }));
    await userEvent.click(screen.getByRole("button", { name: "Abbrechen" }));
    expect(screen.queryByRole("form")).not.toBeInTheDocument();
    expect(screen.getByRole("heading", { level: 1, name: "Hafer-Bowl" })).toBeInTheDocument();
  });

  it("löscht nach Rückfrage und kehrt zur Liste zurück", async () => {
    const server = serverFor(() => detail(), { "DELETE /recipes/7": { status: 204 } });
    renderPage(<RecipesPage />, ROUTE);
    await userEvent.click(await screen.findByRole("button", { name: "Löschen" }));
    expect(server.calls.some((c) => c.method === "DELETE")).toBe(false);
    const dialog = screen.getByRole("alertdialog");
    expect(dialog).toHaveTextContent("„Hafer-Bowl“ wirklich löschen?");
    await userEvent.click(within(dialog).getByRole("button", { name: "Ja, löschen" }));
    await waitFor(() => expect(server.calls.some((c) => c.method === "DELETE" && c.path === "/recipes/7")).toBe(true));
    expect(await screen.findByRole("list", { name: "Rezepte" })).toBeInTheDocument();
    expect(screen.queryByRole("heading", { level: 1, name: "Hafer-Bowl" })).not.toBeInTheDocument();
  });

  it("zeigt Fehler beim Löschen in der Rückfrage", async () => {
    serverFor(() => detail(), { "DELETE /recipes/7": { status: 404, body: { detail: "Rezept nicht gefunden." } } });
    renderPage(<RecipesPage />, ROUTE);
    await userEvent.click(await screen.findByRole("button", { name: "Löschen" }));
    await userEvent.click(screen.getByRole("button", { name: "Ja, löschen" }));
    expect(await within(screen.getByRole("alertdialog")).findByRole("alert")).toHaveTextContent("Rezept nicht gefunden.");
  });

  it("zeigt „nicht gefunden“ mit Link zurück zur Liste", async () => {
    mockServer({
      "GET /me/targets": { body: targets() },
      "GET /recipes/7": { status: 404, body: { detail: "Rezept nicht gefunden." } },
    });
    renderPage(<RecipesPage />, ROUTE);
    expect(await screen.findByText("Rezept nicht gefunden.")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "← Alle Rezepte" })).toBeInTheDocument();
  });

  it("zeigt Warnungen des Imports und Notizen", async () => {
    serverFor(() => detail({ warnings: ["Keine Portionszahl bekannt."], notes: "Hinweis: kcal weichen ab." }));
    renderPage(<RecipesPage />, ROUTE);
    expect(await screen.findByText("Keine Portionszahl bekannt.")).toBeInTheDocument();
    expect(screen.getByText("Hinweis: kcal weichen ab.")).toBeInTheDocument();
  });
});

describe("buildLines", () => {
  const original = [line({ id: 1, raw_text: "a" }), line({ id: 2, raw_text: "b" }), line({ id: 3, raw_text: "a" })];

  it("behält ids bei unveränderten Zeilen, auch bei Umsortierung und doppeltem Text", () => {
    expect(buildLines("b\na\na\nc", original)).toEqual([
      { id: 2, raw_text: "b" },
      { id: 1, raw_text: "a" },
      { id: 3, raw_text: "a" },
      { raw_text: "c" },
    ]);
  });

  it("sendet neue Zeilen nur als Text und ignoriert Leerzeilen", () => {
    expect(buildLines("  x \n\n y ")).toEqual([{ raw_text: "x" }, { raw_text: "y" }]);
  });
});
