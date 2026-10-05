import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";
import { mockServer, renderPage } from "../../test/helpers";
import TrainingPlanPage from "./index";

type Session = {
  id: number;
  weekday: number;
  session_type: string;
  intensity: "easy" | "moderate" | "hard";
  start_time: string | null;
  duration_min: number | null;
  expected_kcal: number | null;
  enabled: boolean;
  note: string | null;
};

const MON: Session = {
  id: 1,
  weekday: 0,
  session_type: "Krafttraining",
  intensity: "hard",
  start_time: "18:30:00",
  duration_min: 60,
  expected_kcal: 400,
  enabled: true,
  note: "Testnotiz",
};
const WED: Session = { ...MON, id: 2, weekday: 2, session_type: "Laufen", intensity: "easy", start_time: null, duration_min: 40, expected_kcal: null, note: null };
const WED2: Session = { ...WED, id: 3, session_type: "Yoga", intensity: "moderate", duration_min: null, enabled: false };

function serverWith(initial: Session[], extra: Parameters<typeof mockServer>[0] = {}) {
  let list = [...initial];
  return mockServer({
    "GET /me/training-plan": () => ({ body: list }),
    "POST /me/training-plan": ({ body }) => {
      const created = { id: 99, ...(body as object) } as Session;
      list = [...list, created];
      return { status: 201, body: created };
    },
    "PUT /me/training-plan/1": ({ body }) => {
      const updated = { id: 1, ...(body as object) } as Session;
      list = list.map((s) => (s.id === 1 ? updated : s));
      return { body: updated };
    },
    "DELETE /me/training-plan/2": () => {
      list = list.filter((s) => s.id !== 2);
      return { status: 200 };
    },
    ...extra,
  });
}

const day = (name: string) => within(screen.getByRole("region", { name }));

