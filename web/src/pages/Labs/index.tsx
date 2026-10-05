import { useMemo, useState } from "react";
import { Link } from "react-router-dom";
import { dateDe } from "../../format";
import { useQuery } from "../../hooks/useApi";
import { Alert, Async, Badge, CheckField, Card, EmptyState, PageHeader, Spinner, Table, TextField } from "../../ui";
import {
  FLAG_TEXT,
  type LabReport,
  type LabResult,
  type LatestLabValue,
  byAnalyte,
  refText,
  reportDateIso,
  reportTypeText,
  valueText,
} from "./labFormat";
import "./Labs.css";

type Row = {
  key: string;
  analyte: string;
  unit: string;
  value: number | null;
  value_op: string | null;
  flag: string | null;
  ref_low: number | null;
  ref_high: number | null;
  ref_op: string | null;
  pending: boolean;
  date: string | null;
};

function FlagBadge({ flag }: { flag: string | null }) {
  if (flag !== "L" && flag !== "H") return <span aria-label="unauffällig">–</span>;
  return <Badge kind={flag === "H" ? "error" : "warn"}>{FLAG_TEXT[flag]}</Badge>;
}

function ValueCell({ row }: { row: Pick<Row, "pending" | "value" | "value_op"> }) {
  if (row.pending) return <span className="lab-pending">Wert steht noch aus</span>;
  return <>{valueText(row.value, row.value_op)}</>;
}

function latestRow(v: LatestLabValue): Row {
  return { ...v, key: `l-${v.report_id}-${v.analyte}-${v.unit}`, pending: false, date: v.report_date };
}

/** Je Analyt und Einheit der jüngste ausstehende Wert (Berichte sind neueste zuerst). */
function pendingRows(reports: LabReport[]): Row[] {
  const seen = new Map<string, Row>();
  for (const report of reports) {
    for (const r of report.results) {
      const id = `${r.analyte}|${r.unit}`;
      if (r.pending && !seen.has(id)) seen.set(id, { ...r, key: `p-${r.id}`, date: reportDateIso(report) });
    }
  }
  return [...seen.values()];
}

function ResultsTable({ results }: { results: LabResult[] }) {
  return (
    <Table>
      <thead>
        <tr>
          <th scope="col">Analyt</th>
          <th scope="col">Wert</th>
          <th scope="col">Einheit</th>
          <th scope="col">Referenzbereich</th>
          <th scope="col">Kennzeichen</th>
        </tr>
      </thead>
      <tbody>
        {[...results].sort(byAnalyte).map((r) => (
          <tr key={r.id}>
            <th scope="row">{r.analyte}</th>
            <td>
              <ValueCell row={r} />
            </td>
            <td>{r.unit || "–"}</td>
            <td>{refText(r.ref_low, r.ref_high, r.ref_op)}</td>
            <td>{r.pending ? <Badge>ausstehend</Badge> : <FlagBadge flag={r.flag} />}</td>
          </tr>
        ))}
      </tbody>
    </Table>
  );
}

