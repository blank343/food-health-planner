import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { mockServer, renderPage } from "../../test/helpers";
import { NO_TARGETS, TODAY, card, list, targets } from "./fixtures";
import RecipesPage from "./index";
import { buildListPath } from "./RecipeList";
import { DEFAULT_FILTERS } from "./types";

beforeEach(() => {
  // Nur die Uhrzeit festlegen (12 Uhr: Standard-Mahlzeit ist das Mittagessen), Timer laufen normal.
  vi.useFakeTimers({ toFake: ["Date"] });
  vi.setSystemTime(new Date(2026, 9, 6, 12, 0, 0));
});
afterEach(() => vi.useRealTimers());

const fitted = (over = {}) => card({ fit_score: 87, fit_factor: 1.5, ...over });

function recipePaths(server: ReturnType<typeof mockServer>): string[] {
  return server.calls.filter((c) => c.method === "GET" && c.path.startsWith("/recipes")).map((c) => c.path);
}

describe("Rezeptliste", () => {
  it("zeigt zuerst einen Ladehinweis", async () => {
    mockServer({ "GET /me/targets": { body: targets() }, "GET /recipes": { body: list([]) } });
    renderPage(<RecipesPage />);
    expect(screen.getByText("Berechne Tagesziel …")).toBeInTheDocument();
    await screen.findByText(/Noch keine Rezepte/);
  });

  it("zeigt Karten mit kcal, Protein, Portionsgewicht, Zeit, Sättigung und Status", async () => {
    mockServer({
      "GET /me/targets": NO_TARGETS,
      "GET /recipes": {
        body: list([
          card({ status: "needs_review", avg_rating: 4.5, coverage: 0.8 }),
          card({ id: 2, title: "Linsensuppe", status: "ready", prep_min: null, cook_min: null, favorite: true }),
        ]),
      },
    });
    renderPage(<RecipesPage />);
    const grid = await screen.findByRole("list", { name: "Rezepte" });
    const [first, second] = within(grid).getAllByRole("listitem");
    const a = within(first!);
    expect(a.getByRole("link", { name: "Hafer-Bowl" })).toHaveAttribute("href", "/?rezept=1");
    expect(a.getByText("600 kcal")).toBeInTheDocument();
    expect(a.getByText("36 g")).toBeInTheDocument();
    expect(a.getByText(/Portion 380 g · Zeit 45 Min\./)).toBeInTheDocument();
    expect(a.getByText("Sättigung 72 von 100 (hoch)")).toBeInTheDocument();
    expect(a.getByRole("meter", { name: "Sättigung: 72 von 100" })).toHaveAttribute("aria-valuenow", "72");
    expect(a.getByText("Prüfen")).toBeInTheDocument();
    expect(a.getByText("Frühstück")).toBeInTheDocument();
    expect(a.getByText(/nur 80 % der Zutaten/)).toBeInTheDocument();
    expect(a.getByText("Ø 4,5")).toBeInTheDocument();
    const b = within(second!);
    expect(b.getByText(/Zeit –/)).toBeInTheDocument();
    expect(b.queryByText("Prüfen")).not.toBeInTheDocument();
    expect(b.getByRole("button", { name: "Favorit entfernen: Linsensuppe" })).toHaveAttribute("aria-pressed", "true");
    expect(screen.getByText("2 Rezepte")).toBeInTheDocument();
  });

  it("fragt standardmäßig Slot nach Tageszeit (Mittag) und heutiges Datum für die Passung ab", async () => {
    const server = mockServer({
      "GET /me/targets": { body: targets() },
      "GET /recipes": { body: list([fitted()]) },
    });
    renderPage(<RecipesPage />);
    await screen.findByRole("list", { name: "Rezepte" });
    expect(screen.getByLabelText("Mahlzeit")).toHaveValue("lunch");
    expect(screen.getByLabelText("Datum für das Tagesziel")).toHaveValue(TODAY);
    expect(recipePaths(server)).toEqual([
      `/recipes?fit_slot=lunch&fit_date=${TODAY}&sort=title&limit=100`,
    ]);
  });

  it("bietet nur Mahlzeiten mit Anteil größer 0 an", async () => {
    mockServer({ "GET /me/targets": { body: targets() }, "GET /recipes": { body: list([]) } });
    renderPage(<RecipesPage />);
    const select = await screen.findByLabelText("Mahlzeit");
    await waitFor(() => expect(select).toBeEnabled());
    const options = within(select).getAllByRole("option").map((o) => o.textContent);
    expect(options).toEqual(["Ohne Passung", "Frühstück", "Mittagessen", "Abendessen"]);
  });

  it("zeigt Fit-Score, Portionsfaktor und Balken je Makro mit Abweichung", async () => {
    mockServer({
      "GET /me/targets": { body: targets() },
      "GET /recipes": { body: list([fitted()]) },
    });
    renderPage(<RecipesPage />);
    const item = within((await screen.findAllByRole("listitem"))[0]!);
    expect(item.getByText("Passung 87 von 100: sehr gut")).toBeInTheDocument();
    expect(item.getByText("1,5-fache Portion")).toBeInTheDocument();
    const kcal = item.getByRole("meter", { name: "Kalorien: 100 % des Ziels" });
    expect(kcal).toHaveAttribute("aria-valuetext", "100 % des Ziels, trifft das Ziel");
    const protein = item.getByRole("meter", { name: "Protein: 90 % des Ziels" });
    expect(protein).toHaveAttribute("aria-valuetext", "90 % des Ziels, 10 % unter dem Ziel");
    expect(item.getByRole("meter", { name: "Kohlenhydrate: 120 % des Ziels" })).toHaveAttribute(
      "aria-valuetext",
      "120 % des Ziels, 20 % über dem Ziel",
    );
    // Text statt nur Farbe: die Abweichung steht auch sichtbar da
    expect(item.getByText(/54 von 60 g · 10 % unter dem Ziel/)).toBeInTheDocument();
  });

  it("wechselt die Mahlzeit, lädt neu und kann die Passung abschalten", async () => {
    const server = mockServer({
      "GET /me/targets": { body: targets() },
      "GET /recipes": ({ path }) => ({
        body: list([path.includes("fit_slot") ? fitted() : card()]),
      }),
    });
    renderPage(<RecipesPage />);
    await screen.findByText("Passung 87 von 100: sehr gut");
    await userEvent.selectOptions(screen.getByLabelText("Mahlzeit"), "dinner");
    await waitFor(() => expect(recipePaths(server).some((p) => p.includes("fit_slot=dinner"))).toBe(true));
    await userEvent.selectOptions(screen.getByLabelText("Mahlzeit"), "none");
    await waitFor(() => expect(screen.queryByText(/Passung 87 von 100/)).not.toBeInTheDocument());
    expect(recipePaths(server).at(-1)).toBe("/recipes?sort=title&limit=100");
  });

  it("lädt bei Datumswechsel Tagesziel und Liste neu", async () => {
    const server = mockServer({
      "GET /me/targets": { body: targets() },
      "GET /recipes": { body: list([fitted()]) },
    });
    renderPage(<RecipesPage />);
    await screen.findByText("Passung 87 von 100: sehr gut");
    const date = screen.getByLabelText("Datum für das Tagesziel");
    await userEvent.clear(date);
    await userEvent.type(date, "2026-10-09");
    await waitFor(() => expect(server.calls.some((c) => c.path === "/me/targets?date=2026-10-09")).toBe(true));
    await waitFor(() => expect(recipePaths(server).some((p) => p.includes("fit_date=2026-10-09"))).toBe(true));
  });

  it("erklärt einen 422 des Tagesziels freundlich und lädt die Liste ohne Passung", async () => {
    const server = mockServer({
      "GET /me/targets": NO_TARGETS,
      "GET /recipes": { body: list([card()]) },
    });
    renderPage(<RecipesPage />);
    expect(await screen.findByText("Das Tagesziel kann noch nicht berechnet werden.")).toBeInTheDocument();
    expect(screen.getByText(/Es liegt kein Gewicht vor/)).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Tagesziel" })).toHaveAttribute("href", "/ziele");
    expect(screen.getByRole("link", { name: "Importe" })).toHaveAttribute("href", "/importe");
    expect(await screen.findByRole("link", { name: "Hafer-Bowl" })).toBeInTheDocument();
    expect(recipePaths(server)).toEqual(["/recipes?sort=title&limit=100"]);
    expect(screen.getByLabelText("Mahlzeit")).toBeDisabled();
    expect(screen.queryByText(/Passung \d+ von 100/)).not.toBeInTheDocument();
    // Sortierung nach Passung gibt es ohne Passung nicht
    const sortOptions = within(screen.getByLabelText("Sortierung")).getAllByRole("option").map((o) => o.textContent);
    expect(sortOptions).not.toContain("Passung (beste zuerst)");
  });

  it("zeigt andere Fehler des Tagesziels als Fehler", async () => {
    mockServer({ "GET /me/targets": { status: 500, body: {} }, "GET /recipes": { body: list([]) } });
    renderPage(<RecipesPage />);
    expect(await screen.findByText("Serverfehler. Bitte später erneut versuchen.")).toBeInTheDocument();
  });

  it("sortiert nach Passung mit sort=fit", async () => {
    const server = mockServer({
      "GET /me/targets": { body: targets() },
      "GET /recipes": { body: list([fitted()]) },
    });
    renderPage(<RecipesPage />);
    await screen.findByText("Passung 87 von 100: sehr gut");
    await userEvent.selectOptions(screen.getByLabelText("Sortierung"), "fit");
    await waitFor(() => expect(recipePaths(server).at(-1)).toContain("sort=fit"));
    expect(recipePaths(server).at(-1)).toContain("fit_slot=lunch");
  });

  it("sucht (verzögert) und filtert nach Favoriten, Status und Mahlzeit", async () => {
    const server = mockServer({
      "GET /me/targets": NO_TARGETS,
      "GET /recipes": { body: list([card()]) },
    });
    renderPage(<RecipesPage />);
    await screen.findByRole("link", { name: "Hafer-Bowl" });

    await userEvent.type(screen.getByLabelText("Rezepte suchen"), "Hafer");
    await waitFor(() => expect(recipePaths(server).at(-1)).toContain("q=Hafer"));
    // beim Tippen entstehen keine Abfragen pro Buchstabe
    expect(recipePaths(server).filter((p) => p.includes("q="))).toHaveLength(1);

    await userEvent.click(screen.getByLabelText("Nur Favoriten"));
    await waitFor(() => expect(recipePaths(server).at(-1)).toContain("favorite=true"));

    await userEvent.selectOptions(screen.getByLabelText("Status"), "needs_review");
    await waitFor(() => expect(recipePaths(server).at(-1)).toContain("status=needs_review"));

    expect(screen.queryByLabelText("Auch Rezepte ohne Slot-Tag")).not.toBeInTheDocument();
    await userEvent.selectOptions(screen.getByLabelText("Mahlzeit des Rezepts"), "breakfast");
    await waitFor(() => expect(recipePaths(server).at(-1)).toContain("slot=breakfast"));
    expect(recipePaths(server).at(-1)).not.toContain("include_untagged");
    await userEvent.click(screen.getByLabelText("Auch Rezepte ohne Slot-Tag"));
    await waitFor(() => expect(recipePaths(server).at(-1)).toContain("include_untagged=true"));
  });

  it("zeigt einen leeren Zustand mit Importhinweis und öffnet den Import-Dialog", async () => {
    mockServer({ "GET /me/targets": NO_TARGETS, "GET /recipes": { body: list([]) } });
    renderPage(<RecipesPage />);
    expect(await screen.findByText("Noch keine Rezepte: Importiere ein Rezept per URL.")).toBeInTheDocument();
    const buttons = screen.getAllByRole("button", { name: "Rezept importieren" });
    await userEvent.click(buttons[buttons.length - 1]!);
    expect(screen.getByRole("dialog", { name: "Rezept importieren" })).toBeInTheDocument();
  });

  it("zeigt bei Filtern ohne Treffer einen anderen Hinweis und setzt die Filter zurück", async () => {
    const server = mockServer({ "GET /me/targets": NO_TARGETS, "GET /recipes": { body: list([]) } });
    renderPage(<RecipesPage />);
    await screen.findByText(/Noch keine Rezepte/);
    await userEvent.click(screen.getByLabelText("Nur Favoriten"));
    expect(await screen.findByText(/Keine Rezepte gefunden/)).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "Filter zurücksetzen" }));
    await waitFor(() => expect(recipePaths(server).at(-1)).not.toContain("favorite"));
    expect(screen.getByLabelText("Nur Favoriten")).not.toBeChecked();
  });

  it("zeigt Ladefehler der Liste", async () => {
    mockServer({
      "GET /me/targets": NO_TARGETS,
      "GET /recipes": { status: 500, body: { detail: "Serverfehler." } },
    });
    renderPage(<RecipesPage />);
    expect(await screen.findByText("Serverfehler.")).toBeInTheDocument();
  });

  it("setzt eine Bewertung per Klick (PUT) und nimmt sie beim erneuten Klick zurück (DELETE)", async () => {
    const server = mockServer({
      "GET /me/targets": NO_TARGETS,
      "GET /recipes": { body: list([card({ my_rating: 2 })]) },
      "PUT /recipes/1/rating": { body: { recipe_id: 1, person_id: 1, rating: 4 } },
      "DELETE /recipes/1/rating": { status: 204 },
    });
    renderPage(<RecipesPage />);
    const group = await screen.findByRole("group", { name: "Eigene Bewertung für Hafer-Bowl" });
    expect(within(group).getByRole("button", { name: "2 von 5 Sternen" })).toHaveAttribute("aria-pressed", "true");

    await userEvent.click(within(group).getByRole("button", { name: "4 von 5 Sternen" }));
    await waitFor(() =>
      expect(within(group).getByRole("button", { name: "4 von 5 Sternen" })).toHaveAttribute("aria-pressed", "true"),
    );
    const put = server.calls.find((c) => c.method === "PUT");
    expect(put?.path).toBe("/recipes/1/rating");
    expect(put?.body).toEqual({ rating: 4 });

    await userEvent.click(within(group).getByRole("button", { name: "4 von 5 Sternen" }));
    await waitFor(() => expect(server.calls.some((c) => c.method === "DELETE")).toBe(true));
    await waitFor(() =>
      expect(within(group).getByRole("button", { name: "4 von 5 Sternen" })).toHaveAttribute("aria-pressed", "false"),
    );
  });

  it("zeigt einen Fehler, wenn die Bewertung nicht gespeichert werden kann", async () => {
    mockServer({
      "GET /me/targets": NO_TARGETS,
      "GET /recipes": { body: list([card()]) },
      "PUT /recipes/1/rating": { status: 500, body: {} },
    });
    renderPage(<RecipesPage />);
    await userEvent.click(await screen.findByRole("button", { name: "5 von 5 Sternen" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("Serverfehler");
    expect(screen.getByRole("button", { name: "5 von 5 Sternen" })).toHaveAttribute("aria-pressed", "false");
  });

  it("markiert Favoriten (PATCH)", async () => {
    const server = mockServer({
      "GET /me/targets": NO_TARGETS,
      "GET /recipes": { body: list([card()]) },
      "PATCH /recipes/1": { body: {} },
    });
    renderPage(<RecipesPage />);
    const button = await screen.findByRole("button", { name: "Als Favorit markieren: Hafer-Bowl" });
    await userEvent.click(button);
    expect(await screen.findByRole("button", { name: "Favorit entfernen: Hafer-Bowl" })).toBeInTheDocument();
    expect(server.calls.find((c) => c.method === "PATCH")?.body).toEqual({ favorite: true });
  });
});

describe("buildListPath", () => {
  it("lässt leere Filter weg und setzt include_untagged nur mit Mahlzeit", () => {
    expect(buildListPath(DEFAULT_FILTERS, "", null, "title")).toBe("/recipes?sort=title&limit=100");
    expect(buildListPath({ ...DEFAULT_FILTERS, untagged: true }, "", null, "title")).not.toContain("include_untagged");
    expect(
      buildListPath({ ...DEFAULT_FILTERS, slot: "lunch", untagged: true, favorite: true, status: "ready" }, "Reis", { slot: "dinner", date: TODAY }, "fit"),
    ).toBe(
      `/recipes?q=Reis&slot=lunch&include_untagged=true&favorite=true&status=ready&fit_slot=dinner&fit_date=${TODAY}&sort=fit&limit=100`,
    );
  });
});