describe("Trainingsplan", () => {
  it("zeigt Montag bis Sonntag mit Einheiten und Ruhetagen", async () => {
    serverWith([MON, WED, WED2]);
    renderPage(<TrainingPlanPage />);
    await screen.findByRole("heading", { name: "Krafttraining" });
    const headings = screen.getAllByRole("heading", { level: 2 }).map((h) => h.textContent);
    expect(headings).toEqual([
      "Zusammenfassung",
      "Montag",
      "Dienstag",
      "Mittwoch",
      "Donnerstag",
      "Freitag",
      "Samstag",
      "Sonntag",
    ]);
    const mon = day("Montag");
    expect(mon.getByText("hart")).toBeInTheDocument();
    expect(mon.getByText("18:30 Uhr")).toBeInTheDocument();
    expect(mon.getByText("60 min")).toBeInTheDocument();
    expect(mon.getByText("400 kcal")).toBeInTheDocument();
    expect(mon.getByText("Testnotiz")).toBeInTheDocument();
    expect(day("Dienstag").getByText("Ruhetag (keine Einheit)")).toBeInTheDocument();
    const wed = day("Mittwoch");
    expect(wed.getByRole("heading", { name: "Laufen" })).toBeInTheDocument();
    expect(wed.getByRole("heading", { name: "Yoga" })).toBeInTheDocument();
    expect(wed.getByText("leicht")).toBeInTheDocument();
    expect(wed.getByText("mittel")).toBeInTheDocument();
    expect(wed.getByText("pausiert")).toBeInTheDocument();
    expect(wed.queryByText("Ruhetag (keine Einheit)")).not.toBeInTheDocument();
  });

  it("fasst aktive Einheiten pro Woche und Intensität zusammen", async () => {
    serverWith([MON, WED, WED2]);
    renderPage(<TrainingPlanPage />);
    await screen.findByRole("heading", { name: "Krafttraining" });
    const summary = within(screen.getByRole("region", { name: "Zusammenfassung" }));
    const value = (label: string) => summary.getByText(label).previousElementSibling?.textContent;
    expect(value("Einheiten pro Woche")).toBe("2"); // Yoga ist pausiert
    expect(value("Trainingstage")).toBe("2");
    expect(summary.getByText("5 Ruhetage")).toBeInTheDocument();
    expect(value("Intensität leicht")).toBe("1");
    expect(value("Intensität mittel")).toBe("0");
    expect(value("Intensität hart")).toBe("1");
  });

  it("erklärt, dass die härteste Einheit pro Tag zählt", async () => {
    serverWith([MON]);
    renderPage(<TrainingPlanPage />);
    expect(await screen.findByText(/härteste aktive Einheit/)).toBeInTheDocument();
  });

  it("zeigt einen leeren Zustand und öffnet das Formular am Montag", async () => {
    serverWith([]);
    renderPage(<TrainingPlanPage />);
    expect(await screen.findByText(/Noch keine Trainingseinheiten/)).toBeInTheDocument();
    for (const d of ["Montag", "Sonntag"]) expect(day(d).getByText("Ruhetag (keine Einheit)")).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "Erste Einheit hinzufügen" }));
    expect(day("Montag").getByRole("form", { name: "Einheit hinzufügen" })).toBeInTheDocument();
    expect(screen.queryByText(/Noch keine Trainingseinheiten/)).not.toBeInTheDocument();
  });

  it("legt eine Einheit an einem bestimmten Tag an", async () => {
    const server = serverWith([MON]);
    renderPage(<TrainingPlanPage />);
    await screen.findByRole("heading", { name: "Krafttraining" });
    await userEvent.click(screen.getByRole("button", { name: "Einheit hinzufügen: Freitag" }));
    const form = day("Freitag").getByRole("form", { name: "Einheit hinzufügen" });
    expect(within(form).getByLabelText("Wochentag")).toHaveValue("4");
    expect(within(form).getByLabelText("Intensität")).toHaveValue("");
    await userEvent.type(within(form).getByLabelText("Art der Einheit"), "Radfahren");
    await userEvent.selectOptions(within(form).getByLabelText("Intensität"), "moderate");
    await userEvent.type(within(form).getByLabelText("Uhrzeit (optional)"), "07:15");
    await userEvent.type(within(form).getByLabelText("Dauer (min)"), "90");
    await userEvent.type(within(form).getByLabelText("Erwartete Kalorien (kcal)"), "650");
    await userEvent.type(within(form).getByLabelText("Notiz"), "locker");
    await userEvent.click(within(form).getByRole("button", { name: "Speichern" }));
    await waitFor(() => expect(server.calls.some((c) => c.method === "POST")).toBe(true));
    expect(server.calls.find((c) => c.method === "POST")?.body).toEqual({
      weekday: 4,
      session_type: "Radfahren",
      intensity: "moderate",
      start_time: "07:15",
      duration_min: 90,
      expected_kcal: 650,
      enabled: true,
      note: "locker",
    });
    expect(await day("Freitag").findByRole("heading", { name: "Radfahren" })).toBeInTheDocument();
  });

  it("sendet leere optionale Felder als null", async () => {
    const server = serverWith([]);
    renderPage(<TrainingPlanPage />);
    await userEvent.click(await screen.findByRole("button", { name: "Erste Einheit hinzufügen" }));
    await userEvent.type(screen.getByLabelText("Art der Einheit"), "Spazieren");
    await userEvent.selectOptions(screen.getByLabelText("Intensität"), "easy");
    await userEvent.click(screen.getByRole("button", { name: "Speichern" }));
    await waitFor(() => expect(server.calls.some((c) => c.method === "POST")).toBe(true));
    expect(server.calls.find((c) => c.method === "POST")?.body).toEqual({
      weekday: 0,
      session_type: "Spazieren",
      intensity: "easy",
      start_time: null,
      duration_min: null,
      expected_kcal: null,
      enabled: true,
      note: null,
    });
  });

  it("verlangt Art und Intensität und prüft die Dauer", async () => {
    const server = serverWith([]);
    renderPage(<TrainingPlanPage />);
    await userEvent.click(await screen.findByRole("button", { name: "Erste Einheit hinzufügen" }));
    await userEvent.click(screen.getByRole("button", { name: "Speichern" }));
    expect(screen.getByRole("alert")).toHaveTextContent("Bitte die Art der Einheit angeben");
    await userEvent.type(screen.getByLabelText("Art der Einheit"), "Laufen");
    await userEvent.click(screen.getByRole("button", { name: "Speichern" }));
    expect(screen.getByRole("alert")).toHaveTextContent("Bitte die Intensität wählen.");
    await userEvent.selectOptions(screen.getByLabelText("Intensität"), "hard");
    await userEvent.type(screen.getByLabelText("Dauer (min)"), "2000");
    await userEvent.click(screen.getByRole("button", { name: "Speichern" }));
    expect(screen.getByRole("alert")).toHaveTextContent("zwischen 1 und 1440 Minuten");
    expect(server.calls.some((c) => c.method === "POST")).toBe(false);
  });

  it("zeigt die Servermeldung bei 422", async () => {
    serverWith([], { "POST /me/training-plan": { status: 422, body: { detail: "Die Eingabe ist ungültig." } } });
    renderPage(<TrainingPlanPage />);
    await userEvent.click(await screen.findByRole("button", { name: "Erste Einheit hinzufügen" }));
    await userEvent.type(screen.getByLabelText("Art der Einheit"), "Laufen");
    await userEvent.selectOptions(screen.getByLabelText("Intensität"), "hard");
    await userEvent.click(screen.getByRole("button", { name: "Speichern" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("Die Eingabe ist ungültig.");
    expect(screen.getByRole("form", { name: "Einheit hinzufügen" })).toBeInTheDocument();
  });

  it("bearbeitet eine Einheit und kann sie auf einen anderen Tag legen (PUT)", async () => {
    const server = serverWith([MON, WED]);
    renderPage(<TrainingPlanPage />);
    await userEvent.click(await screen.findByRole("button", { name: "Krafttraining am Montag bearbeiten" }));
    expect(screen.getByLabelText("Uhrzeit (optional)")).toHaveValue("18:30");
    expect(screen.getByLabelText("Intensität")).toHaveValue("hard");
    await userEvent.selectOptions(screen.getByLabelText("Wochentag"), "1");
    await userEvent.selectOptions(screen.getByLabelText("Intensität"), "moderate");
    await userEvent.click(screen.getByLabelText("Aktiv"));
    await userEvent.click(screen.getByRole("button", { name: "Speichern" }));
    await waitFor(() => expect(server.calls.some((c) => c.method === "PUT")).toBe(true));
    const put = server.calls.find((c) => c.method === "PUT");
    expect(put?.path).toBe("/me/training-plan/1");
    expect(put?.body).toEqual({
      weekday: 1,
      session_type: "Krafttraining",
      intensity: "moderate",
      start_time: "18:30",
      duration_min: 60,
      expected_kcal: 400,
      enabled: false,
      note: "Testnotiz",
    });
    expect(await day("Dienstag").findByRole("heading", { name: "Krafttraining" })).toBeInTheDocument();
    expect(day("Montag").getByText("Ruhetag (keine Einheit)")).toBeInTheDocument();
  });

  it("löscht nach Rückfrage", async () => {
    const server = serverWith([MON, WED]);
    renderPage(<TrainingPlanPage />);
    await userEvent.click(await screen.findByRole("button", { name: "Laufen am Mittwoch löschen" }));
    expect(server.calls.some((c) => c.method === "DELETE")).toBe(false);
    expect(screen.getByRole("alertdialog")).toHaveTextContent("„Laufen am Mittwoch“ wirklich löschen?");
    await userEvent.click(screen.getByRole("button", { name: "Ja, löschen" }));
    await waitFor(() => expect(server.calls.some((c) => c.method === "DELETE" && c.path === "/me/training-plan/2")).toBe(true));
    await waitFor(() => expect(day("Mittwoch").getByText("Ruhetag (keine Einheit)")).toBeInTheDocument());
  });

  it("zeigt Ladefehler", async () => {
    mockServer({ "GET /me/training-plan": { status: 500, body: { detail: "Serverfehler." } } });
    renderPage(<TrainingPlanPage />);
    expect(await screen.findByRole("alert")).toHaveTextContent("Serverfehler.");
  });
});
