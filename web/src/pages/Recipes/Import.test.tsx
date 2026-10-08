import { fireEvent, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { mockServer, renderPage } from "../../test/helpers";
import { NO_TARGETS, card, detail, line, list } from "./fixtures";
import RecipesPage from "./index";
import type { Preview } from "./types";

beforeEach(() => {
  vi.useFakeTimers({ toFake: ["Date"] });
  vi.setSystemTime(new Date(2026, 9, 6, 12, 0, 0));
});
afterEach(() => vi.useRealTimers());

const URL_ = "https://beispiel.de/linsen-dal";

const PREVIEW: Preview = {
  title: "Linsen-Dal",
  source_url: URL_,
  source_site: "beispiel.de",
  servings: 4,
  prep_min: 10,
  cook_min: 25,
  instructions: "Alles kochen.",
  image_url: null,
  site_nutrients: {},
  warnings: ["Die Seite nennt keine Nährwerte."],
  lines: [
    {
      raw_text: "200 g Linsen",
      name: "Linsen",
      quantity: 200,
      unit: "g",
      note: null,
      optional: false,
      grams: 200,
      ingredient_id: 3,
      ingredient_name: "Linsen",
      matches: [
        { ingredient_id: 3, name: "Linsen", score: 100, via: "exact" },
        { ingredient_id: 4, name: "Linsen, rot", score: 80, via: "fuzzy" },
      ],
    },
    {
      raw_text: "1 Msp. Garam Masala",
      name: "Garam Masala",
      quantity: 1,
      unit: "Msp.",
      note: "frisch",
      optional: false,
      grams: null,
      ingredient_id: null,
      ingredient_name: null,
      matches: [{ ingredient_id: 8, name: "Currypulver", score: 55, via: "fuzzy" }],
    },
    {
      raw_text: "Salz",
      name: "Salz",
      quantity: null,
      unit: null,
      note: null,
      optional: true,
      grams: null,
      ingredient_id: null,
      ingredient_name: null,
      matches: [],
    },
  ],
};

const SAVED = detail({
  id: 55,
  title: "Linsen-Dal",
  lines: [
    line({ id: 101, position: 0, raw_text: "200 g Linsen", ingredient: { id: 3, name: "Linsen", source: "bls" } }),
    line({ id: 102, position: 1, raw_text: "1 Msp. Garam Masala", ingredient: null, grams: null }),
    line({ id: 103, position: 2, raw_text: "Salz", ingredient: null, grams: null, optional: true }),
  ],
});

function base(extra: Parameters<typeof mockServer>[0] = {}) {
  return mockServer({
    "GET /me/targets": NO_TARGETS,
    "GET /recipes": { body: list([card()]) },
    "GET /recipes/55": { body: SAVED },
    "GET /recipes/12": { body: detail({ id: 12, title: "Schon da" }) },
    ...extra,
  });
}

async function openDialog() {
  await userEvent.click(await screen.findByRole("button", { name: "Rezept importieren" }));
  return screen.getByRole("dialog", { name: "Rezept importieren" });
}

async function loadPreview(dialog: HTMLElement, url = URL_) {
  await userEvent.click(within(dialog).getByLabelText("Adresse des Rezepts (URL)"));
  await userEvent.paste(url);
  await userEvent.click(within(dialog).getByRole("button", { name: "Vorschau laden" }));
}

describe("Rezept importieren", () => {
  it("öffnet den Dialog mit Fokus im Adressfeld und schließt ihn mit Escape", async () => {
    base();
    renderPage(<RecipesPage />);
    const opener = await screen.findByRole("button", { name: "Rezept importieren" });
    opener.focus();
    const dialog = await openDialog();
    expect(dialog).toHaveAttribute("aria-modal", "true");
    expect(within(dialog).getByLabelText("Adresse des Rezepts (URL)")).toHaveFocus();
    await userEvent.keyboard("{Escape}");
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
    expect(opener).toHaveFocus();
  });

  it("hält den Tabulator im Dialog", async () => {
    base();
    renderPage(<RecipesPage />);
    const dialog = await openDialog();
    const close = within(dialog).getByRole("button", { name: "Rezept importieren schließen" });
    close.focus();
    await userEvent.tab({ shift: true });
    // von der ersten bedienbaren Stelle (Schließen) rückwärts: Sprung ans Ende des Dialogs
    expect(dialog.contains(document.activeElement)).toBe(true);
    await userEvent.tab();
    expect(dialog.contains(document.activeElement)).toBe(true);
  });

  it("verlangt eine Adresse mit http(s) und sendet sonst nichts", async () => {
    const server = base();
    renderPage(<RecipesPage />);
    const dialog = await openDialog();
    await loadPreview(dialog, "beispiel.de/rezept");
    expect(within(dialog).getByRole("alert")).toHaveTextContent("Bitte eine Adresse mit http:// oder https:// eingeben.");
    expect(server.calls.some((c) => c.method === "POST")).toBe(false);
  });

  it("zeigt die Vorschau mit Zutaten, vorgeschlagener Zutat, Treffern und Warnungen", async () => {
    const server = base({ "POST /recipes/import-preview": { body: PREVIEW } });
    renderPage(<RecipesPage />);
    const dialog = await openDialog();
    await loadPreview(dialog);
    expect(await within(dialog).findByRole("heading", { name: "Linsen-Dal" })).toBeInTheDocument();
    expect(server.calls.find((c) => c.path === "/recipes/import-preview")?.body).toEqual({ url: URL_ });
    expect(within(dialog).getByText(/beispiel\.de · 4 Portionen · 10 Min\. Vorbereitung, 25 Min\. Kochen/)).toBeInTheDocument();
    expect(within(dialog).getByText("Die Seite nennt keine Nährwerte.")).toBeInTheDocument();

    const list_ = within(dialog).getByRole("list", { name: "Erkannte Zutaten" });
    expect(within(list_).getAllByRole("listitem")).toHaveLength(3);
    const first = within(dialog).getByLabelText("Zutat für 200 g Linsen");
    expect(first).toHaveValue("3");
    expect(within(first).getAllByRole("option").map((o) => o.textContent)).toEqual(["Linsen (100 %)", "Linsen, rot (80 %)"]);
    const second = within(dialog).getByLabelText("Zutat für 1 Msp. Garam Masala");
    expect(second).toHaveValue("");
    expect(within(second).getAllByRole("option").map((o) => o.textContent)).toEqual(["Später zuordnen", "Currypulver (55 %)"]);
    expect(within(dialog).getByText(/≈ 200 g/)).toBeInTheDocument();
    expect(within(dialog).getByText(/frisch/)).toBeInTheDocument();
    expect(within(dialog).getByText(/Kein Treffer/)).toBeInTheDocument();
    // nichts gespeichert
    expect(server.calls.some((c) => c.path === "/recipes/import")).toBe(false);
  });

  it("speichert, übernimmt geänderte Zuordnungen und öffnet das Rezept", async () => {
    const server = base({
      "POST /recipes/import-preview": { body: PREVIEW },
      "POST /recipes/import": { status: 201, body: SAVED },
      "POST /recipe-lines/101/assign": { body: {} },
      "POST /recipe-lines/102/assign": { body: {} },
    });
    renderPage(<RecipesPage />);
    const dialog = await openDialog();
    await loadPreview(dialog);
    await within(dialog).findByRole("heading", { name: "Linsen-Dal" });
    await userEvent.selectOptions(within(dialog).getByLabelText("Zutat für 200 g Linsen"), "4");
    await userEvent.selectOptions(within(dialog).getByLabelText("Zutat für 1 Msp. Garam Masala"), "8");
    await userEvent.click(within(dialog).getByRole("button", { name: "Speichern" }));

    expect(await screen.findByRole("heading", { level: 1, name: "Linsen-Dal" })).toBeInTheDocument();
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
    const posts = server.calls.filter((c) => c.method === "POST").map((c) => [c.path, c.body]);
    expect(posts).toEqual([
      ["/recipes/import-preview", { url: URL_ }],
      ["/recipes/import", { url: URL_ }],
      ["/recipe-lines/101/assign", { ingredient_id: 4, save_synonym: true }],
      ["/recipe-lines/102/assign", { ingredient_id: 8, save_synonym: true }],
    ]);
  });

  it("speichert ohne Zusatzaufrufe, wenn die Zuordnungen unverändert bleiben (und merkt sich die Wahl nicht, wenn abgewählt)", async () => {
    const server = base({
      "POST /recipes/import-preview": { body: PREVIEW },
      "POST /recipes/import": { status: 201, body: SAVED },
      "POST /recipe-lines/102/assign": { body: {} },
    });
    renderPage(<RecipesPage />);
    const dialog = await openDialog();
    await loadPreview(dialog);
    await within(dialog).findByRole("heading", { name: "Linsen-Dal" });
    await userEvent.click(within(dialog).getByLabelText("Neue Zuordnungen merken"));
    await userEvent.selectOptions(within(dialog).getByLabelText("Zutat für 1 Msp. Garam Masala"), "8");
    await userEvent.click(within(dialog).getByRole("button", { name: "Speichern" }));
    await screen.findByRole("heading", { level: 1, name: "Linsen-Dal" });
    const assigns = server.calls.filter((c) => c.path.includes("/assign"));
    expect(assigns).toHaveLength(1);
    expect(assigns[0]?.body).toEqual({ ingredient_id: 8, save_synonym: false });
  });

  it("meldet, wenn eine Zuordnung nach dem Speichern scheitert, und bietet das Rezept an", async () => {
    base({
      "POST /recipes/import-preview": { body: PREVIEW },
      "POST /recipes/import": { status: 201, body: SAVED },
      "POST /recipe-lines/102/assign": { status: 500, body: {} },
    });
    renderPage(<RecipesPage />);
    const dialog = await openDialog();
    await loadPreview(dialog);
    await within(dialog).findByRole("heading", { name: "Linsen-Dal" });
    await userEvent.selectOptions(within(dialog).getByLabelText("Zutat für 1 Msp. Garam Masala"), "8");
    await userEvent.click(within(dialog).getByRole("button", { name: "Speichern" }));
    expect(await within(dialog).findByText(/Das Rezept ist gespeichert\. Eine Zuordnung konnte nicht übernommen werden/)).toBeInTheDocument();
    await userEvent.click(within(dialog).getByRole("button", { name: "Rezept öffnen" }));
    expect(await screen.findByRole("heading", { level: 1, name: "Linsen-Dal" })).toBeInTheDocument();
  });

  it("erklärt 422 (unbrauchbare Seite) verständlich", async () => {
    base({
      "POST /recipes/import-preview": { status: 422, body: { detail: "Auf der Seite wurde kein Rezept gefunden." } },
    });
    renderPage(<RecipesPage />);
    const dialog = await openDialog();
    await loadPreview(dialog);
    const alert = await within(dialog).findByRole("alert");
    expect(alert).toHaveTextContent("Diese Adresse lässt sich nicht als Rezept lesen.");
    expect(alert).toHaveTextContent("Auf der Seite wurde kein Rezept gefunden.");
    expect(within(dialog).queryByRole("button", { name: "Speichern" })).not.toBeInTheDocument();
  });

  it("erklärt 502 (Seite antwortet nicht) und empfiehlt das manuelle Anlegen", async () => {
    base({
      "POST /recipes/import-preview": { status: 502, body: { detail: "Die Seite konnte nicht geladen werden (Zeitüberschreitung)." } },
    });
    renderPage(<RecipesPage />);
    const dialog = await openDialog();
    await loadPreview(dialog);
    const alert = await within(dialog).findByRole("alert");
    expect(alert).toHaveTextContent("Die Seite hat nicht richtig geantwortet.");
    expect(alert).toHaveTextContent("Zeitüberschreitung");
    expect(alert).toHaveTextContent("von Hand anlegen");
  });

  it("erklärt 409 beim Speichern mit Link zum vorhandenen Rezept", async () => {
    base({
      "POST /recipes/import-preview": { body: PREVIEW },
      "POST /recipes/import": { status: 409, body: { detail: "Dieses Rezept ist schon vorhanden (ID 12)." } },
    });
    renderPage(<RecipesPage />);
    const dialog = await openDialog();
    await loadPreview(dialog);
    await within(dialog).findByRole("heading", { name: "Linsen-Dal" });
    await userEvent.click(within(dialog).getByRole("button", { name: "Speichern" }));
    const alert = await within(dialog).findByRole("alert");
    expect(alert).toHaveTextContent("Dieses Rezept gibt es schon.");
    const link = within(alert).getByRole("link", { name: "Vorhandenes Rezept öffnen" });
    expect(link).toHaveAttribute("href", "/?rezept=12");
    await userEvent.click(link);
    expect(await screen.findByRole("heading", { level: 1, name: "Schon da" })).toBeInTheDocument();
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
  });

  it("zeigt Netzwerkfehler verständlich", async () => {
    base({ "POST /recipes/import-preview": { status: 500, body: {} } });
    renderPage(<RecipesPage />);
    const dialog = await openDialog();
    await loadPreview(dialog);
    expect(await within(dialog).findByRole("alert")).toHaveTextContent("Der Import ist fehlgeschlagen. Serverfehler");
  });
});

describe("Neues Rezept von Hand", () => {
  async function openNew() {
    await userEvent.click(await screen.findByRole("button", { name: "Neues Rezept" }));
    return screen.getByRole("dialog", { name: "Rezept von Hand anlegen" });
  }

  it("legt ein Rezept mit Freitext-Zutaten an und öffnet es", async () => {
    const server = base({
      "POST /recipes": { status: 201, body: detail({ id: 60, title: "Pasta Pomodoro" }) },
      "GET /recipes/60": { body: detail({ id: 60, title: "Pasta Pomodoro" }) },
    });
    renderPage(<RecipesPage />);
    const dialog = await openNew();
    const f = within(dialog);
    expect(f.getByLabelText("Titel")).toHaveFocus();
    await userEvent.type(f.getByLabelText("Titel"), "  Pasta Pomodoro ");
    fireEvent.change(f.getByLabelText("Zutaten (eine pro Zeile)"), {
      target: { value: "200 g Spaghetti\n\n1 Dose Tomaten" },
    });
    await userEvent.type(f.getByLabelText("Anleitung"), "Kochen.");
    expect(f.queryByLabelText("Notizen")).not.toBeInTheDocument();
    await userEvent.click(f.getByRole("button", { name: "Rezept anlegen" }));

    expect(await screen.findByRole("heading", { level: 1, name: "Pasta Pomodoro" })).toBeInTheDocument();
    const post = server.calls.find((c) => c.method === "POST" && c.path === "/recipes");
    expect(post?.body).toEqual({
      title: "Pasta Pomodoro",
      servings: 2,
      instructions: "Kochen.",
      favorite: false,
      lines: [{ raw_text: "200 g Spaghetti" }, { raw_text: "1 Dose Tomaten" }],
    });
  });

  it("verlangt einen Titel und zeigt Fehler des Servers im Formular", async () => {
    const server = base({ "POST /recipes": { status: 422, body: { detail: "lines.0.raw_text: Text zu lang" } } });
    renderPage(<RecipesPage />);
    const dialog = await openNew();
    await userEvent.click(within(dialog).getByRole("button", { name: "Rezept anlegen" }));
    expect(within(dialog).getByRole("alert")).toHaveTextContent("Bitte einen Titel angeben.");
    expect(server.calls.some((c) => c.method === "POST")).toBe(false);
    await userEvent.type(within(dialog).getByLabelText("Titel"), "X");
    await userEvent.click(within(dialog).getByRole("button", { name: "Rezept anlegen" }));
    await waitFor(() => expect(within(dialog).getByRole("alert")).toHaveTextContent("Text zu lang"));
    expect(screen.getByRole("dialog", { name: "Rezept von Hand anlegen" })).toBeInTheDocument();
  });

  it("bricht ab", async () => {
    base();
    renderPage(<RecipesPage />);
    const dialog = await openNew();
    await userEvent.click(within(dialog).getByRole("button", { name: "Abbrechen" }));
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
  });
});
