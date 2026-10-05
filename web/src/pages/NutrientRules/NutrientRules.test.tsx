import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";
import { mockServer, renderPage } from "../../test/helpers";
import NutrientRulesPage from "./index";

type Rule = {
  id: number;
  subject: string;
  kind: "max" | "min" | "avoid" | "target";
  value: number | null;
  unit: string | null;
  per: "day" | "week";
  hard: boolean;
  enabled: boolean;
  doctor_confirmed: boolean;
  suggested_by_app: boolean;
  source: string | null;
  note: string | null;
};

const base = {
  unit: null,
  per: "day",
  hard: true,
  enabled: true,
  doctor_confirmed: false,
  suggested_by_app: false,
  source: null,
  note: null,
} as const;

const SALT: Rule = { ...base, id: 1, subject: "salt_g", kind: "max", value: 5, unit: "g", doctor_confirmed: true, source: "Beratung (erfunden)" };
const FISH: Rule = { ...base, id: 2, subject: "fatty_fish_portions", kind: "target", value: 1.5, unit: "Portionen", per: "week", hard: false, suggested_by_app: true };
const LICORICE: Rule = { ...base, id: 3, subject: "licorice", kind: "avoid", value: null, enabled: false, note: "Testnotiz" };

function serverWith(initial: Rule[], extra: Parameters<typeof mockServer>[0] = {}) {
  let list = [...initial];
  return mockServer({
    "GET /me/nutrient-rules": () => ({ body: list }),
    "POST /me/nutrient-rules": ({ body }) => {
      const created = { id: 99, ...(body as object) } as Rule;
      list = [...list, created];
      return { status: 201, body: created };
    },
    "PUT /me/nutrient-rules/1": ({ body }) => {
      const updated = { id: 1, ...(body as object) } as Rule;
      list = list.map((r) => (r.id === 1 ? updated : r));
      return { body: updated };
    },
    "PUT /me/nutrient-rules/2": ({ body }) => {
      const updated = { id: 2, ...(body as object) } as Rule;
      list = list.map((r) => (r.id === 2 ? updated : r));
      return { body: updated };
    },
    "PATCH /me/nutrient-rules/1": ({ body }) => {
      list = list.map((r) => (r.id === 1 ? { ...r, ...(body as object) } : r));
      return { body: list.find((r) => r.id === 1) };
    },
    "PATCH /me/nutrient-rules/2": ({ body }) => {
      list = list.map((r) => (r.id === 2 ? { ...r, ...(body as object) } : r));
      return { body: list.find((r) => r.id === 2) };
    },
    "DELETE /me/nutrient-rules/3": () => {
      list = list.filter((r) => r.id !== 3);
      return { status: 200 };
    },
    ...extra,
  });
}

const item = (name: string) => screen.getByRole("heading", { name }).closest("li") as HTMLElement;

