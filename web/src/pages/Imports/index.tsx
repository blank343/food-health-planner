import { useMemo, useState } from "react";
import { num } from "../../format";
import { useQuery } from "../../hooks/useApi";
import { Alert, Async, Badge, Card, EmptyState, PageHeader, Progress, Table } from "../../ui";
import { type CardConfig, ImportCard } from "./ImportCard";
import { type ImportJob, STATUS_LABEL, kindLabel, timeDe } from "./jobs";
import "./Imports.css";

const CARDS: CardConfig[] = [
  {
    kind: "hae",
    title: "Health Auto Export",
    endpoint: "/me/imports/hae",
    extensions: [".zip", ".csv"],
    howTo: <p>Löse in der App Health Auto Export einen Export als ZIP oder CSV aus und lade die Datei hier hoch.</p>,
    doneLink: { to: "/", label: "Übersicht" },
  },
  {
    kind: "apple_health",
    title: "Apple Health (Export aus der Health-App)",
    endpoint: "/me/imports/apple-health",
    extensions: [".zip", ".xml"],
    howTo: (
      <>
        <p>
          Öffne die Health-App, tippe auf dein Profilbild und wähle „Alle Gesundheitsdaten exportieren“. Lade danach
          die Datei export.zip (oder export.xml) hier hoch.
        </p>
        <p className="muted">Große Dateien (über 1 GB) können einige Minuten dauern.</p>
      </>
    ),
    doneLink: { to: "/", label: "Übersicht" },
  },
  {
    kind: "labs",
    title: "Laborbefund (PDF)",
    endpoint: "/me/imports/labs",
    extensions: [".pdf"],
    howTo: (
      <>
        <p>Lade den Laborbefund als PDF hoch.</p>
        <p className="muted">
          Das Geburtsdatum im Befund muss zu deinem Profil passen. Ein Teilbefund wird später durch den vollständigen
          Befund ergänzt. Der Name im Befund wird nicht gespeichert.
        </p>
      </>
    ),
    doneLink: { to: "/labor", label: "Labor" },
  },
];

function statusBadge(status: string) {
  const kind = status === "done" ? "ok" : status === "failed" ? "error" : status === "running" ? "warn" : undefined;
  return <Badge kind={kind}>{STATUS_LABEL[status] ?? status}</Badge>;
}

export default function ImportsPage() {
  const list = useQuery<ImportJob[]>("/me/imports");
  const [live, setLive] = useState<Record<number, ImportJob>>({});

  const jobs = useMemo(() => (list.data ?? []).map((j) => live[j.id] ?? j), [list.data, live]);
  const latestByKind = useMemo(() => {
    const out: Record<string, ImportJob> = {};
    for (const j of list.data ?? []) if (!(j.kind in out)) out[j.kind] = j;
    return out;
  }, [list.data]);

  const onJob = (job: ImportJob) => setLive((prev) => ({ ...prev, [job.id]: job }));

  return (
    <>
      <PageHeader title="Importe">
        Lade hier Gesundheitsdaten und Laborbefunde hoch. Pro Quelle läuft immer nur ein Import gleichzeitig.
      </PageHeader>

      {CARDS.map((config) => (
        <ImportCard
          key={config.kind}
          config={config}
          resumeJob={latestByKind[config.kind]}
          onJob={onJob}
          onStarted={list.reload}
          onFinished={list.reload}
        />
      ))}

      <Card title="Letzte Importe">
        <Async loading={list.loading && !list.data} error={list.data ? null : list.error}>
          {list.data && list.error && <Alert kind="error">{list.error}</Alert>}
          {jobs.length === 0 ? (
            <EmptyState>Noch keine Importe.</EmptyState>
          ) : (
            <Table>
              <thead>
                <tr>
                  <th scope="col">Zeit</th>
                  <th scope="col">Art</th>
                  <th scope="col">Dateiname</th>
                  <th scope="col">Status</th>
                </tr>
              </thead>
              <tbody>
                {jobs.map((j) => (
                  <tr key={j.id}>
                    <td>{timeDe(j.created_at)}</td>
                    <td>{kindLabel(j.kind)}</td>
                    <td>{j.filename ?? "–"}</td>
                    <td>
                      {statusBadge(j.status)}
                      {j.status === "running" && (
                        <div className="stack">
                          <Progress fraction={j.progress} label={`Fortschritt ${kindLabel(j.kind)}`} />
                          <small>{num(j.progress * 100)} %</small>
                        </div>
                      )}
                      {j.status === "failed" && j.error && (
                        <div>
                          <small>{j.error}</small>
                        </div>
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </Table>
          )}
        </Async>
      </Card>
    </>
  );
}
