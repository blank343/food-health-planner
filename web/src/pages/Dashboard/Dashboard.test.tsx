import { screen, within } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import type { components } from "../../api/schema";
import { dateDe, todayIso } from "../../format";
import { mockServer, renderPage } from "../../test/helpers";
import DashboardPage from "./index";

type Dash = components["schemas"]["DashboardOut"];

function daysAgo(n: number): string {
  const d = new Date();
  d.setDate(d.getDate() - n);
  return todayIso(d);
}

const EMPTY: Dash = {
  weight: { latest_kg: null, latest_date: null, trend_kg_per_week: null, trend_n_points: 0, points: [] },
  energy: { avg_active_kcal: null, avg_basal_kcal: null, device_tdee_kcal: null, n_days: 0, coverage: 0, last_day: null },
  workouts: [],
  data: [],
  labs: { latest_report_date: null, latest_report_type: null, flagged_count: 0, pending_count: 0 },
  imports: [],
};

function filled(latestWeightDaysAgo = 2): Dash {
  const latest = daysAgo(latestWeightDaysAgo);
  return {
    weight: {
      latest_kg: 80.5,
      latest_date: latest,
      trend_kg_per_week: -0.4,
      trend_n_points: 12,
      points: [
        { day: daysAgo(latestWeightDaysAgo + 14), kg: 81.6 },
        { day: daysAgo(latestWeightDaysAgo + 7), kg: 81.0 },
        { day: latest, kg: 80.5 },
      ],
    },
    energy: {
      avg_active_kcal: 600,
      avg_basal_kcal: 1800,
      device_tdee_kcal: 2400,
      n_days: 20,
      coverage: 0.71,
      last_day: daysAgo(1),
    },
    workouts: [
      { week_start: "2026-08-17", iso_week: "2026-W34", count: 2, total_minutes: 90, by_type: {} },
      { week_start: "2026-08-24", iso_week: "2026-W35", count: 0, total_minutes: 0, by_type: {} },
      { week_start: "2026-08-31", iso_week: "2026-W36", count: 3, total_minutes: 150, by_type: {} },
    ],
    data: [
      { source: "apple_health_xml", first_day: "2025-01-01", last_day: "2026-09-30", days: 400 },
      { source: "hae_zip", first_day: "2026-06-01", last_day: "2026-10-01", days: 90 },
      { source: "manual", first_day: "2026-09-01", last_day: "2026-09-02", days: 2 },
    ],
    labs: { latest_report_date: "2026-07-15", latest_report_type: "Blutbild", flagged_count: 2, pending_count: 1 },
    imports: [
      {
        id: 3, kind: "apple_health", filename: "export-test.zip", status: "done", progress: 1, message: null,
        stats: {}, error: null, created_at: "2026-10-01T08:00:00", started_at: null, finished_at: null,
      },
      {
        id: 2, kind: "hae", filename: "hae-test.zip", status: "failed", progress: 0.3, message: null,
        stats: {}, error: "Fehler", created_at: "2026-09-28T08:00:00", started_at: null, finished_at: null,
      },
    ],
  };
}