describe("Ernährungsregeln", () => {
  it("zeigt Regeln mit deutschen Bezeichnungen, Werten, hart/sanft, Quelle und Notiz", async () => {
    serverWith([SALT, FISH, LICORICE]);
    renderPage(<NutrientRulesPage />);
    await screen.findByRole("list", { name: "Ernährungsregeln" });

    const salt = within(item("Salz (g)"));
    expect(salt.getByText("salt_g")).toBeInTheDocument();
    expect(salt.getByText("Obergrenze: 5 g pro Tag")).toBeInTheDocument();
    expect(salt.getByText("hart")).toBeInTheDocument();
    expect(salt.getByText("Quelle: Beratung (erfunden)")).toBeInTheDocument();

    const fish = within(item("Fetter Fisch (Portionen)"));
    expect(fish.getByText("Ziel: 1,5 Portionen pro Woche")).toBeInTheDocument();
    expect(fish.getByText("sanft")).toBeInTheDocument();

    const lic = within(item("Lakritz"));
    expect(lic.getAllByText("Meiden").length).toBeGreaterThan(0);
    expect(lic.getByText("pausiert")).toBeInTheDocument();
    expect(lic.getByText("Testnotiz")).toBeInTheDocument();
  });

  it("unbekannte Gegenstände erscheinen unverändert", async () => {
    serverWith([{ ...SALT, subject: "mein_stoff" }]);
    renderPage(<NutrientRulesPage />);
    expect(await screen.findByRole("heading", { name: "mein_stoff" })).toBeInTheDocument();
  });

  it("zeigt Badges für ärztlich bestätigt und App-Vorschlag", async () => {
    serverWith([SALT, FISH, LICORICE]);
    renderPage(<NutrientRulesPage />);
    await screen.findByRole("list", { name: "Ernährungsregeln" });
    expect(within(item("Salz (g)")).getByText("Vom Arzt bestätigt")).toBeInTheDocument();
    expect(within(item("Salz (g)")).queryByText(/Vorschlag der App/)).not.toBeInTheDocument();
    expect(within(item("Fetter Fisch (Portionen)")).getByText("Vorschlag der App – bitte ärztlich bestätigen")).toBeInTheDocument();
    expect(within(item("Lakritz")).queryByText("Vom Arzt bestätigt")).not.toBeInTheDocument();
    expect(within(item("Lakritz")).queryByText(/Vorschlag der App/)).not.toBeInTheDocument();
  });

  it("blendet den App-Vorschlag aus, sobald ein Arzt bestätigt hat", async () => {
    serverWith([{ ...FISH, doctor_confirmed: true }]);
    renderPage(<NutrientRulesPage />);
    const li = await screen.findByRole("heading", { name: "Fetter Fisch (Portionen)" });
    expect(within(li.closest("li") as HTMLElement).queryByText(/Vorschlag der App/)).not.toBeInTheDocument();
    expect(within(li.closest("li") as HTMLElement).getByText("Vom Arzt bestätigt")).toBeInTheDocument();
  });

  it("weist deutlich darauf hin, dass die App keine medizinischen Ratschläge gibt", async () => {
    serverWith([SALT]);
    renderPage(<NutrientRulesPage />);
    expect(await screen.findByText(/keine medizinischen Ratschläge/)).toBeInTheDocument();
  });

  it("zeigt einen leeren Zustand mit Aktion", async () => {
    serverWith([]);
    renderPage(<NutrientRulesPage />);
    expect(await screen.findByText(/Noch keine Ernährungsregeln/)).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "Erste Regel hinzufügen" }));
    expect(screen.getByRole("form", { name: "Regel hinzufügen" })).toBeInTheDocument();
  });

  it("legt eine Obergrenze an (Wert und Einheit werden gesendet)", async () => {
    const server = serverWith([SALT]);
    renderPage(<NutrientRulesPage />);
    await userEvent.click(await screen.findByRole("button", { name: "Regel hinzufügen" }));
    await userEvent.type(screen.getByLabelText("Gegenstand"), "zinc_mg");
    await userEvent.selectOptions(screen.getByLabelText("Art der Regel"), "max");
    await userEvent.type(screen.getByLabelText("Wert"), "25");
    await userEvent.type(screen.getByLabelText("Einheit"), "mg");
    await userEvent.selectOptions(screen.getByLabelText("Gilt pro"), "week");
    await userEvent.click(screen.getByLabelText("Harte Regel"));
    await userEvent.type(screen.getByLabelText("Quelle"), "Erfundene Quelle");
    await userEvent.click(screen.getByRole("button", { name: "Speichern" }));
    await waitFor(() => expect(server.calls.some((c) => c.method === "POST")).toBe(true));
    expect(server.calls.find((c) => c.method === "POST")?.body).toEqual({
      subject: "zinc_mg",
      kind: "max",
      value: 25,
      unit: "mg",
      per: "week",
      hard: false,
      enabled: true,
      doctor_confirmed: false,
      suggested_by_app: false,
      source: "Erfundene Quelle",
      note: null,
    });
    expect(await screen.findByRole("heading", { name: "Zink (mg)" })).toBeInTheDocument();
  });

  it("blendet Wert und Einheit bei „Meiden“ aus und sendet sie als null", async () => {
    const server = serverWith([SALT]);
    renderPage(<NutrientRulesPage />);
    await userEvent.click(await screen.findByRole("button", { name: "Regel hinzufügen" }));
    expect(screen.queryByLabelText("Wert")).not.toBeInTheDocument();
    await userEvent.selectOptions(screen.getByLabelText("Art der Regel"), "min");
    expect(screen.getByLabelText("Wert")).toBeInTheDocument();
    await userEvent.type(screen.getByLabelText("Wert"), "3");
    await userEvent.type(screen.getByLabelText("Einheit"), "g");
    await userEvent.selectOptions(screen.getByLabelText("Art der Regel"), "avoid");
    expect(screen.queryByLabelText("Wert")).not.toBeInTheDocument();
    expect(screen.queryByLabelText("Einheit")).not.toBeInTheDocument();
    await userEvent.type(screen.getByLabelText("Gegenstand"), "grapefruit");
    await userEvent.click(screen.getByRole("button", { name: "Speichern" }));
    await waitFor(() => expect(server.calls.some((c) => c.method === "POST")).toBe(true));
    expect(server.calls.find((c) => c.method === "POST")?.body).toMatchObject({
      subject: "grapefruit",
      kind: "avoid",
      value: null,
      unit: null,
    });
  });

  it("verlangt für Obergrenze, Untergrenze und Ziel einen Wert (wie der Server)", async () => {
    const server = serverWith([SALT]);
    renderPage(<NutrientRulesPage />);
    await userEvent.click(await screen.findByRole("button", { name: "Regel hinzufügen" }));
    await userEvent.type(screen.getByLabelText("Gegenstand"), "salt_g");
    await userEvent.click(screen.getByRole("button", { name: "Speichern" }));
    expect(screen.getByRole("alert")).toHaveTextContent("Bitte die Art der Regel wählen.");
    for (const kind of ["max", "min", "target"]) {
      await userEvent.selectOptions(screen.getByLabelText("Art der Regel"), kind);
      await userEvent.click(screen.getByRole("button", { name: "Speichern" }));
      expect(screen.getByRole("alert")).toHaveTextContent("Für diese Regelart ist ein Wert erforderlich.");
    }
    expect(server.calls.some((c) => c.method === "POST")).toBe(false);
  });

  it("akzeptiert den Wert 0 für eine Obergrenze", async () => {
    const server = serverWith([]);
    renderPage(<NutrientRulesPage />);
    await userEvent.click(await screen.findByRole("button", { name: "Erste Regel hinzufügen" }));
    await userEvent.type(screen.getByLabelText("Gegenstand"), "salt_g");
    await userEvent.selectOptions(screen.getByLabelText("Art der Regel"), "max");
    await userEvent.type(screen.getByLabelText("Wert"), "0");
    await userEvent.click(screen.getByRole("button", { name: "Speichern" }));
    await waitFor(() => expect(server.calls.some((c) => c.method === "POST")).toBe(true));
    expect(server.calls.find((c) => c.method === "POST")?.body).toMatchObject({ value: 0 });
  });

  it("bietet Gegenstandsvorschläge mit deutschen Namen an, ohne vorzubelegen", async () => {
    serverWith([SALT]);
    const { container } = renderPage(<NutrientRulesPage />);
    await userEvent.click(await screen.findByRole("button", { name: "Regel hinzufügen" }));
    const input = screen.getByLabelText("Gegenstand");
    expect(input).toHaveValue("");
    const opts = [...container.querySelectorAll(`datalist[id="${input.getAttribute("list")}"] option`)].map((o) => [
      o.getAttribute("value"),
      o.getAttribute("label"),
    ]);
    expect(opts).toContainEqual(["salt_g", "Salz (g)"]);
    expect(opts).toContainEqual(["licorice", "Lakritz"]);
    expect(opts).toHaveLength(9);
    expect(screen.getByLabelText("Art der Regel")).toHaveValue("");
  });

  it("zeigt die Servermeldung bei 422 in role=alert und lässt das Formular offen", async () => {
    serverWith([], {
      "POST /me/nutrient-rules": { status: 422, body: { detail: "Für diese Regelart ist ein Wert erforderlich." } },
    });
    renderPage(<NutrientRulesPage />);
    await userEvent.click(await screen.findByRole("button", { name: "Erste Regel hinzufügen" }));
    await userEvent.type(screen.getByLabelText("Gegenstand"), "salt_g");
    await userEvent.selectOptions(screen.getByLabelText("Art der Regel"), "avoid");
    await userEvent.click(screen.getByRole("button", { name: "Speichern" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("Für diese Regelart ist ein Wert erforderlich.");
    expect(screen.getByRole("form", { name: "Regel hinzufügen" })).toBeInTheDocument();
  });

  it("bearbeitet eine Regel (PUT) und behält suggested_by_app bei", async () => {
    const server = serverWith([SALT, FISH]);
    renderPage(<NutrientRulesPage />);
    await userEvent.click(await screen.findByRole("button", { name: "Fetter Fisch (Portionen) bearbeiten" }));
    expect(screen.getByLabelText("Art der Regel")).toHaveValue("target");
    expect(screen.getByLabelText("Wert")).toHaveValue(1.5);
    expect(screen.getByLabelText("Gilt pro")).toHaveValue("week");
    await userEvent.clear(screen.getByLabelText("Wert"));
    await userEvent.type(screen.getByLabelText("Wert"), "2");
    await userEvent.click(screen.getByRole("button", { name: "Speichern" }));
    await waitFor(() => expect(screen.queryByRole("form")).not.toBeInTheDocument());
    const put = server.calls.find((c) => c.method === "PUT");
    expect(put?.path).toBe("/me/nutrient-rules/2");
    expect(put?.body).toMatchObject({ value: 2, suggested_by_app: true, kind: "target", per: "week", hard: false });
  });

  it("schaltet „aktiv“ per PATCH um und lädt neu", async () => {
    const server = serverWith([SALT, FISH]);
    renderPage(<NutrientRulesPage />);
    const toggle = await screen.findByRole("checkbox", { name: "aktiv: Salz (g)" });
    expect(toggle).toBeChecked();
    await userEvent.click(toggle);
    await waitFor(() => expect(server.calls.some((c) => c.method === "PATCH")).toBe(true));
    const patch = server.calls.find((c) => c.method === "PATCH");
    expect(patch?.path).toBe("/me/nutrient-rules/1");
    expect(patch?.body).toEqual({ enabled: false });
    await waitFor(() => expect(screen.getByRole("checkbox", { name: "aktiv: Salz (g)" })).not.toBeChecked());
    expect(within(item("Salz (g)")).getByText("pausiert")).toBeInTheDocument();
  });

  it("bestätigt ärztlich per Schnellschalter und entfernt den App-Hinweis", async () => {
    const server = serverWith([SALT, FISH]);
    renderPage(<NutrientRulesPage />);
    const toggle = await screen.findByRole("checkbox", { name: "Arzt bestätigt: Fetter Fisch (Portionen)" });
    expect(toggle).not.toBeChecked();
    await userEvent.click(toggle);
    await waitFor(() => expect(server.calls.find((c) => c.method === "PATCH")?.body).toEqual({ doctor_confirmed: true }));
    expect(server.calls.find((c) => c.method === "PATCH")?.path).toBe("/me/nutrient-rules/2");
    await waitFor(() =>
      expect(within(item("Fetter Fisch (Portionen)")).queryByText(/Vorschlag der App/)).not.toBeInTheDocument(),
    );
    expect(within(item("Fetter Fisch (Portionen)")).getByText("Vom Arzt bestätigt")).toBeInTheDocument();
  });

  it("zeigt Fehler eines Schnellschalters", async () => {
    serverWith([SALT], { "PATCH /me/nutrient-rules/1": { status: 500, body: { detail: "Serverfehler." } } });
    renderPage(<NutrientRulesPage />);
    await userEvent.click(await screen.findByRole("checkbox", { name: "aktiv: Salz (g)" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("Serverfehler.");
    // Zustand bleibt wie auf dem Server
    expect(screen.getByRole("checkbox", { name: "aktiv: Salz (g)" })).toBeChecked();
  });

  it("sortiert wahlweise nach Art der Regel", async () => {
    serverWith([SALT, FISH, LICORICE]);
    renderPage(<NutrientRulesPage />);
    await screen.findByRole("list", { name: "Ernährungsregeln" });
    const names = () => within(screen.getByRole("list", { name: "Ernährungsregeln" })).getAllByRole("heading").map((h) => h.textContent);
    expect(names()).toEqual(["Fetter Fisch (Portionen)", "Lakritz", "Salz (g)"]);
    await userEvent.selectOptions(screen.getByLabelText("Sortieren nach"), "kind");
    expect(names()).toEqual(["Salz (g)", "Lakritz", "Fetter Fisch (Portionen)"]);
  });

  it("löscht nach Rückfrage", async () => {
    const server = serverWith([SALT, LICORICE]);
    renderPage(<NutrientRulesPage />);
    await userEvent.click(await screen.findByRole("button", { name: "Lakritz löschen" }));
    await userEvent.click(screen.getByRole("button", { name: "Ja, löschen" }));
    await waitFor(() => expect(server.calls.some((c) => c.method === "DELETE" && c.path === "/me/nutrient-rules/3")).toBe(true));
    await waitFor(() => expect(screen.queryByRole("heading", { name: "Lakritz" })).not.toBeInTheDocument());
  });
});
