import { useRef } from "react";
import { dateDe, num } from "../format";
import "./charts.css";
import { dayNumber, niceTicks, paddedRange, shortDate } from "./scale";
import { useChartWidth } from "./useChartWidth";

export type LinePoint = { x: string; y: number };

type Props = {
  /** Messpunkte, `x` als ISO-Datum (`2026-10-05`). */
  points: LinePoint[];
  /** Kurzer Titel für die Vorlesehilfe, z. B. „Gewicht“. */
  title: string;
  unit?: string;
  digits?: number;
  height?: number;
  /** Spaltenüberschriften der Tabelle (Standard: Datum, Wert). */
  tableHeaders?: [string, string];
};

const M = { l: 44, r: 12, t: 12, b: 28 };

type XLabel = { iso: string; anchor: "start" | "middle" | "end"; x: number };

export function LineChart({ points, title, unit, digits = 1, height = 220, tableHeaders = ["Datum", "Wert"] }: Props) {
  const boxRef = useRef<HTMLDivElement>(null);
  const width = useChartWidth(boxRef);
  const data = points
    .filter((p) => Number.isFinite(p.y) && Number.isFinite(dayNumber(p.x)))
    .sort((a, b) => dayNumber(a.x) - dayNumber(b.x));

  if (data.length === 0) return <p className="chart-empty">Keine Werte vorhanden.</p>;

  const first = data[0]!;
  const last = data[data.length - 1]!;
  const ys = data.map((p) => p.y);
  const minY = Math.min(...ys);
  const maxY = Math.max(...ys);
  const [lo, hi] = paddedRange(minY, maxY);
  const x0 = dayNumber(first.x);
  const x1 = dayNumber(last.x);
  const plotW = width - M.l - M.r;
  const plotH = height - M.t - M.b;
  const sx = (iso: string) => (x1 === x0 ? M.l + plotW / 2 : M.l + ((dayNumber(iso) - x0) / (x1 - x0)) * plotW);
  const sy = (v: number) => M.t + (1 - (v - lo) / (hi - lo)) * plotH;
  const ticks = niceTicks(lo, hi, 4);
  const path = data.map((p, i) => `${i === 0 ? "M" : "L"}${sx(p.x).toFixed(1)} ${sy(p.y).toFixed(1)}`).join(" ");

  const mid = data.length > 2 ? data[Math.floor((data.length - 1) / 2)]! : null;
  const xLabels: XLabel[] =
    x1 === x0
      ? [{ iso: first.x, anchor: "middle", x: sx(first.x) }]
      : [
          { iso: first.x, anchor: "start", x: M.l },
          ...(mid && sx(mid.x) - M.l > 70 && M.l + plotW - sx(mid.x) > 70
            ? [{ iso: mid.x, anchor: "middle", x: sx(mid.x) } satisfies XLabel]
            : []),
          { iso: last.x, anchor: "end", x: M.l + plotW },
        ];

  const label =
    `${title}: ${data.length} ${data.length === 1 ? "Wert" : "Werte"} ` +
    (data.length > 1 ? `von ${dateDe(first.x)} bis ${dateDe(last.x)}. ` : `am ${dateDe(first.x)}. `) +
    `Zuletzt ${num(last.y, digits, unit)}, niedrigster Wert ${num(minY, digits, unit)}, ` +
    `höchster Wert ${num(maxY, digits, unit)}.`;

  return (
    <figure className="chart">
      <div className="chart-box" ref={boxRef}>
        <svg viewBox={`0 0 ${width} ${height}`} role="img" aria-label={label}>
          {ticks.map((t) => (
            <g key={t}>
              <line className="chart-grid" x1={M.l} x2={M.l + plotW} y1={sy(t)} y2={sy(t)} />
              <text className="chart-axis-text" x={M.l - 6} y={sy(t)} textAnchor="end" dominantBaseline="middle">
                {num(t, digits)}
              </text>
            </g>
          ))}
          {xLabels.map((l) => (
            <text key={l.iso} className="chart-axis-text" x={l.x} y={height - 8} textAnchor={l.anchor}>
              {shortDate(l.iso)}
            </text>
          ))}
          {data.length > 1 && <path className="chart-line" d={path} />}
          {data.length <= 31 &&
            data.map((p) => <circle key={p.x} className="chart-dot" cx={sx(p.x)} cy={sy(p.y)} r={3.5} />)}
          <circle className="chart-dot" cx={sx(last.x)} cy={sy(last.y)} r={5} />
        </svg>
      </div>
      {unit && <p className="chart-caption">Einheit: {unit}</p>}
      <details className="chart-details">
        <summary>Werte als Tabelle anzeigen</summary>
        <div className="chart-details-scroll">
          <table className="table">
            <caption className="muted">{title}</caption>
            <thead>
              <tr>
                <th scope="col">{tableHeaders[0]}</th>
                <th scope="col">{tableHeaders[1]}</th>
              </tr>
            </thead>
            <tbody>
              {[...data].reverse().map((p) => (
                <tr key={p.x}>
                  <td>{dateDe(p.x)}</td>
                  <td>{num(p.y, digits, unit)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </details>
    </figure>
  );
}
