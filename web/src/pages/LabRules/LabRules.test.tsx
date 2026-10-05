import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";
import { mockServer, renderPage } from "../../test/helpers";
import LabRulesPage, { conditionText } from "./index";

type Rule = {
  id: number;
  name: string;
  analyte: string;
  comparator: "lt" | "gt" | "between" | "outside_ref";
  threshold_low: number | null;
  threshold_high: number | null;
  effect_key: string;
  effect_weight: number;
  enabled: boolean;
  doctor_confirmed: boolean;
  suggested_by_app: boolean;
  source: string | null;
  note: string | null;
};

const base = { enabled: true, doctor_confirmed: false, suggested_by_app: false, source: null, note: null, effect_weight: 0.5 } as const;

const LOW: Rule = { ...base, id: 1, name: "Testwert niedrig", analyte: "Analyt Alpha", comparator: "lt", threshold_low: null, threshold_high: 1.2, effect_key: "boost_iron_vitc", doctor_confirmed: true, effect_weight: 0.8 };
const BETWEEN: Rule = { ...base, id: 2, name: "Testbereich", analyte: "Analyt Beta", comparator: "between", threshold_low: 10, threshold_high: 30, effect_key: "eigener_schluessel", suggested_by_app: true, enabled: false };
const OUTSIDE: Rule = { ...base, id: 3, name: "Referenzregel", analyte: "Analyt Gamma", comparator: "outside_ref", threshold_low: null, threshold_high: null, effect_key: "limit_sodium", note: "Testnotiz" };
const GREATER: Rule = { ...base, id: 4, name: "Testwert hoch", analyte: "Analyt Delta", comparator: "gt", threshold_low: 5, threshold_high: null, effect_key: "boost_fiber" };

function serverWith(initial: Rule[], extra: Parameters<typeof mockServer>[0] = {}) {
  let list = [...initial];
  const patchHandler = (id: number) => ({ body }: { body: unknown }) => {
    list = list.map((r) => (r.id === id ? { ...r, ...(body as object) } : r));
    return { body: list.find((r) => r.id === id) };
  };
  return mockServer({
    "GET /me/lab-rules": () => ({ body: list }),
    "GET /me/labs/latest": {
      body: [
        { analyte: "Analyt Zeta", unit: "u", value: 1, value_op: null, flag: null, ref_low: null, ref_high: null, ref_op: null, report_id: 1, report_date: null },
        { analyte: "Analyt Alpha", unit: "u", value: 2, value_op: null, flag: null, ref_low: null, ref_high: null, ref_op: null, report_id: 1, report_date: null },
      ],
    },
    "POST /me/lab-rules": ({ body }) => {
      const created = { id: 99, ...(body as object) } as Rule;
      list = [...list, created];
      return { status: 201, body: created };
    },
    "PUT /me/lab-rules/1": ({ body }) => {
      const updated = { id: 1, ...(body as object) } as Rule;
      list = list.map((r) => (r.id === 1 ? updated : r));
      return { body: updated };
    },
    "PATCH /me/lab-rules/1": patchHandler(1),
    "PATCH /me/lab-rules/2": patchHandler(2),
    "DELETE /me/lab-rules/3": () => {
      list = list.filter((r) => r.id !== 3);
      return { status: 200 };
    },
    ...extra,
  });
}

const item = (name: string) => screen.getByRole("heading", { name }).closest("li") as HTMLElement;
const post = (s: ReturnType<typeof mockServer>) => s.calls.find((c) => c.method === "POST");

describe("conditionText", () => {
  it("beschreibt Bedingungen in Worten", () => {
    expect(conditionText({ comparator: "lt", threshold_low: null, threshold_high: 1.2 })).toBe("Wert unter 1,2");
    expect(conditionText({ comparator: "gt", threshold_low: 5, threshold_high: null })).toBe("Wert über 5");
    expect(conditionText({ comparator: "between", threshold_low: 10, threshold_high: 30 })).toBe("Wert zwischen 10 und 30");
    expect(conditionText({ comparator: "outside_ref", threshold_low: null, threshold_high: null })).toBe(
      "Wert außerhalb des Referenzbereichs",
    );
    // Rückfall, falls ein Datensatz die andere Seite nutzt
    expect(conditionText({ comparator: "lt", threshold_low: 3, threshold_high: null })).toBe("Wert unter 3");
  });
});

