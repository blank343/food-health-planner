import { Link } from "react-router-dom";
import type { components } from "../../api/schema";
import { BarChart, LineChart } from "../../charts";
import { dateDe, kcal, kg, num, todayIso } from "../../format";
import { useQuery } from "../../hooks/useApi";
import { Alert, Async, Badge, Card, EmptyState, PageHeader, Stat, Table } from "../../ui";
import {
  STALE_WEIGHT_DAYS,
  daysBetween,
  importKindName,
  importStatus,
  signed,
  sourceName,
  weekNumber,
} from "./helpers";

type DashboardData = components["schemas"]["DashboardOut"];

function isEmptyDashboard(d: DashboardData): boolean {
  return (
    d.weight.latest_kg === null &&
    d.weight.points.length === 0 &&
    d.energy.device_tdee_kcal === null &&
    d.data.length === 0 &&
    d.labs.latest_report_date === null &&
    d.imports.length === 0 &&
    d.workouts.every((w) => w.count === 0)
  );
}

function EmptyDashboard() {
  return (
    <Card>
      <EmptyState>
        <p>
          <strong>Noch keine Daten vorhanden.</strong>
        </p>
        <p>
          Importieren Sie Ihre Gesundheitsdaten (Apple Health oder Health Auto Export), um Gewicht, Energie und
          Workouts zu sehen.
        </p>
        <p>
          Das Gewicht lässt sich auch von Hand eintragen, und zwar unter „Tagesziel“. Damit sind Zielwerte schon ohne
          Import möglich.
        </p>
        <div className="row" style={{ justifyContent: "center" }}>
          <Link className="btn primary" to="/importe">
            Zu den Importen
          </Link>
          <Link className="btn" to="/ziele">
            Gewicht unter „Tagesziel“ eintragen
          </Link>
        </div>
      </EmptyState>
    </Card>
  );
}

function Stats({ d }: { d: DashboardData }) {
  const { weight, energy, workouts } = d;
  const thisWeek = workouts[workouts.length - 1];
  const energyHint =
    energy.device_tdee_kcal === null
      ? "Keine vollständigen Gerätedaten"
      : `Ø der letzten ${energy.n_days} Tage, Abdeckung ${num(energy.coverage * 100, 0)} %` +
        (energy.last_day ? `, bis ${dateDe(energy.last_day)}` : "");
  return (
    <div className="grid" style={{ marginBottom: 16 }}>
      <Stat
        label="Aktuelles Gewicht"
        value={kg(weight.latest_kg)}
        hint={weight.latest_date ? `vom ${dateDe(weight.latest_date)}` : "Noch kein Gewicht"}
      />
      <Stat
        label="Trend pro Woche"
        value={signed(weight.trend_kg_per_week, 2, "kg")}
        hint={
          weight.trend_kg_per_week === null
            ? "Zu wenige Messwerte in den letzten 28 Tagen"
            : `aus ${weight.trend_n_points} Messwerten (28 Tage)`
        }
      />
      <Stat label="Energiebedarf laut Uhr" value={kcal(energy.device_tdee_kcal)} hint={energyHint} />
      <Stat
        label="Workouts diese Woche"
        value={thisWeek ? num(thisWeek.count) : "–"}
        hint={thisWeek ? `KW ${weekNumber(thisWeek.iso_week)}, ${num(thisWeek.total_minutes, 0, "min")}` : undefined}
      />
    </div>
  );
}