describe("Dashboard", () => {
  it("zeigt zuerst einen Ladehinweis", () => {
    mockServer({ "GET /me/dashboard": { body: EMPTY } });
    renderPage(<DashboardPage />);
    expect(screen.getByRole("status")).toHaveTextContent("Lädt");
  });

  it("zeigt bei leeren Daten einen freundlichen Hinweis mit Links", async () => {
    mockServer({ "GET /me/dashboard": { body: EMPTY } });
    renderPage(<DashboardPage />);
    expect(await screen.findByText("Noch keine Daten vorhanden.")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Zu den Importen" })).toHaveAttribute("href", "/importe");
    expect(screen.getByRole("link", { name: /Gewicht unter „Tagesziel“ eintragen/ })).toHaveAttribute("href", "/ziele");
    expect(screen.getByText(/Das Gewicht lässt sich auch von Hand eintragen/)).toBeInTheDocument();
    expect(screen.queryByRole("img")).not.toBeInTheDocument();
  });

  it("zeigt Kennzahlen im deutschen Format", async () => {
    mockServer({ "GET /me/dashboard": { body: filled() } });
    renderPage(<DashboardPage />);
    const stat = (await screen.findByText("Aktuelles Gewicht")).parentElement!;
    expect(within(stat).getByText("80,5 kg")).toBeInTheDocument();
    expect(screen.getByText(`vom ${dateDe(daysAgo(2))}`)).toBeInTheDocument();
    expect(screen.getByText("-0,40 kg")).toBeInTheDocument();
    expect(screen.getByText("2.400 kcal")).toBeInTheDocument();
    expect(screen.getByText(/Ø der letzten 20 Tage, Abdeckung 71 %/)).toBeInTheDocument();
    expect(screen.getByText("Workouts diese Woche")).toBeInTheDocument();
    expect(screen.getByText(/KW 36, 150 min/)).toBeInTheDocument();
    expect(screen.queryByText(/Tage alt/)).not.toBeInTheDocument();
  });

  it("zeigt beide Diagramme mit aussagekräftigen Beschriftungen", async () => {
    mockServer({ "GET /me/dashboard": { body: filled() } });
    renderPage(<DashboardPage />);
    await screen.findByText("Aktuelles Gewicht");
    const labels = screen.getAllByRole("img").map((i) => i.getAttribute("aria-label") ?? "");
    expect(labels).toHaveLength(2);
    expect(labels[0]).toContain("Gewicht: 3 Werte");
    expect(labels[0]).toContain("Zuletzt 80,5 kg");
    expect(labels[1]).toContain("insgesamt 5 Workouts und 240 Minuten");
  });

  it("zeigt die Datenabdeckung mit freundlichen Quellennamen", async () => {
    mockServer({ "GET /me/dashboard": { body: filled() } });
    renderPage(<DashboardPage />);
    const card = (await screen.findByRole("heading", { name: "Datenabdeckung" })).closest("section")!;
    expect(within(card).getByText("Apple Health")).toBeInTheDocument();
    expect(within(card).getByText("Health Auto Export")).toBeInTheDocument();
    expect(within(card).getByText("Manuell")).toBeInTheDocument();
    expect(within(card).getByText("01.01.2025")).toBeInTheDocument();
    expect(within(card).getByText("400")).toBeInTheDocument();
  });

  it("fasst das Labor zusammen und verlinkt dorthin", async () => {
    mockServer({ "GET /me/dashboard": { body: filled() } });
    renderPage(<DashboardPage />);
    const card = (await screen.findByRole("heading", { name: "Labor" })).closest("section")!;
    expect(within(card).getByText("15.07.2026")).toBeInTheDocument();
    expect(within(card).getByText("2 auffällige Werte")).toBeInTheDocument();
    expect(within(card).getByText("1 Wert ausstehend")).toBeInTheDocument();
    expect(within(card).getByRole("link", { name: "Zum Labor" })).toHaveAttribute("href", "/labor");
  });

  it("zeigt die letzten Importe mit Statusmarken", async () => {
    mockServer({ "GET /me/dashboard": { body: filled() } });
    renderPage(<DashboardPage />);
    const card = (await screen.findByRole("heading", { name: "Letzte Importe" })).closest("section")!;
    expect(within(card).getByText("Fertig")).toBeInTheDocument();
    expect(within(card).getByText("Fehlgeschlagen")).toHaveClass("error");
    expect(within(card).getByText("01.10.2026")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Zum Tagesziel" })).toHaveAttribute("href", "/ziele");
  });

  it("warnt, wenn das Gewicht älter als 30 Tage ist", async () => {
    mockServer({ "GET /me/dashboard": { body: filled(45) } });
    renderPage(<DashboardPage />);
    const alert = await screen.findByText(/Das letzte Gewicht ist 45 Tage alt/);
    expect(alert.closest(".alert")).toHaveClass("warn");
  });

  it("warnt nicht bei genau 30 Tagen", async () => {
    mockServer({ "GET /me/dashboard": { body: filled(30) } });
    renderPage(<DashboardPage />);
    await screen.findByText("Aktuelles Gewicht");
    expect(screen.queryByText(/Tage alt/)).not.toBeInTheDocument();
  });

  it("zeigt Serverfehler auf Deutsch", async () => {
    mockServer({ "GET /me/dashboard": { status: 500, body: {} } });
    renderPage(<DashboardPage />);
    expect(await screen.findByRole("alert")).toHaveTextContent("Serverfehler");
  });

  it("kommt mit Teildaten zurecht (kein Gewicht, nur Import)", async () => {
    const d: Dash = { ...EMPTY, imports: filled().imports.slice(0, 1) };
    mockServer({ "GET /me/dashboard": { body: d } });
    renderPage(<DashboardPage />);
    expect(await screen.findByText("Noch kein Gewicht")).toBeInTheDocument();
    expect(screen.getByText("Noch kein Laborbericht vorhanden.")).toBeInTheDocument();
    expect(screen.getByText("In den letzten 90 Tagen wurde kein Gewicht erfasst.")).toBeInTheDocument();
    expect(screen.getByText("Keine vollständigen Gerätedaten")).toBeInTheDocument();
  });
});
