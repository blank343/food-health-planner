import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";
import { mockServer, renderPage } from "../../test/helpers";
import SupplementsPage from "./index";

type Sup = {
  id: number;
  name: string;
  dose_amount: number | null;
  dose_unit: string | null;
  nutrients_per_day: Record<string, number>;
  taking: boolean;
  time_of_day: string | null;
  note: string | null;
};

const A: Sup = {
  id: 1,
  name: "Testkapsel A",
  dose_amount: 500,
  dose_unit: "mg",
  nutrients_per_day: { zinc_mg: 15, epa_dha_mg: 600 },
  taking: true,
  time_of_day: "abends",
  note: "Mit Wasser",
};
const B: Sup = {
  id: 2,
  name: "Testpulver B",
  dose_amount: null,
  dose_unit: null,
  nutrients_per_day: {},
  taking: false,
  time_of_day: null,
  note: null,
};

function serverWith(initial: Sup[], extra: Parameters<typeof mockServer>[0] = {}) {
  let list = [...initial];
  return mockServer({
    "GET /me/supplements": () => ({ body: list }),
    "POST /me/supplements": ({ body }) => {
      const created = { id: 99, ...(body as object) } as Sup;
      list = [...list, created];
      return { status: 201, body: created };
    },
    "PUT /me/supplements/1": ({ body }) => {
      const updated = { id: 1, ...(body as object) } as Sup;
      list = list.map((s) => (s.id === 1 ? updated : s));
      return { body: updated };
    },
    "DELETE /me/supplements/2": () => {
      list = list.filter((s) => s.id !== 2);
      return { status: 200 };
    },
    ...extra,
  });
}

