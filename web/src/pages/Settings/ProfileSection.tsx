import { type FormEvent, useState } from "react";
import { api } from "../../api/client";
import { useAuth, usePerson } from "../../auth/AuthContext";
import { useAction } from "../../hooks/useApi";
import { Alert, Button, Card, SelectField, TextField } from "../../ui";
import { todayIso } from "../../format";
import { DecimalField, parseDecimal, toField, validateNumber } from "./helpers";

type Errors = { name?: string; birth?: string; height?: string };

export function ProfileSection() {
  const person = usePerson();
  const { refresh } = useAuth();
  const [name, setName] = useState(person.name);
  const [sex, setSex] = useState<string>(person.sex);
  const [birth, setBirth] = useState(person.birth_date);
  const [height, setHeight] = useState(toField(person.height_cm));
  const [errors, setErrors] = useState<Errors>({});
  const [note, setNote] = useState<string | null>(null);

  const patch = useAction(async (body: Record<string, unknown>) => {
    await api("PATCH", "/me", body);
    await refresh();
    return true;
  });

  const submit = async (e: FormEvent) => {
    e.preventDefault();
    setNote(null);
    const next: Errors = {};
    if (!name.trim()) next.name = "Bitte einen Namen eingeben.";
    if (!birth) next.birth = "Bitte das Geburtsdatum angeben.";
    else if (birth >= todayIso()) next.birth = "Das Geburtsdatum muss in der Vergangenheit liegen.";
    const heightErr = validateNumber(height, { min: 50, max: 260 });
    if (heightErr) next.height = heightErr;
    setErrors(next);
    if (Object.keys(next).length > 0) return;

    const changes: Record<string, unknown> = {};
    if (name.trim() !== person.name) changes.name = name.trim();
    if (sex !== person.sex) changes.sex = sex;
    if (birth !== person.birth_date) changes.birth_date = birth;
    const h = parseDecimal(height).value;
    if (h !== null && h !== person.height_cm) changes.height_cm = h;
    if (Object.keys(changes).length === 0) {
      setNote("Es gibt keine Änderungen zu speichern.");
      return;
    }
    if (await patch.run(changes)) setNote("Gespeichert.");
  };

  return (
    <Card title="Profil">
      <form aria-label="Profil" onSubmit={submit} noValidate>
        <TextField label="Name" value={name} onChange={setName} error={errors.name} autoComplete="off" />
        <SelectField
          label="Geschlecht"
          value={sex}
          onChange={setSex}
          options={[
            { value: "m", label: "männlich" },
            { value: "f", label: "weiblich" },
          ]}
        />
        <TextField label="Geburtsdatum" type="date" value={birth} onChange={setBirth} error={errors.birth} />
        <DecimalField label="Körpergröße" unit="cm" value={height} onChange={setHeight} error={errors.height} />
        {patch.error && <Alert kind="error">{patch.error}</Alert>}
        {note && !patch.error && <Alert kind={note === "Gespeichert." ? "ok" : "info"}>{note}</Alert>}
        <Button type="submit" variant="primary" disabled={patch.busy}>
          {patch.busy ? "Speichert …" : "Speichern"}
        </Button>
      </form>
    </Card>
  );
}
