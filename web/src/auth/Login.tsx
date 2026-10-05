import { type FormEvent, useState } from "react";
import { Alert, Button, Card, TextField } from "../ui";
import { useAuth } from "./AuthContext";

export default function Login() {
  const { state, login } = useAuth();
  const [token, setTokenValue] = useState("");
  const [busy, setBusy] = useState(false);

  async function submit(e: FormEvent) {
    e.preventDefault();
    if (!token.trim()) return;
    setBusy(true);
    await login(token);
    setBusy(false);
  }

  const error = state.status === "anon" ? state.error : null;
  return (
    <main className="login">
      <h1>Essensplan</h1>
      <p className="muted">Bitte melde dich mit deinem persönlichen Zugangstoken an.</p>
      <Card>
        <form onSubmit={submit}>
          {error && <Alert kind="error">{error}</Alert>}
          <TextField
            label="Zugangstoken"
            hint="Das Token erzeugt der Server-Verwalter mit „python -m app.cli“. Es bleibt nur auf diesem Gerät gespeichert."
            type="password"
            autoComplete="current-password"
            value={token}
            onChange={setTokenValue}
            required
          />
          <Button variant="primary" type="submit" disabled={busy || !token.trim()}>
            {busy ? "Prüfe …" : "Anmelden"}
          </Button>
        </form>
      </Card>
    </main>
  );
}