describe("Laborregeln", () => {
  it("zeigt Regeln mit Analyt, Bedingung, Wirkung, Gewicht und Badges", async () => {
    serverWith([LOW, BETWEEN, OUTSIDE, GREATER]);
    renderPage(<LabRulesPage />);
    await screen.findByRole("list", { name: "Laborregeln" });

    const low = within(item("Testwert niedrig"));
    expect(low.getByText("Analyt Alpha")).toBeInTheDocument();
    expect(low.getByText("Wert unter 1,2")).toBeInTheDocument();
    expect(low.getByText(/Eisen mit Vitamin C kombinieren/)).toBeInTheDocument();
    expect(low.getByText("Gewicht 0,8")).toBeInTheDocument();
    expect(low.getByText("Vom Arzt bestätigt")).toBeInTheDocument();

    const between = within(item("Testbereich"));
    expect(between.getByText("Wert zwischen 10 und 30")).toBeInTheDocument();
    expect(between.getByText("Wirkung: eigener_schluessel")).toBeInTheDocument();
    expect(between.getByText("pausiert")).toBeInTheDocument();
    expect(between.getByText("Vorschlag der App – bitte ärztlich bestätigen")).toBeInTheDocument();

    const outside = within(item("Referenzregel"));
    expect(outside.getByText("Wert außerhalb des Referenzbereichs")).toBeInTheDocument();
    expect(outside.getByText("Testnotiz")).toBeInTheDocument();
    expect(outside.queryByText("Vom Arzt bestätigt")).not.toBeInTheDocument();

    expect(within(item("Testwert hoch")).getByText("Wert über 5")).toBeInTheDocument();
  });

  it("weist darauf hin, dass nur sanfte Ziele entstehen und nie diagnostiziert wird", async () => {
    serverWith([LOW]);
    renderPage(<LabRulesPage />);
    expect(await screen.findByText(/nur sanfte Planungsziele und stellen niemals eine Diagnose/)).toBeInTheDocument();
  });

  it("zeigt einen leeren Zustand mit Aktion", async () => {
    serverWith([]);
    renderPage(<LabRulesPage />);
    expect(await screen.findByText(/Noch keine Laborregeln/)).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "Erste Laborregel hinzufügen" }));
    expect(screen.getByRole("form", { name: "Laborregel hinzufügen" })).toBeInTheDocument();
  });

  it("lädt Analytnamen aus den Laborwerten als Vorschläge (sortiert) und ignoriert Fehler", async () => {
    serverWith([LOW]);
    const { container, unmount } = renderPage(<LabRulesPage />);
    await screen.findByRole("list", { name: "Laborregeln" });
    await userEvent.click(screen.getByRole("button", { name: "Laborregel hinzufügen" }));
    const input = screen.getByLabelText("Analyt (Laborwert)");
    expect(input).toHaveValue("");
    await waitFor(() => {
      const values = [...container.querySelectorAll(`datalist[id="${input.getAttribute("list")}"] option`)].map((o) => o.getAttribute("value"));
      expect(values).toEqual(["Analyt Alpha", "Analyt Zeta"]);
    });
    unmount();

    serverWith([LOW], { "GET /me/labs/latest": { status: 500, body: { detail: "kaputt" } } });
    const second = renderPage(<LabRulesPage />);
    await screen.findByRole("list", { name: "Laborregeln" });
    await userEvent.click(screen.getByRole("button", { name: "Laborregel hinzufügen" }));
    const input2 = screen.getByLabelText("Analyt (Laborwert)");
    expect(second.container.querySelectorAll(`datalist[id="${input2.getAttribute("list")}"] option`)).toHaveLength(0);
    expect(screen.queryByText("kaputt")).not.toBeInTheDocument();
    // Freie Eingabe bleibt möglich
    await userEvent.type(input2, "Analyt Eigen");
    expect(input2).toHaveValue("Analyt Eigen");
  });

  it("zeigt Schwellenwerte abhängig von der Bedingung", async () => {
    serverWith([LOW]);
    renderPage(<LabRulesPage />);
    await userEvent.click(await screen.findByRole("button", { name: "Laborregel hinzufügen" }));
    const cmp = screen.getByLabelText("Bedingung");
    expect(cmp).toHaveValue("");
    expect(screen.queryByLabelText("Schwellenwert")).not.toBeInTheDocument();
    expect(screen.queryByLabelText("Untere Grenze")).not.toBeInTheDocument();

    await userEvent.selectOptions(cmp, "lt");
    expect(screen.getByLabelText("Schwellenwert")).toBeInTheDocument();
    expect(screen.queryByLabelText("Untere Grenze")).not.toBeInTheDocument();
    await userEvent.selectOptions(cmp, "gt");
    expect(screen.getByLabelText("Schwellenwert")).toBeInTheDocument();
    await userEvent.selectOptions(cmp, "between");
    expect(screen.queryByLabelText("Schwellenwert")).not.toBeInTheDocument();
    expect(screen.getByLabelText("Untere Grenze")).toBeInTheDocument();
    expect(screen.getByLabelText("Obere Grenze")).toBeInTheDocument();
    await userEvent.selectOptions(cmp, "outside_ref");
    expect(screen.queryByLabelText("Untere Grenze")).not.toBeInTheDocument();
    expect(screen.getByText(/außerhalb des Referenzbereichs aus dem Laborbericht/)).toBeInTheDocument();
    expect(within(cmp).getByRole("option", { name: "kleiner als" })).toBeInTheDocument();
    expect(within(cmp).getByRole("option", { name: "außerhalb des Referenzbereichs" })).toBeInTheDocument();
  });

  async function fillCommon(name = "Neue Regel") {
    await userEvent.type(screen.getByLabelText("Name"), name);
    await userEvent.type(screen.getByLabelText("Analyt (Laborwert)"), "Analyt Eta");
    await userEvent.type(screen.getByLabelText("Wirkung"), "boost_fiber");
  }

  it("legt „kleiner als“ mit threshold_high an", async () => {
    const server = serverWith([LOW]);
    renderPage(<LabRulesPage />);
    await userEvent.click(await screen.findByRole("button", { name: "Laborregel hinzufügen" }));
    await fillCommon();
    await userEvent.selectOptions(screen.getByLabelText("Bedingung"), "lt");
    await userEvent.type(screen.getByLabelText("Schwellenwert"), "1.5");
    await userEvent.click(screen.getByRole("button", { name: "Speichern" }));
    await waitFor(() => expect(post(server)).toBeDefined());
    expect(post(server)?.body).toEqual({
      name: "Neue Regel",
      analyte: "Analyt Eta",
      comparator: "lt",
      threshold_low: null,
      threshold_high: 1.5,
      effect_key: "boost_fiber",
      effect_weight: 0.5,
      enabled: true,
      doctor_confirmed: false,
      suggested_by_app: false,
      source: null,
      note: null,
    });
    expect(await screen.findByRole("heading", { name: "Neue Regel" })).toBeInTheDocument();
  });

  it("legt „größer als“ mit threshold_low an", async () => {
    const server = serverWith([LOW]);
    renderPage(<LabRulesPage />);
    await userEvent.click(await screen.findByRole("button", { name: "Laborregel hinzufügen" }));
    await fillCommon();
    await userEvent.selectOptions(screen.getByLabelText("Bedingung"), "gt");
    await userEvent.type(screen.getByLabelText("Schwellenwert"), "7");
    await userEvent.click(screen.getByRole("button", { name: "Speichern" }));
    await waitFor(() => expect(post(server)).toBeDefined());
    expect(post(server)?.body).toMatchObject({ comparator: "gt", threshold_low: 7, threshold_high: null });
  });

  it("„zwischen“ braucht beide Grenzen und untere <= obere", async () => {
    const server = serverWith([LOW]);
    renderPage(<LabRulesPage />);
    await userEvent.click(await screen.findByRole("button", { name: "Laborregel hinzufügen" }));
    await fillCommon();
    await userEvent.selectOptions(screen.getByLabelText("Bedingung"), "between");
    await userEvent.type(screen.getByLabelText("Untere Grenze"), "10");
    await userEvent.click(screen.getByRole("button", { name: "Speichern" }));
    expect(screen.getByRole("alert")).toHaveTextContent("untere und obere Grenze erforderlich");

    await userEvent.type(screen.getByLabelText("Obere Grenze"), "5");
    await userEvent.click(screen.getByRole("button", { name: "Speichern" }));
    expect(screen.getByRole("alert")).toHaveTextContent("untere Grenze darf nicht größer als die obere sein");
    expect(post(server)).toBeUndefined();

    await userEvent.clear(screen.getByLabelText("Obere Grenze"));
    await userEvent.type(screen.getByLabelText("Obere Grenze"), "30");
    await userEvent.click(screen.getByRole("button", { name: "Speichern" }));
    await waitFor(() => expect(post(server)).toBeDefined());
    expect(post(server)?.body).toMatchObject({ comparator: "between", threshold_low: 10, threshold_high: 30 });
  });

  it("„außerhalb des Referenzbereichs“ sendet keine Schwellenwerte, auch nach Wechsel der Bedingung", async () => {
    const server = serverWith([LOW]);
    renderPage(<LabRulesPage />);
    await userEvent.click(await screen.findByRole("button", { name: "Laborregel hinzufügen" }));
    await fillCommon();
    await userEvent.selectOptions(screen.getByLabelText("Bedingung"), "lt");
    await userEvent.type(screen.getByLabelText("Schwellenwert"), "4");
    await userEvent.selectOptions(screen.getByLabelText("Bedingung"), "outside_ref");
    await userEvent.click(screen.getByRole("button", { name: "Speichern" }));
    await waitFor(() => expect(post(server)).toBeDefined());
    expect(post(server)?.body).toMatchObject({ comparator: "outside_ref", threshold_low: null, threshold_high: null });
  });

  it("verlangt Schwellenwert, Namen, Analyt, Wirkung und ein Gewicht von 0 bis 1", async () => {
    const server = serverWith([LOW]);
    renderPage(<LabRulesPage />);
    await userEvent.click(await screen.findByRole("button", { name: "Laborregel hinzufügen" }));
    const save = () => userEvent.click(screen.getByRole("button", { name: "Speichern" }));
    await save();
    expect(screen.getByRole("alert")).toHaveTextContent("Bitte einen Namen angeben.");
    await userEvent.type(screen.getByLabelText("Name"), "X");
    await save();
    expect(screen.getByRole("alert")).toHaveTextContent("Bitte den Analyten");
    await userEvent.type(screen.getByLabelText("Analyt (Laborwert)"), "A");
    await save();
    expect(screen.getByRole("alert")).toHaveTextContent("Bitte die Bedingung wählen.");
    await userEvent.selectOptions(screen.getByLabelText("Bedingung"), "gt");
    await save();
    expect(screen.getByRole("alert")).toHaveTextContent("Bitte einen Schwellenwert angeben.");
    await userEvent.type(screen.getByLabelText("Schwellenwert"), "1");
    await save();
    expect(screen.getByRole("alert")).toHaveTextContent("Bitte die Wirkung angeben.");
    await userEvent.type(screen.getByLabelText("Wirkung"), "boost_fiber");
    await userEvent.clear(screen.getByLabelText("Gewicht (0 bis 1)"));
    await userEvent.type(screen.getByLabelText("Gewicht (0 bis 1)"), "1.5");
    await save();
    expect(screen.getByRole("alert")).toHaveTextContent("Das Gewicht muss zwischen 0 und 1 liegen.");
    expect(post(server)).toBeUndefined();
  });

  it("bietet Wirkungsvorschläge mit deutschen Namen an, erlaubt aber freien Text", async () => {
    serverWith([LOW]);
    const { container } = renderPage(<LabRulesPage />);
    await userEvent.click(await screen.findByRole("button", { name: "Laborregel hinzufügen" }));
    const input = screen.getByLabelText("Wirkung");
    expect(input).toHaveValue("");
    const opts = [...container.querySelectorAll(`datalist[id="${input.getAttribute("list")}"] option`)].map((o) => o.getAttribute("value"));
    expect(opts).toEqual(["boost_iron_vitc", "boost_vitamin_d", "limit_sodium", "boost_unsaturated_fat", "boost_fiber"]);
    await userEvent.type(input, "mein_schluessel");
    expect(input).toHaveValue("mein_schluessel");
  });

  it("zeigt die Servermeldung bei 422", async () => {
    serverWith([LOW], {
      "POST /me/lab-rules": { status: 422, body: { detail: [{ loc: ["body"], msg: "Value error, threshold_low darf nicht größer als threshold_high sein." }] } },
    });
    renderPage(<LabRulesPage />);
    await userEvent.click(await screen.findByRole("button", { name: "Laborregel hinzufügen" }));
    await fillCommon();
    await userEvent.selectOptions(screen.getByLabelText("Bedingung"), "outside_ref");
    await userEvent.click(screen.getByRole("button", { name: "Speichern" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("threshold_low darf nicht größer als threshold_high sein.");
    expect(screen.getByRole("alert")).not.toHaveTextContent("Value error");
    expect(screen.getByRole("form", { name: "Laborregel hinzufügen" })).toBeInTheDocument();
  });

  it("bearbeitet eine Regel (PUT) und füllt das Formular mit den gespeicherten Werten", async () => {
    const server = serverWith([LOW]);
    renderPage(<LabRulesPage />);
    await userEvent.click(await screen.findByRole("button", { name: "Testwert niedrig bearbeiten" }));
    expect(screen.getByLabelText("Bedingung")).toHaveValue("lt");
    expect(screen.getByLabelText("Schwellenwert")).toHaveValue(1.2);
    expect(screen.getByLabelText("Gewicht (0 bis 1)")).toHaveValue(0.8);
    expect(screen.getByLabelText("Vom Arzt bestätigt")).toBeChecked();
    await userEvent.selectOptions(screen.getByLabelText("Bedingung"), "between");
    // der bisherige Schwellenwert (threshold_high) bleibt als obere Grenze stehen
    expect(screen.getByLabelText("Obere Grenze")).toHaveValue(1.2);
    expect(screen.getByLabelText("Untere Grenze")).toHaveValue(null);
    await userEvent.type(screen.getByLabelText("Untere Grenze"), "0.5");
    await userEvent.click(screen.getByRole("button", { name: "Speichern" }));
    await waitFor(() => expect(server.calls.some((c) => c.method === "PUT")).toBe(true));
    const put = server.calls.find((c) => c.method === "PUT");
    expect(put?.path).toBe("/me/lab-rules/1");
    expect(put?.body).toMatchObject({ comparator: "between", threshold_low: 0.5, threshold_high: 1.2, doctor_confirmed: true, effect_weight: 0.8 });
  });

  it("schaltet aktiv und Arzt bestätigt per PATCH um", async () => {
    const server = serverWith([LOW, BETWEEN]);
    renderPage(<LabRulesPage />);
    const confirm = await screen.findByRole("checkbox", { name: "Arzt bestätigt: Testbereich" });
    expect(confirm).not.toBeChecked();
    await userEvent.click(confirm);
    await waitFor(() => expect(server.calls.find((c) => c.method === "PATCH")?.body).toEqual({ doctor_confirmed: true }));
    expect(server.calls.find((c) => c.method === "PATCH")?.path).toBe("/me/lab-rules/2");
    await waitFor(() => expect(within(item("Testbereich")).queryByText(/Vorschlag der App/)).not.toBeInTheDocument());

    const active = screen.getByRole("checkbox", { name: "aktiv: Testwert niedrig" });
    expect(active).toBeChecked();
    await userEvent.click(active);
    await waitFor(() => expect(server.calls.filter((c) => c.method === "PATCH")).toHaveLength(2));
    expect(server.calls.filter((c) => c.method === "PATCH")[1]?.body).toEqual({ enabled: false });
    await waitFor(() => expect(within(item("Testwert niedrig")).getByText("pausiert")).toBeInTheDocument());
  });

  it("löscht nach Rückfrage", async () => {
    const server = serverWith([LOW, OUTSIDE]);
    renderPage(<LabRulesPage />);
    await userEvent.click(await screen.findByRole("button", { name: "Referenzregel löschen" }));
    await userEvent.click(screen.getByRole("button", { name: "Ja, löschen" }));
    await waitFor(() => expect(server.calls.some((c) => c.method === "DELETE" && c.path === "/me/lab-rules/3")).toBe(true));
    await waitFor(() => expect(screen.queryByRole("heading", { name: "Referenzregel" })).not.toBeInTheDocument());
  });
});
