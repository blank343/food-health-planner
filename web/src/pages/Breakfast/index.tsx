import { useCallback, useState } from "react";
import { api } from "../../api/client";
import { useAction, useQuery } from "../../hooks/useApi";
import { Alert, Async, Button, PageHeader } from "../../ui";
import { ComponentsManager } from "./ComponentsManager";
import { Composer } from "./Composer";
import { SeedResult } from "./SeedResult";
import type { ComponentOut, SeedOut } from "./types";
import "../Ingredients/Ingredients.css";

type Tab = "compose" | "manage";

export default function BreakfastPage() {
  const [tab, setTab] = useState<Tab>("compose");
  const [creating, setCreating] = useState(false);
  const [seedResult, setSeedResult] = useState<SeedOut | null>(null);
  const list = useQuery<ComponentOut[]>("/components");
  const { reload } = list;
  const components = list.data ?? [];

  const seed = useAction(
    useCallback(async () => {
      const result = await api<SeedOut>("POST", "/components/seed-defaults");
      setSeedResult(result);
      reload();
      return result;
    }, [reload]),
  );
  const runSeed = () => void seed.run();

  return (
    <>
      <PageHeader
        title="Frühstück"
        actions={
          <>
            <Button onClick={runSeed} disabled={seed.busy} aria-busy={seed.busy}>
              {seed.busy ? "Legt an …" : "Standard-Komponenten anlegen"}
            </Button>
            {tab === "manage" && !creating && (
              <Button variant="primary" onClick={() => setCreating(true)}>
                Komponente anlegen
              </Button>
            )}
          </>
        }
      >
        Der Baukasten für das Frühstück: Komponenten verwalten und Mengen mit Live-Summe zusammenstellen.
      </PageHeader>

      {seed.error && <Alert kind="error">{seed.error}</Alert>}
      {seedResult && <SeedResult result={seedResult} onDismiss={() => setSeedResult(null)} />}

      <div className="tabs" role="tablist" aria-label="Bereiche">
        <button
          type="button"
          role="tab"
          id="tab-compose"
          className="tab"
          aria-selected={tab === "compose"}
          aria-controls="panel-compose"
          onClick={() => setTab("compose")}
        >
          Zusammenstellen
        </button>
        <button
          type="button"
          role="tab"
          id="tab-manage"
          className="tab"
          aria-selected={tab === "manage"}
          aria-controls="panel-manage"
          onClick={() => setTab("manage")}
        >
          Komponenten
        </button>
      </div>

      <Async loading={list.loading && !list.data} error={list.error}>
        {/* Der Rechner bleibt beim Wechsel der Reiter erhalten (nur verborgen), damit die Auswahl nicht verloren geht. */}
        <div role="tabpanel" id="panel-compose" aria-labelledby="tab-compose" hidden={tab !== "compose"}>
          <Composer components={components} onSeed={runSeed} seeding={seed.busy} />
        </div>
        {tab === "manage" && (
          <div role="tabpanel" id="panel-manage" aria-labelledby="tab-manage">
            <ComponentsManager
              components={components}
              reload={reload}
              onSeed={runSeed}
              seeding={seed.busy}
              creating={creating}
              onCreatingChange={setCreating}
            />
          </div>
        )}
      </Async>
    </>
  );
}
