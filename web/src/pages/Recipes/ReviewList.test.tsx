import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";
import { mockServer, renderPage } from "../../test/helpers";
import RecipesPage from "./index";
import type { UnassignedLine } from "./types";

const ROUTE = { route: "/?tab=pruefen" };

function item(over: Partial<UnassignedLine> = {}): UnassignedLine {
  return {
    line_id: 1,
    recipe_id: 7,
    recipe_title: "Hafer-Bowl",
    raw_text: "1 Prise Garam Masala",
    name: "Garam Masala",
    quantity: 1,
    unit: "Prise",
    similar_count: 2,
    suggestions: [
      { ingredient_id: 8, name: "Currypulver", score: 61, via: "fuzzy" },
      { ingredient_id: 9, name: "Kreuzkümmel", score: 50, via: "fuzzy" },
    ],
    ...over,
  };
}

const page = (items: UnassignedLine[]) => ({ items, total: items.length, limit: 50, offset: 0 });

describe("Zutaten prüfen", () => {
  it("zeigt Zeilen mit Rezepttitel, Menge, Hinweis auf gleichlautende Zeilen und Vorschlägen als Schaltflächen", async () => {
    mockServer({ "GET /recipe-lines/unassigned": { body: page([item(), item({ line_id: 2, raw_text: "Salz", name: "Salz", quantity: null, unit: null, similar_count: 1, suggestions: [] })]) } });
    renderPage(<RecipesPage />, ROUTE);
    const list = await screen.findByRole("list", { name: "Zutaten prüfen" });
    const [first, second] = within(list).getAllByRole("listitem");
    const a = within(first!);
    expect(a.getByRole("heading", { name: "1 Prise Garam Masala" })).toBeInTheDocument();
    expect(a.getByRole("link", { name: "Hafer-Bowl" })).toHaveAttribute("href", "/?rezept=7");
    expect(a.getByText(/Menge 1 Prise/)).toBeInTheDocument();
    expect(a.getByText(/1 gleichlautende Zeile werden/)).toBeInTheDocument();
    expect(a.getByRole("button", { name: "Vorschlag Currypulver zuordnen" })).toBeInTheDocument();
    expect(a.getByRole("button", { name: "Vorschlag Kreuzkümmel zuordnen" })).toBeInTheDocument();
    expect(within(second!).queryByText("Vorschläge")).not.toBeInTheDocument();
    expect(screen.getByText("2 Zeilen offen")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Zutaten prüfen" })).toHaveAttribute("aria-current", "page");
  });

  it("ordnet per Vorschlag zu (merken ist Standard); gleichlautende Zeilen verschwinden", async () => {
    let rows = [item(), item({ line_id: 5, recipe_id: 8, recipe_title: "Dal", similar_count: 2 }), item({ line_id: 6, raw_text: "Salz", name: "Salz", similar_count: 1, suggestions: [] })];
    const server = mockServer({
      "GET /recipe-lines/unassigned": () => ({ body: page(rows) }),
      "POST /recipe-lines/1/assign": () => {
        rows = rows.filter((r) => r.line_id === 6);
        return {
          body: { line: {}, assigned_line_ids: [1, 5], recipe_ids: [7, 8], synonym: "garam masala" },
        };
      },
    });
    renderPage(<RecipesPage />, ROUTE);
    const list = await screen.findByRole("list", { name: "Zutaten prüfen" });
    const first = within(within(list).getAllByRole("listitem")[0]!);
    expect(first.getByLabelText("Zuordnung merken")).toBeChecked();
    await userEvent.click(first.getByRole("button", { name: "Vorschlag Currypulver zuordnen" }));

    expect(await screen.findByText(/„1 Prise Garam Masala“ zugeordnet: 2 Zeilen in 2 Rezepten wurden aktualisiert\./)).toBeInTheDocument();
    expect(server.calls.find((c) => c.method === "POST")?.body).toEqual({ ingredient_id: 8, save_synonym: true });
    await waitFor(() => expect(within(screen.getByRole("list", { name: "Zutaten prüfen" })).getAllByRole("listitem")).toHaveLength(1));
    expect(screen.getByRole("heading", { name: "Salz" })).toBeInTheDocument();
    expect(screen.queryByRole("heading", { name: "1 Prise Garam Masala" })).not.toBeInTheDocument();
    expect(screen.getByText("1 Zeile offen")).toBeInTheDocument();
  });

  it("ordnet über die Zutatensuche zu, ohne zu merken", async () => {
    const server = mockServer({
      "GET /recipe-lines/unassigned": { body: page([item({ similar_count: 1 })]) },
      "GET /ingredients": {
        body: { items: [{ id: 21, name: "Gewürzmischung", category: "Gewürze", source: "bls" }], total: 1, limit: 8, offset: 0 },
      },
      "POST /recipe-lines/1/assign": { body: { line: {}, assigned_line_ids: [1], recipe_ids: [7], synonym: null } },
    });
    renderPage(<RecipesPage />, ROUTE);
    const group = await screen.findByRole("group", { name: "Zuordnung für 1 Prise Garam Masala" });
    await userEvent.click(within(group).getByLabelText("Zuordnung merken"));
    await userEvent.type(within(group).getByLabelText("Andere Zutat suchen"), "Gewürz");
    await userEvent.click(await within(group).findByRole("button", { name: "Gewürzmischung zuordnen" }));
    expect(server.calls.some((c) => c.path === "/ingredients?q=Gew%C3%BCrz&limit=8")).toBe(true);
    await waitFor(() => expect(server.calls.some((c) => c.method === "POST")).toBe(true));
    expect(server.calls.find((c) => c.method === "POST")?.body).toEqual({ ingredient_id: 21, save_synonym: false });
    expect(await screen.findByText(/„1 Prise Garam Masala“ zugeordnet\./)).toBeInTheDocument();
  });

  it("meldet, wenn die Suche nichts findet", async () => {
    mockServer({
      "GET /recipe-lines/unassigned": { body: page([item()]) },
      "GET /ingredients": { body: { items: [], total: 0, limit: 8, offset: 0 } },
    });
    renderPage(<RecipesPage />, ROUTE);
    const group = await screen.findByRole("group", { name: "Zuordnung für 1 Prise Garam Masala" });
    await userEvent.type(within(group).getByLabelText("Andere Zutat suchen"), "xyz");
    expect(await within(group).findByText(/Keine Zutat gefunden/)).toBeInTheDocument();
  });

  it("zeigt Fehler der Zuordnung an der Zeile und lässt die Liste stehen", async () => {
    mockServer({
      "GET /recipe-lines/unassigned": { body: page([item()]) },
      "POST /recipe-lines/1/assign": { status: 404, body: { detail: "Zutat nicht gefunden." } },
    });
    renderPage(<RecipesPage />, ROUTE);
    await userEvent.click(await screen.findByRole("button", { name: "Vorschlag Currypulver zuordnen" }));
    expect(await screen.findByText("Zutat nicht gefunden.")).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "1 Prise Garam Masala" })).toBeInTheDocument();
  });

  it("zeigt einen leeren Zustand", async () => {
    mockServer({ "GET /recipe-lines/unassigned": { body: page([]) } });
    renderPage(<RecipesPage />, ROUTE);
    expect(await screen.findByText(/Alle Zutaten sind zugeordnet/)).toBeInTheDocument();
  });

  it("zeigt Ladefehler", async () => {
    mockServer({ "GET /recipe-lines/unassigned": { status: 500, body: {} } });
    renderPage(<RecipesPage />, ROUTE);
    expect(await screen.findByRole("alert")).toHaveTextContent("Serverfehler");
  });

  it("zeigt zuerst einen Ladehinweis", async () => {
    mockServer({ "GET /recipe-lines/unassigned": { body: page([]) } });
    renderPage(<RecipesPage />, ROUTE);
    expect(screen.getByText("Lädt …")).toBeInTheDocument();
    await screen.findByText(/Alle Zutaten sind zugeordnet/);
  });
});