function Dashboard({ d }: { d: DashboardData }) {
  const today = todayIso();
  const stale =
    d.weight.latest_date !== null && daysBetween(d.weight.latest_date, today) > STALE_WEIGHT_DAYS
      ? daysBetween(d.weight.latest_date, today)
      : null;

  return (
    <>
      {stale !== null && (
        <Alert kind="warn">
          Das letzte Gewicht ist {num(stale)} Tage alt (vom {dateDe(d.weight.latest_date)}). Für verlässliche Zielwerte
          bitte ein aktuelles Gewicht unter „Tagesziel“ eintragen.
        </Alert>
      )}

      <Stats d={d} />

      <Card title="Gewicht (letzte 90 Tage)">
        {d.weight.points.length > 0 ? (
          <LineChart
            title="Gewicht"
            unit="kg"
            digits={1}
            points={d.weight.points.map((p) => ({ x: p.day, y: p.kg }))}
            tableHeaders={["Datum", "Gewicht"]}
          />
        ) : (
          <p className="muted">In den letzten 90 Tagen wurde kein Gewicht erfasst.</p>
        )}
      </Card>

      <Card title="Workouts pro Woche (8 Wochen)">
        <BarChart
          title="Workouts pro Kalenderwoche"
          unit="Workouts"
          extraUnit="Minuten"
          caption="Kalenderwoche"
          tableHeaders={["Woche", "Workouts", "Minuten"]}
          bars={d.workouts.map((w) => ({
            label: weekNumber(w.iso_week),
            longLabel: `KW ${weekNumber(w.iso_week)} (ab ${dateDe(w.week_start)})`,
            value: w.count,
            extra: w.total_minutes,
          }))}
        />
      </Card>

      <Card title="Datenabdeckung">
        {d.data.length === 0 ? (
          <p className="muted">Noch keine Gesundheitsdaten importiert.</p>
        ) : (
          <Table>
            <thead>
              <tr>
                <th scope="col">Quelle</th>
                <th scope="col">Erster Tag</th>
                <th scope="col">Letzter Tag</th>
                <th scope="col">Tage</th>
              </tr>
            </thead>
            <tbody>
              {d.data.map((s) => (
                <tr key={s.source}>
                  <td>{sourceName(s.source)}</td>
                  <td>{dateDe(s.first_day)}</td>
                  <td>{dateDe(s.last_day)}</td>
                  <td>{num(s.days)}</td>
                </tr>
              ))}
            </tbody>
          </Table>
        )}
      </Card>

      <Card
        title="Labor"
        actions={
          <Link className="btn" to="/labor">
            Zum Labor
          </Link>
        }
      >
        {d.labs.latest_report_date === null ? (
          <p className="muted">Noch kein Laborbericht vorhanden.</p>
        ) : (
          <div className="stack">
            <p style={{ marginBottom: 0 }}>
              Letzter Bericht: <strong>{dateDe(d.labs.latest_report_date)}</strong>
              {d.labs.latest_report_type ? ` (${d.labs.latest_report_type})` : ""}
            </p>
            <div className="row">
              <Badge kind={d.labs.flagged_count > 0 ? "warn" : "ok"}>
                {d.labs.flagged_count === 1 ? "1 auffälliger Wert" : `${num(d.labs.flagged_count)} auffällige Werte`}
              </Badge>
              <Badge kind={d.labs.pending_count > 0 ? "warn" : undefined}>
                {d.labs.pending_count === 1 ? "1 Wert ausstehend" : `${num(d.labs.pending_count)} Werte ausstehend`}
              </Badge>
            </div>
          </div>
        )}
      </Card>

      <Card
        title="Letzte Importe"
        actions={
          <Link className="btn" to="/importe">
            Zu den Importen
          </Link>
        }
      >
        {d.imports.length === 0 ? (
          <p className="muted">Noch kein Import durchgeführt.</p>
        ) : (
          <Table>
            <thead>
              <tr>
                <th scope="col">Quelle</th>
                <th scope="col">Datum</th>
                <th scope="col">Status</th>
              </tr>
            </thead>
            <tbody>
              {d.imports.map((j) => {
                const st = importStatus(j.status);
                return (
                  <tr key={j.id}>
                    <td>
                      {importKindName(j.kind)}
                      {j.filename && <small style={{ display: "block", wordBreak: "break-all" }}>{j.filename}</small>}
                    </td>
                    <td>{dateDe(j.created_at)}</td>
                    <td>
                      <Badge kind={st.kind}>{st.label}</Badge>
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </Table>
        )}
      </Card>

      <Card title="Tagesziel">
        <p>Zielwerte für Kalorien, Protein, Fett und Kohlenhydrate pro Tag und Mahlzeit.</p>
        <Link className="btn primary" to="/ziele">
          Zum Tagesziel
        </Link>
      </Card>
    </>
  );
}

export default function DashboardPage() {
  const q = useQuery<DashboardData>("/me/dashboard");
  return (
    <>
      <PageHeader title="Übersicht">Gewicht, Energie, Training und Datenstand auf einen Blick.</PageHeader>
      <Async loading={q.loading} error={q.error}>
        {q.data && (isEmptyDashboard(q.data) ? <EmptyDashboard /> : <Dashboard d={q.data} />)}
      </Async>
    </>
  );
}
