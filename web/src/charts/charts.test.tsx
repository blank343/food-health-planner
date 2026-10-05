import { render, screen, within } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { BarChart } from "./BarChart";
import { LineChart } from "./LineChart";
import { niceTicks, paddedRange, shortDate } from "./scale";

describe("scale", () => {
  it("liefert runde Ticks innerhalb des Bereichs", () => {
    const ticks = niceTicks(79.2, 83.8, 4);
    expect(ticks.length).toBeGreaterThanOrEqual(2);
    for (const t of ticks) {
      expect(t).toBeGreaterThanOrEqual(79.2);
      expect(t).toBeLessThanOrEqual(83.8);
    }
  });

  it("gibt bei gleichen Werten einen sichtbaren Bereich zurück", () => {
    const [lo, hi] = paddedRange(80, 80);
    expect(hi - lo).toBeGreaterThan(0);
  });

  it("kürzt Datum auf Tag und Monat", () => {
    expect(shortDate("2026-10-05")).toBe("05.10.");
  });
});

describe("LineChart", () => {
  const points = [
    { x: "2026-08-01", y: 82.4 },
    { x: "2026-08-15", y: 81.9 },
    { x: "2026-09-01", y: 81.2 },
  ];

  it("hat role=img mit zusammenfassendem aria-label in deutschem Format", () => {
    render(<LineChart points={points} title="Gewicht" unit="kg" />);
    const img = screen.getByRole("img");
    const label = img.getAttribute("aria-label") ?? "";
    expect(label).toContain("Gewicht: 3 Werte von 01.08.2026 bis 01.09.2026");
    expect(label).toContain("Zuletzt 81,2 kg");
    expect(label).toContain("niedrigster Wert 81,2 kg");
    expect(label).toContain("höchster Wert 82,4 kg");
  });

  it("bietet eine Datentabelle als Alternative", () => {
    render(<LineChart points={points} title="Gewicht" unit="kg" tableHeaders={["Datum", "Gewicht"]} />);
    expect(screen.getByText("Werte als Tabelle anzeigen")).toBeInTheDocument();
    const table = screen.getByRole("table", { hidden: true });
    expect(within(table).getAllByRole("row", { hidden: true })).toHaveLength(4);
    expect(within(table).getByText("15.08.2026")).toBeInTheDocument();
    expect(within(table).getByText("82,4 kg")).toBeInTheDocument();
  });

  it("sortiert unsortierte Punkte nach Datum", () => {
    render(<LineChart points={[...points].reverse()} title="Gewicht" unit="kg" />);
    expect(screen.getByRole("img").getAttribute("aria-label")).toContain("von 01.08.2026 bis 01.09.2026");
  });

  it("zeichnet auch einen einzelnen Wert", () => {
    render(<LineChart points={[{ x: "2026-09-01", y: 80 }]} title="Gewicht" unit="kg" />);
    expect(screen.getByRole("img").getAttribute("aria-label")).toContain("1 Wert am 01.09.2026");
  });

  it("zeigt bei leeren Daten einen Hinweis statt einer Grafik", () => {
    render(<LineChart points={[]} title="Gewicht" />);
    expect(screen.queryByRole("img")).not.toBeInTheDocument();
    expect(screen.getByText("Keine Werte vorhanden.")).toBeInTheDocument();
  });

  it("verwendet nur Farbvariablen und keine Schrift unter 12 px", () => {
    const { container } = render(<LineChart points={points} title="Gewicht" unit="kg" />);
    expect(container.innerHTML).not.toMatch(/#[0-9a-f]{3,6}/i);
    expect(container.querySelector("svg")?.getAttribute("viewBox")).toMatch(/^0 0 \d+ 220$/);
  });
});

describe("BarChart", () => {
  const bars = [
    { label: "40", longLabel: "KW 40", value: 2, extra: 90 },
    { label: "41", longLabel: "KW 41", value: 0, extra: 0 },
    { label: "42", longLabel: "KW 42", value: 3, extra: 150 },
  ];

  it("fasst Anzahl und Minuten im aria-label zusammen", () => {
    render(<BarChart bars={bars} title="Workouts pro Woche" unit="Workouts" extraUnit="Minuten" />);
    const label = screen.getByRole("img").getAttribute("aria-label") ?? "";
    expect(label).toContain("insgesamt 5 Workouts und 240 Minuten");
    expect(label).toContain("KW 42: 3 Workouts, 150 Minuten");
  });

  it("enthält eine Tabelle mit Minuten", () => {
    render(
      <BarChart
        bars={bars}
        title="Workouts pro Woche"
        unit="Workouts"
        extraUnit="Minuten"
        tableHeaders={["Woche", "Workouts", "Minuten"]}
      />,
    );
    const table = screen.getByRole("table", { hidden: true });
    expect(within(table).getByRole("columnheader", { name: "Minuten", hidden: true })).toBeInTheDocument();
    expect(within(table).getAllByRole("row", { hidden: true })).toHaveLength(4);
  });

  it("kommt mit lauter Nullen zurecht", () => {
    render(<BarChart bars={[{ label: "1", value: 0 }, { label: "2", value: 0 }]} title="Test" unit="Stück" />);
    expect(screen.getByRole("img").getAttribute("aria-label")).toContain("insgesamt 0 Stück");
  });

  it("zeigt bei leeren Daten einen Hinweis", () => {
    render(<BarChart bars={[]} title="Test" />);
    expect(screen.queryByRole("img")).not.toBeInTheDocument();
  });
});
