// Eine Importkarte: Anleitung, Dateiauswahl (auch per Ziehen), Upload mit Fortschritt, Abfrage des Jobs.
import { type ChangeEvent, type DragEvent, type ReactNode, useEffect, useId, useRef, useState } from "react";
import { Link } from "react-router-dom";
import { ApiError, api, upload } from "../../api/client";
import { num } from "../../format";
import { Alert, Card, Progress, Spinner } from "../../ui";
import { type ImportJob, isActive, isStale, summarize } from "./jobs";

export const POLL_MS = 2000;

export type CardConfig = {
  kind: string;
  title: string;
  endpoint: string;
  extensions: string[];
  howTo: ReactNode;
  doneLink: { to: string; label: string };
};

type Phase = "idle" | "uploading" | "processing" | "done" | "failed";

const mb = (bytes: number) => num(bytes / (1024 * 1024), 1, "MB");

function extensionOf(name: string): string {
  const i = name.lastIndexOf(".");
  return i < 0 ? "" : name.slice(i).toLowerCase();
}

type Props = {
  config: CardConfig;
  /** Neuester Job dieser Art aus der Liste; läuft er noch, wird die Abfrage fortgesetzt. */
  resumeJob?: ImportJob;
  onJob: (job: ImportJob) => void;
  onStarted: () => void;
  onFinished: () => void;
};

export function ImportCard({ config, resumeJob, onJob, onStarted, onFinished }: Props) {
  const inputId = useId();
  const [phase, setPhase] = useState<Phase>("idle");
  const [fraction, setFraction] = useState(0);
  const [file, setFile] = useState<{ name: string; size: number } | null>(null);
  const [job, setJob] = useState<ImportJob | null>(null);
  const [jobId, setJobId] = useState<number | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [pollWarning, setPollWarning] = useState<string | null>(null);
  const [over, setOver] = useState(false);
  const handled = useRef(new Set<number>());
  const callbacks = useRef({ onJob, onStarted, onFinished });
  callbacks.current = { onJob, onStarted, onFinished };

  const busy = phase === "uploading" || phase === "processing";
  const extList = config.extensions.join(", ");

  // Laufenden Job aus der Liste wieder aufnehmen (z. B. nach Neuladen der Seite).
  useEffect(() => {
    if (!resumeJob || phase !== "idle" || handled.current.has(resumeJob.id)) return;
    if (!isActive(resumeJob) || isStale(resumeJob)) return;
    handled.current.add(resumeJob.id);
    setJob(resumeJob);
    setJobId(resumeJob.id);
    setPhase("processing");
  }, [resumeJob, phase]);

  // Job alle 2 s abfragen, bis er fertig ist oder fehlschlägt. Der Timer wird beim Verlassen entfernt.
  useEffect(() => {
    if (jobId === null) return;
    let cancelled = false;
    let timer: ReturnType<typeof setTimeout> | undefined;
    const poll = async () => {
      try {
        const next = await api<ImportJob>("GET", `/me/imports/${jobId}`);
        if (cancelled) return;
        setJob(next);
        setPollWarning(null);
        callbacks.current.onJob(next);
        if (next.status === "done" || next.status === "failed") {
          setPhase(next.status);
          setJobId(null);
          callbacks.current.onFinished();
          return;
        }
      } catch (e) {
        if (cancelled) return;
        if (e instanceof ApiError && e.status === 404) {
          setError(e.message);
          setPhase("idle");
          setJobId(null);
          return;
        }
        setPollWarning(e instanceof ApiError ? e.message : "Der Stand konnte nicht abgefragt werden.");
      }
      timer = setTimeout(poll, POLL_MS);
    };
    timer = setTimeout(poll, POLL_MS);
    return () => {
      cancelled = true;
      if (timer !== undefined) clearTimeout(timer);
    };
  }, [jobId]);

  async function start(picked: File) {
    if (busy) return;
    setError(null);
    setPollWarning(null);
    setJob(null);
    if (!config.extensions.includes(extensionOf(picked.name))) {
      setPhase("idle");
      setFile(null);
      setError(`Dateityp nicht unterstützt. Erlaubt: ${extList}.`);
      return;
    }
    if (picked.size === 0) {
      setPhase("idle");
      setFile(null);
      setError("Die Datei ist leer.");
      return;
    }
    setFile({ name: picked.name, size: picked.size });
    setFraction(0);
    setPhase("uploading");
    try {
      const created = await upload<ImportJob>(config.endpoint, picked, setFraction);
      handled.current.add(created.id);
      setJob(created);
      setJobId(created.id);
      setPhase("processing");
      callbacks.current.onJob(created);
      callbacks.current.onStarted();
    } catch (e) {
      setPhase("idle");
      setError(e instanceof ApiError ? e.message : "Der Upload ist fehlgeschlagen.");
    }
  }

  function onPick(e: ChangeEvent<HTMLInputElement>) {
    const picked = e.target.files?.[0];
    e.target.value = ""; // dieselbe Datei darf erneut gewählt werden
    if (picked) void start(picked);
  }

  function onDrop(e: DragEvent<HTMLDivElement>) {
    e.preventDefault();
    setOver(false);
    const dropped = e.dataTransfer.files?.[0];
    if (dropped && !busy) void start(dropped);
  }

  const percent = Math.round(fraction * 100);
  const jobPercent = Math.round((job?.progress ?? 0) * 100);
  const fileName = file?.name ?? job?.filename ?? null;

  return (
    <Card title={config.title}>
      <div className="import-howto">{config.howTo}</div>
      <div
        className={`dropzone${over ? " over" : ""}`}
        onDragOver={(e) => {
          e.preventDefault();
          if (!busy) setOver(true);
        }}
        onDragLeave={() => setOver(false)}
        onDrop={onDrop}
      >
        <div className="field">
          <label className="label" htmlFor={inputId}>
            {config.title}: Datei auswählen ({extList})
          </label>
          <input
            id={inputId}
            className="input"
            type="file"
            accept={config.extensions.join(",")}
            disabled={busy}
            onChange={onPick}
          />
          <span className="hint">Oder die Datei hierher ziehen.</span>
        </div>
      </div>

      {error && <Alert kind="error">{error}</Alert>}

      {phase === "uploading" && (
        <div role="status" aria-live="polite" className="stack">
          <div>
            Hochladen … {percent} %{file ? ` (${file.name}, ${mb(file.size)})` : ""}
          </div>
          <Progress fraction={fraction} label="Hochladen …" />
        </div>
      )}

      {phase === "processing" && (
        <div className="stack">
          <Spinner label={`Wird verarbeitet … ${jobPercent} %${job?.message ? ` – ${job.message}` : ""}`} />
          <Progress fraction={job?.progress ?? 0} label="Wird verarbeitet …" />
          {fileName && <small>Datei: {fileName}</small>}
          {pollWarning && <Alert kind="warn">{pollWarning}</Alert>}
        </div>
      )}

      {phase === "done" && job && (
        <div className="stack">
          <Alert kind="ok">
            {fileName ? `${fileName}: ` : ""}
            {summarize(job)}
          </Alert>
          <Link className="btn" to={config.doneLink.to}>
            {config.doneLink.label}
          </Link>
        </div>
      )}

      {phase === "failed" && job && <Alert kind="error">{job.error ?? "Der Import ist fehlgeschlagen."}</Alert>}
    </Card>
  );
}
