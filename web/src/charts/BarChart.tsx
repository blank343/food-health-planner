import { useRef } from "react";
import { num } from "../format";
import "./charts.css";
import { useChartWidth } from "./useChartWidth";

export type Bar = {
  /** Kurze Beschriftung unter dem Balken, z. B. „41“. */
  label: string;
  /** Ausführliche Beschriftung für Vorlesehilfe und Tabelle, z. B. „KW 41 (06.10.)“. */
  longLabel?: string;
  value: number;
  /** Zusatzwert, nur in Tabelle und Vorlesetext (z. B. Minuten). */
  extra?: number;
};

type Props = {
  bars: Bar[];
  title: string;
  /** Einheit des Hauptwerts, z. B. „Workouts“. */
  unit?: string;
  extraUnit?: string;
  /** Text unter der Zeichnung, z. B. „Kalenderwoche“. */
  caption?: string;
  height?: number;
  /** Spaltenüberschriften der Tabelle: Zeitraum, Hauptwert, Zusatzwert. */
  tableHeaders?: [string, string, string?];
};

const M = { l: 8, r: 8, t: 22, b: 26 };

export function BarChart({ bars, title, unit, extraUnit, caption, height = 200, tableHeaders }: Props) {
  const boxRef = useRef<HTMLDivElement>(null);
  const width = useChartWidth(boxRef);
  if (bars.length === 0) return <p className="chart-empty">Keine Werte vorhanden.</p>;

  const max = Math.max(1, ...bars.map((b) => b.value));
  const plotW = width - M.l - M.r;
  const plotH = height - M.t - M.b;
  const slot = plotW / bars.length;
  const barW = Math.min(40, slot * 0.62);
  const baseY = M.t + plotH;
  const name = (b: Bar) => b.longLabel ?? b.label;
  const hasExtra = bars.some((b) => b.extra !== undefined);

  const total = bars.reduce((s, b) => s + b.value, 0);
  const extraTotal = bars.reduce((s, b) => s + (b.extra ?? 0), 0);
  const label =
    `${title}: ${bars.length} Zeiträume, insgesamt ${num(total, 0, unit)}` +
    (hasExtra ? ` und ${num(extraTotal, 0, extraUnit)}` : "") +
    ". " +
    bars
      .map((b) => `${name(b)}: ${num(b.value, 0, unit)}${b.extra !== undefined ? `, ${num(b.extra, 0, extraUnit)}` : ""}`)
      .join("; ") +
    ".";

  const headers = tableHeaders ?? ["Zeitraum", unit ?? "Wert", extraUnit];

  return (
    <figure className="chart">
      <div className="chart-box" ref={boxRef}>
        <svg viewBox={`0 0 ${width} ${height}`} role="img" aria-label={label}>
          <line className="chart-grid" x1={M.l} x2={width - M.r} y1={baseY} y2={baseY} />
          {bars.map((b, i) => {
            const cx = M.l + slot * i + slot / 2;
            const h = (b.value / max) * (plotH - 4);
            return (
              <g key={`${b.label}-${i}`}>
                {b.value > 0 && (
                  <rect className="chart-bar" x={cx - barW / 2} y={baseY - h} width={barW} height={h} rx={3} />
                )}
                <text className="chart-value-text" x={cx} y={baseY - h - 5} textAnchor="middle">
                  {num(b.value, 0)}
                </text>
                <text className="chart-axis-text" x={cx} y={height - 6} textAnchor="middle">
                  {b.label}
                </text>
              </g>
            );
          })}
        </svg>
      </div>
      {caption && <p className="chart-caption">{caption}</p>}
      <details className="chart-details">
        <summary>Werte als Tabelle anzeigen</summary>
        <div className="chart-details-scroll">
          <table className="table">
            <caption className="muted">{title}</caption>
            <thead>
              <tr>
                <th scope="col">{headers[0]}</th>
                <th scope="col">{headers[1]}</th>
                {hasExtra && <th scope="col">{headers[2] ?? "Zusatz"}</th>}
              </tr>
            </thead>
            <tbody>
              {bars.map((b, i) => (
                <tr key={`${b.label}-${i}`}>
                  <td>{name(b)}</td>
                  <td>{num(b.value, 0)}</td>
                  {hasExtra && <td>{num(b.extra, 0)}</td>}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </details>
    </figure>
  );
}