describe("Supplemente", () => {
  it("zeigt die Liste mit Dosis, Beitrag, Badge, Tageszeit und Notiz", async () => {
    serverWith([A, B]);
    renderPage(<SupplementsPage />);
    const list = await screen.findByRole("list", { name: "Supplemente" });
    const items = within(list).getAllByRole("listitem");
    expect(items).toHaveLength(2);
    const first = within(items[0]!);
    expect(first.getByRole("heading", { name: "Testkapsel A" })).toBeInTheDocument();
    expect(first.getByText("Dosis: 500 mg")).toBeInTheDocument();
    expect(first.getByText("Beitrag pro Tag: Zink (mg): 15 · EPA/DHA (mg): 600")).toBeInTheDocument();
    expect(first.getByText("nimmt aktuell")).toBeInTheDocument();
    expect(first.getByText("abends")).toBeInTheDocument();
    expect(first.getByText("Mit Wasser")).toBeInTheDocument();
    const second = within(items[1]!);
    expect(second.getByText("nimmt aktuell nicht")).toBeInTheDocument();
    expect(second.getByText("Kein Nährstoffbeitrag eingetragen.")).toBeInTheDocument();
  });

  it("erklärt, dass Supplemente bei Obergrenzen mitgezählt werden", async () => {
    serverWith([A]);
    renderPage(<SupplementsPage />);
    expect(await screen.findByText(/zusammen mit dem Essen auf Obergrenzen angerechnet/)).toBeInTheDocument();
  });

  it("zeigt einen freundlichen leeren Zustand und öffnet das Formular", async () => {
    serverWith([]);
    renderPage(<SupplementsPage />);
    expect(await screen.findByText(/Noch keine Supplemente eingetragen/)).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "Erstes Supplement hinzufügen" }));
    expect(screen.getByRole("form", { name: "Supplement hinzufügen" })).toBeInTheDocument();
  });

  it("zeigt Ladefehler", async () => {
    mockServer({ "GET /me/supplements": { status: 500, body: { detail: "Serverfehler." } } });
    renderPage(<SupplementsPage />);
    expect(await screen.findByRole("alert")).toHaveTextContent("Serverfehler.");
  });

  it("legt ein Supplement mit Nährstoffzeilen an und lädt die Liste neu", async () => {
    const server = serverWith([]);
    renderPage(<SupplementsPage />);
    await userEvent.click(await screen.findByRole("button", { name: "Erstes Supplement hinzufügen" }));

    await userEvent.type(screen.getByLabelText("Name"), "  Kapsel Neu ");
    await userEvent.type(screen.getByLabelText("Dosis (Menge)"), "2");
    await userEvent.type(screen.getByLabelText("Dosis (Einheit)"), "Kapseln");
    await userEvent.click(screen.getByRole("button", { name: "Nährstoff hinzufügen" }));
    await userEvent.type(screen.getByLabelText("Nährstoff 1"), "zinc_mg");
    await userEvent.type(screen.getByLabelText("Menge pro Tag 1"), "12.5");
    await userEvent.click(screen.getByRole("button", { name: "Nährstoff hinzufügen" }));
    await userEvent.type(screen.getByLabelText("Nährstoff 2"), "magnesium_mg");
    await userEvent.type(screen.getByLabelText("Menge pro Tag 2"), "300");
    await userEvent.selectOptions(screen.getByLabelText("Tageszeit"), "zu den Mahlzeiten");
    await userEvent.type(screen.getByLabelText("Notiz"), "nach dem Essen");
    await userEvent.click(screen.getByRole("button", { name: "Speichern" }));

    await waitFor(() => expect(server.calls.some((c) => c.method === "POST")).toBe(true));
    const post = server.calls.find((c) => c.method === "POST");
    expect(post?.path).toBe("/me/supplements");
    expect(post?.body).toEqual({
      name: "Kapsel Neu",
      dose_amount: 2,
      dose_unit: "Kapseln",
      nutrients_per_day: { zinc_mg: 12.5, magnesium_mg: 300 },
      taking: true,
      time_of_day: "zu den Mahlzeiten",
      note: "nach dem Essen",
    });
    expect(await screen.findByRole("heading", { name: "Kapsel Neu" })).toBeInTheDocument();
    expect(screen.queryByRole("form")).not.toBeInTheDocument();
  });

  it("sendet leere optionale Felder als null und taking=false", async () => {
    const server = serverWith([B]);
    renderPage(<SupplementsPage />);
    await userEvent.click(await screen.findByRole("button", { name: "Supplement hinzufügen" }));
    await userEvent.type(screen.getByLabelText("Name"), "Nur Name");
    await userEvent.click(screen.getByLabelText("Nimmt aktuell"));
    await userEvent.click(screen.getByRole("button", { name: "Speichern" }));
    await waitFor(() => expect(server.calls.some((c) => c.method === "POST")).toBe(true));
    expect(server.calls.find((c) => c.method === "POST")?.body).toEqual({
      name: "Nur Name",
      dose_amount: null,
      dose_unit: null,
      nutrients_per_day: {},
      taking: false,
      time_of_day: null,
      note: null,
    });
  });

  it("bietet Schlüsselvorschläge an, ohne etwas vorzubelegen", async () => {
    serverWith([]);
    const { container } = renderPage(<SupplementsPage />);
    await userEvent.click(await screen.findByRole("button", { name: "Erstes Supplement hinzufügen" }));
    expect(screen.queryByLabelText("Nährstoff 1")).not.toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "Nährstoff hinzufügen" }));
    const key = screen.getByLabelText("Nährstoff 1");
    expect(key).toHaveValue("");
    const values = [...container.querySelectorAll(`datalist[id="${key.getAttribute("list")}"] option`)].map((o) =>
      o.getAttribute("value"),
    );
    expect(values).toEqual([
      "zinc_mg",
      "magnesium_mg",
      "vitamin_d_ug",
      "epa_dha_mg",
      "folate_ug",
      "vitamin_k2_ug",
      "creatine_g",
    ]);
  });

  it("prüft Zeilen vor dem Senden (Menge fehlt, doppelter Schlüssel)", async () => {
    const server = serverWith([]);
    renderPage(<SupplementsPage />);
    await userEvent.click(await screen.findByRole("button", { name: "Erstes Supplement hinzufügen" }));
    await userEvent.type(screen.getByLabelText("Name"), "X");
    await userEvent.click(screen.getByRole("button", { name: "Nährstoff hinzufügen" }));
    await userEvent.type(screen.getByLabelText("Nährstoff 1"), "zinc_mg");
    await userEvent.click(screen.getByRole("button", { name: "Speichern" }));
    expect(screen.getByRole("alert")).toHaveTextContent("Bitte eine Menge für „zinc_mg“ angeben.");

    await userEvent.type(screen.getByLabelText("Menge pro Tag 1"), "5");
    await userEvent.click(screen.getByRole("button", { name: "Nährstoff hinzufügen" }));
    await userEvent.type(screen.getByLabelText("Nährstoff 2"), "zinc_mg");
    await userEvent.type(screen.getByLabelText("Menge pro Tag 2"), "6");
    await userEvent.click(screen.getByRole("button", { name: "Speichern" }));
    expect(screen.getByRole("alert")).toHaveTextContent("„zinc_mg“ ist doppelt eingetragen.");

    await userEvent.click(screen.getByRole("button", { name: "Nährstoff 2 entfernen" }));
    await userEvent.click(screen.getByRole("button", { name: "Speichern" }));
    await waitFor(() => expect(server.calls.some((c) => c.method === "POST")).toBe(true));
    expect(server.calls.find((c) => c.method === "POST")?.body).toMatchObject({ nutrients_per_day: { zinc_mg: 5 } });
  });

  it("verlangt einen Namen", async () => {
    const server = serverWith([]);
    renderPage(<SupplementsPage />);
    await userEvent.click(await screen.findByRole("button", { name: "Erstes Supplement hinzufügen" }));
    await userEvent.click(screen.getByRole("button", { name: "Speichern" }));
    expect(screen.getByRole("alert")).toHaveTextContent("Bitte einen Namen angeben.");
    expect(server.calls.some((c) => c.method === "POST")).toBe(false);
  });

  it("zeigt die Servermeldung bei 422 neben dem Formular und lässt das Formular offen", async () => {
    serverWith([], {
      "POST /me/supplements": {
        status: 422,
        body: { detail: [{ loc: ["body", "nutrients_per_day"], msg: "Value error, Nährstoffmengen dürfen nicht negativ sein." }] },
      },
    });
    renderPage(<SupplementsPage />);
    await userEvent.click(await screen.findByRole("button", { name: "Erstes Supplement hinzufügen" }));
    await userEvent.type(screen.getByLabelText("Name"), "X");
    await userEvent.click(screen.getByRole("button", { name: "Speichern" }));
    const alert = await screen.findByRole("alert");
    expect(alert).toHaveTextContent("nutrients_per_day: Nährstoffmengen dürfen nicht negativ sein.");
    expect(screen.getByRole("form", { name: "Supplement hinzufügen" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Speichern" })).toBeEnabled();
  });

  it("bearbeitet ein Supplement (PUT mit vollständigem Datensatz)", async () => {
    const server = serverWith([A, B]);
    renderPage(<SupplementsPage />);
    await userEvent.click(await screen.findByRole("button", { name: "Testkapsel A bearbeiten" }));
    expect(screen.getByLabelText("Name")).toHaveValue("Testkapsel A");
    expect(screen.getByLabelText("Nährstoff 1")).toHaveValue("zinc_mg");
    expect(screen.getByLabelText("Menge pro Tag 2")).toHaveValue(600);
    expect(screen.getByLabelText("Tageszeit")).toHaveValue("abends");
    await userEvent.clear(screen.getByLabelText("Menge pro Tag 1"));
    await userEvent.type(screen.getByLabelText("Menge pro Tag 1"), "10");
    await userEvent.click(screen.getByLabelText("Nimmt aktuell"));
    await userEvent.click(screen.getByRole("button", { name: "Speichern" }));
    await waitFor(() => expect(server.calls.some((c) => c.method === "PUT")).toBe(true));
    const put = server.calls.find((c) => c.method === "PUT");
    expect(put?.path).toBe("/me/supplements/1");
    expect(put?.body).toEqual({
      name: "Testkapsel A",
      dose_amount: 500,
      dose_unit: "mg",
      nutrients_per_day: { zinc_mg: 10, epa_dha_mg: 600 },
      taking: false,
      time_of_day: "abends",
      note: "Mit Wasser",
    });
    await waitFor(() => expect(screen.queryByRole("form")).not.toBeInTheDocument());
  });

  it("löscht nach Rückfrage", async () => {
    const server = serverWith([A, B]);
    renderPage(<SupplementsPage />);
    await userEvent.click(await screen.findByRole("button", { name: "Testpulver B löschen" }));
    expect(server.calls.some((c) => c.method === "DELETE")).toBe(false);
    await userEvent.click(screen.getByRole("button", { name: "Ja, löschen" }));
    await waitFor(() => expect(server.calls.some((c) => c.method === "DELETE" && c.path === "/me/supplements/2")).toBe(true));
    await waitFor(() => expect(screen.queryByRole("heading", { name: "Testpulver B" })).not.toBeInTheDocument());
    expect(screen.getByRole("heading", { name: "Testkapsel A" })).toBeInTheDocument();
  });

  it("zeigt Fehler beim Löschen in der Rückfrage", async () => {
    serverWith([B], { "DELETE /me/supplements/2": { status: 404, body: { detail: "Nicht gefunden." } } });
    renderPage(<SupplementsPage />);
    await userEvent.click(await screen.findByRole("button", { name: "Testpulver B löschen" }));
    await userEvent.click(screen.getByRole("button", { name: "Ja, löschen" }));
    const dialog = screen.getByRole("alertdialog");
    expect(await within(dialog).findByRole("alert")).toHaveTextContent("Nicht gefunden.");
  });
});