export default function LabsPage() {
  const latest = useQuery<LatestLabValue[]>("/me/labs/latest");
  const reports = useQuery<LabReport[]>("/me/labs");
  const [search, setSearch] = useState("");
  const [onlyFlagged, setOnlyFlagged] = useState(false);
  const [onlyPending, setOnlyPending] = useState(false);
  const pending = useQuery<LabReport[]>(onlyPending ? "/me/labs?pending=true" : null);

  const rows = useMemo(() => {
    let out: Row[];
    if (!onlyFlagged && !onlyPending) out = (latest.data ?? []).map(latestRow);
    else {
      // Wie im Server: sind beide Filter gesetzt, zählt, was mindestens einen erfüllt.
      out = [];
      if (onlyFlagged) out.push(...(latest.data ?? []).filter((v) => v.flag === "L" || v.flag === "H").map(latestRow));
      if (onlyPending) out.push(...pendingRows(pending.data ?? []));
    }
    const q = search.trim().toLocaleLowerCase("de");
    if (q) out = out.filter((r) => r.analyte.toLocaleLowerCase("de").includes(q));
    return out.sort(byAnalyte);
  }, [latest.data, pending.data, onlyFlagged, onlyPending, search]);

  const nothingAtAll = (latest.data ?? []).length === 0 && (reports.data ?? []).length === 0;

  return (
    <>
      <PageHeader title="Labor">Deine Laborwerte aus den importierten Befunden.</PageHeader>
      <p className="muted lab-disclaimer">
        Die App stellt keine Diagnosen. Auffällige Werte bitte mit der Ärztin oder dem Arzt besprechen.
      </p>

      <Async loading={(latest.loading && !latest.data) || (reports.loading && !reports.data)} error={latest.error ?? reports.error}>
        {nothingAtAll ? (
          <Card>
            <EmptyState>
              <p>Noch keine Laborwerte vorhanden.</p>
              <p>
                Lade unter <Link to="/importe">Importe</Link> einen Laborbefund (PDF) hoch.
              </p>
            </EmptyState>
          </Card>
        ) : (
          <>
            <Card title="Aktuelle Werte">
              <TextField
                label="Analyt suchen"
                type="search"
                value={search}
                onChange={setSearch}
                placeholder="z. B. Cholesterin"
                autoComplete="off"
              />
              <div className="lab-filters" role="group" aria-label="Filter">
                <CheckField label="Nur auffällige" checked={onlyFlagged} onChange={setOnlyFlagged} />
                <CheckField label="Nur ausstehende" checked={onlyPending} onChange={setOnlyPending} />
              </div>
              {onlyPending && pending.loading && !pending.data ? (
                <Spinner />
              ) : onlyPending && pending.error ? (
                <Alert kind="error">{pending.error}</Alert>
              ) : rows.length === 0 ? (
                <EmptyState>Keine passenden Werte.</EmptyState>
              ) : (
                <Table>
                  <thead>
                    <tr>
                      <th scope="col">Analyt</th>
                      <th scope="col">Wert</th>
                      <th scope="col">Einheit</th>
                      <th scope="col">Referenzbereich</th>
                      <th scope="col">Kennzeichen</th>
                      <th scope="col">Datum</th>
                    </tr>
                  </thead>
                  <tbody>
                    {rows.map((r) => (
                      <tr key={r.key}>
                        <th scope="row">{r.analyte}</th>
                        <td>
                          <ValueCell row={r} />
                        </td>
                        <td>{r.unit || "–"}</td>
                        <td>{refText(r.ref_low, r.ref_high, r.ref_op)}</td>
                        <td>{r.pending ? <Badge>ausstehend</Badge> : <FlagBadge flag={r.flag} />}</td>
                        <td>{dateDe(r.date)}</td>
                      </tr>
                    ))}
                  </tbody>
                </Table>
              )}
            </Card>

            <Card title="Berichte">
              {(reports.data ?? []).length === 0 ? (
                <EmptyState>Noch keine Berichte.</EmptyState>
              ) : (
                (reports.data ?? []).map((report) => {
                  const open = report.results.filter((r) => r.pending).length;
                  return (
                    <details className="lab-report" key={report.id}>
                      <summary>
                        <strong>{dateDe(reportDateIso(report))}</strong>
                        <Badge kind={report.report_type === "Endbefund" ? "ok" : undefined}>
                          {reportTypeText(report.report_type)}
                        </Badge>
                        <span>{report.lab_name ?? "Labor unbekannt"}</span>
                        <span className="muted">
                          {report.results.length} {report.results.length === 1 ? "Wert" : "Werte"}, {open} ausstehend
                        </span>
                      </summary>
                      {report.results.length === 0 ? (
                        <EmptyState>Dieser Bericht enthält keine Werte.</EmptyState>
                      ) : (
                        <ResultsTable results={report.results} />
                      )}
                    </details>
                  );
                })
              )}
            </Card>
          </>
        )}
      </Async>
    </>
  );
}
