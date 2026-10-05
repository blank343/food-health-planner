import { useEffect, useState } from "react";
import { useQuery } from "../../hooks/useApi";
import { type Theme, applyTheme, applyStoredTheme, getStoredTheme, storeTheme } from "../../theme";
import { Async, Card, PageHeader, SelectField } from "../../ui";
import { GoalSection } from "./GoalSection";
import { ProfileSection } from "./ProfileSection";
import { EnergySection, SafetySection, SlotsSection, SourcesSection } from "./SettingsSections";
import type { SettingsOut } from "./helpers";
import "./Settings.css";

function AppearanceSection() {
  const [theme, setTheme] = useState<Theme>(getStoredTheme);
  useEffect(() => {
    applyStoredTheme();
  }, []);
  return (
    <Card title="Darstellung">
      <SelectField
        label="Farbschema"
        value={theme}
        onChange={(v) => {
          const t = v as Theme;
          setTheme(t);
          storeTheme(t);
          applyTheme(t);
        }}
        options={[
          { value: "system", label: "System" },
          { value: "light", label: "Hell" },
          { value: "dark", label: "Dunkel" },
        ]}
        hint="Wird sofort angewendet und nur auf diesem Gerät gespeichert."
      />
    </Card>
  );
}

export default function SettingsPage() {
  const q = useQuery<SettingsOut>("/me/settings");
  // Nach dem Speichern liefert der Server die neuen Werte; wir übernehmen sie lokal.
  const [override, setOverride] = useState<SettingsOut | null>(null);
  const settings = override ?? q.data;

  return (
    <>
      <PageHeader title="Einstellungen">
        Alle Werte gehören dir: Leere Felder verwenden sichere Standardwerte, die du jederzeit überschreiben kannst.
      </PageHeader>
      <ProfileSection />
      <GoalSection />
      <Async loading={q.loading && !settings} error={settings ? null : q.error}>
        {settings && (
          <>
            <SafetySection settings={settings} onSaved={setOverride} />
            <EnergySection settings={settings} onSaved={setOverride} />
            <SlotsSection settings={settings} onSaved={setOverride} />
            <SourcesSection settings={settings} onSaved={setOverride} />
          </>
        )}
      </Async>
      <AppearanceSection />
    </>
  );
}
