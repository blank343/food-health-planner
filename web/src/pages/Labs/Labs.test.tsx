import { screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";
import { mockServer, renderPage } from "../../test/helpers";
import type { LabReport, LabResult, LatestLabValue } from "./labFormat";
import LabsPage from "./index";

// Nur erfundene Werte.
const latest: LatestLabValue[] = [
  { analyte: "Leukozyten", unit: "/nl", value: 11.2, value_op: null, flag: "H", ref_low: 3.7, ref_high: 9.9, ref_op: null, report_id: 1, report_date: "2026-09-20" },
  { analyte: "CRP", unit: "mg/l", value: 0.6, value_op: "<", flag: null, ref_low: null, ref_high: 5.0, ref_op: "<", report_id: 1, report_date: "2026-09-20" },
  { analyte: "Ferritin", unit: "µg/l", value: 12, value_op: null, flag: "L", ref_low: 30, ref_high: 400, ref_op: null, report_id: 2, report_date: "2026-08-01" },
  { analyte: "Testwert Alpha", unit: "U/l", value: 45.4, value_op: ">", flag: null, ref_low: 1.2, ref_high: null, ref_op: ">", report_id: 2, report_date: "2026-08-01" },
  { analyte: "Cholesterin gesamt", unit: "mg/dl", value: 180, value_op: null, flag: null, ref_low: null, ref_high: 200, ref_op: "<", report_id: 2, report_date: "2026-08-01" },
];

function result(id: number, over: Partial<LabResult>): LabResult {
  return {
    id,
    analyte: "X",
    unit: "",
    value: null,
    value_op: null,
    flag: null,
    ref_low: null,
    ref_high: null,
    ref_op: null,
    pending: false,
    method: null,
    material: null,
    ...over,
  };
}

const teilbefund: LabReport = {
  id: 1,
  order_no: "A-100",
  lab_name: "Musterlabor Nord",
  report_type: "Teilbefund",
  sample_datetime: "2026-09-20T07:30:00",
  source_filename: "teil.pdf",
  created_at: "2026-09-21T10:00:00",
  results: [
    result(1, { analyte: "Leukozyten", unit: "/nl", value: 11.2, flag: "H", ref_low: 3.7, ref_high: 9.9 }),
    result(2, { analyte: "CRP", unit: "mg/l", value: 0.6, value_op: "<", ref_high: 5.0, ref_op: "<" }),
    result(3, { analyte: "Zink", unit: "µg/dl", pending: true, ref_low: 70, ref_high: 120 }),
  ],
};
const endbefund: LabReport = {
  id: 2,
  order_no: "A-099",
  lab_name: null,
  report_type: "Endbefund",
  sample_datetime: "2026-08-01T08:00:00",
  source_filename: "end.pdf",
  created_at: "2026-08-02T10:00:00",
  results: [
    result(4, { analyte: "Ferritin", unit: "µg/l", value: 12, flag: "L", ref_low: 30, ref_high: 400 }),
    result(5, { analyte: "Testwert Alpha", unit: "U/l", value: 45.4, value_op: ">", ref_low: 1.2, ref_op: ">" }),
    result(6, { analyte: "Cholesterin gesamt", unit: "mg/dl", value: 180, ref_high: 200, ref_op: "<" }),
  ],
};

const card = (name: string) => screen.getByRole("heading", { name }).closest("section") as HTMLElement;
const rowOf = (name: string) => within(card("Aktuelle Werte")).getByRole("row", { name: new RegExp(`^${name}`) });

function serve() {
  return mockServer({
    "GET /me/labs/latest": { body: latest },
    "GET /me/labs": { body: [teilbefund, endbefund] },
    "GET /me/labs?pending=true": {
      body: [{ ...teilbefund, results: [teilbefund.results[2]] }],
    },
  });
}

describe("Labor", () => {
  it("zeigt aktuelle Werte mit Operatoren, Einheit, Referenz in Worten und Datum", async () => {
    serve();
    renderPage(<LabsPage />);
    await screen.findByRole("heading", { name: "Aktuelle Werte" });
    expect(rowOf("Leukozyten")).toHaveTextContent("11,2/nl3,7–9,9zu hoch20.09.2026");
    expect(rowOf("CRP")).toHaveTextContent("<0,6mg/l< 5,0");
    expect(rowOf("Testwert Alpha")).toHaveTextContent(">45,4U/l> 1,2");
    expect(rowOf("Ferritin")).toHaveTextContent("12,0µg/l30,0–400zu niedrig01.08.2026");
    expect(rowOf("Cholesterin gesamt")).toHaveTextContent("180mg/dl< 200");
    expect(screen.getByText(/Die App stellt keine Diagnosen\. Auffällige Werte bitte mit der Ärztin oder dem Arzt besprechen\./)).toBeInTheDocument();
  });

  it("kennzeichnet auffällige Werte mit Text, nicht nur mit Farbe", async () => {
    serve();
    renderPage(<LabsPage />);
    await screen.findByRole("heading", { name: "Aktuelle Werte" });
    const table = within(card("Aktuelle Werte"));
    expect(table.getAllByText("zu hoch")).toHaveLength(1);
    expect(table.getAllByText("zu niedrig")).toHaveLength(1);
  });

  it("zeigt Berichte aufklappbar mit ausstehenden Werten", async () => {
    serve();
    renderPage(<LabsPage />);
    await screen.findByRole("heading", { name: "Berichte" });
    const reports = within(card("Berichte"));
    const first = reports.getByText("20.09.2026").closest("details") as HTMLElement;
    expect(within(first).getByText("Teilbefund")).toBeInTheDocument();
    expect(within(first).getByText("Musterlabor Nord")).toBeInTheDocument();
    expect(within(first).getByText("3 Werte, 1 ausstehend")).toBeInTheDocument();
    expect(first).not.toHaveAttribute("open");
    await userEvent.click(within(first).getByText("Musterlabor Nord"));
    expect(first).toHaveAttribute("open");
    const zink = within(first).getByRole("row", { name: /Zink/ });
    expect(zink).toHaveTextContent("Wert steht noch aus");
    expect(zink).toHaveTextContent("70,0–120");
    expect(zink).toHaveTextContent("ausstehend");
    const second = reports.getByText("01.08.2026").closest("details") as HTMLElement;
    expect(within(second).getByText("Endbefund")).toBeInTheDocument();
    expect(within(second).getByText("Labor unbekannt")).toBeInTheDocument();
    expect(within(second).getByText("3 Werte, 0 ausstehend")).toBeInTheDocument();
  });

  it("filtert nach Suchtext", async () => {
    serve();
    renderPage(<LabsPage />);
    await screen.findByRole("heading", { name: "Aktuelle Werte" });
    await userEvent.type(screen.getByLabelText("Analyt suchen"), "chol");
    const section = within(card("Aktuelle Werte"));
    expect(section.getByRole("row", { name: /Cholesterin gesamt/ })).toBeInTheDocument();
    expect(section.queryByRole("row", { name: /^Leukozyten/ })).not.toBeInTheDocument();
    await userEvent.clear(screen.getByLabelText("Analyt suchen"));
    await userEvent.type(screen.getByLabelText("Analyt suchen"), "gibtesnicht");
    expect(section.getByText("Keine passenden Werte.")).toBeInTheDocument();
  });

  it("zeigt mit „Nur auffällige“ nur Werte mit Kennzeichen", async () => {
    serve();
    renderPage(<LabsPage />);
    await screen.findByRole("heading", { name: "Aktuelle Werte" });
    await userEvent.click(screen.getByLabelText("Nur auffällige"));
    const section = within(card("Aktuelle Werte"));
    expect(section.getByRole("row", { name: /^Leukozyten/ })).toBeInTheDocument();
    expect(section.getByRole("row", { name: /^Ferritin/ })).toBeInTheDocument();
    expect(section.queryByRole("row", { name: /^CRP/ })).not.toBeInTheDocument();
    expect(section.queryByRole("row", { name: /^Cholesterin/ })).not.toBeInTheDocument();
  });

  it("zeigt mit „Nur ausstehende“ die offenen Werte aus den Berichten", async () => {
    const server = serve();
    renderPage(<LabsPage />);
    await screen.findByRole("heading", { name: "Aktuelle Werte" });
    expect(server.calls.some((c) => c.path === "/me/labs?pending=true")).toBe(false);
    await userEvent.click(screen.getByLabelText("Nur ausstehende"));
    const section = within(card("Aktuelle Werte"));
    const zink = await section.findByRole("row", { name: /^Zink/ });
    expect(zink).toHaveTextContent("Wert steht noch aus");
    expect(zink).toHaveTextContent("20.09.2026");
    expect(section.queryByRole("row", { name: /^Leukozyten/ })).not.toBeInTheDocument();
    expect(server.calls.some((c) => c.path === "/me/labs?pending=true")).toBe(true);

    // Beide Filter: wie im Server gilt „mindestens eines“.
    await userEvent.click(screen.getByLabelText("Nur auffällige"));
    expect(section.getByRole("row", { name: /^Zink/ })).toBeInTheDocument();
    expect(section.getByRole("row", { name: /^Ferritin/ })).toBeInTheDocument();
    expect(section.queryByRole("row", { name: /^CRP/ })).not.toBeInTheDocument();
  });

  it("zeigt ohne Befunde einen freundlichen Hinweis mit Link zu den Importen", async () => {
    mockServer({ "GET /me/labs/latest": { body: [] }, "GET /me/labs": { body: [] } });
    renderPage(<LabsPage />);
    expect(await screen.findByText("Noch keine Laborwerte vorhanden.")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Importe" })).toHaveAttribute("href", "/importe");
    expect(screen.queryByLabelText("Analyt suchen")).not.toBeInTheDocument();
  });

  it("zeigt einen Fehler, wenn der Server nicht antwortet", async () => {
    mockServer({
      "GET /me/labs/latest": { status: 500, body: { detail: "Serverfehler. Bitte später erneut versuchen." } },
      "GET /me/labs": { body: [] },
    });
    renderPage(<LabsPage />);
    expect(await screen.findByRole("alert")).toHaveTextContent("Serverfehler");
  });
});
