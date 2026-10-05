import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";
import { setToken } from "./api/client";
import App from "./App";
import { mockServer } from "./test/helpers";

describe("App", () => {
  it("zeigt ohne Token die Anmeldung", () => {
    mockServer({});
    render(<App />);
    expect(screen.getByRole("heading", { name: "Essensplan" })).toBeInTheDocument();
    expect(screen.getByLabelText("Zugangstoken")).toBeInTheDocument();
  });

  it("meldet mit gültigem Token an und zeigt die Navigation", async () => {
    mockServer({});
    render(<App />);
    await userEvent.type(screen.getByLabelText("Zugangstoken"), "geheim");
    await userEvent.click(screen.getByRole("button", { name: "Anmelden" }));
    await waitFor(() => expect(screen.getByText(/Angemeldet als Test A/)).toBeInTheDocument());
    expect(screen.getByRole("navigation", { name: "Hauptnavigation" })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Übersicht" })).toBeInTheDocument();
  });

  it("zeigt bei ungültigem Token eine deutsche Fehlermeldung", async () => {
    mockServer({ "GET /me": { status: 401, body: { detail: "Nicht angemeldet." } } });
    render(<App />);
    await userEvent.type(screen.getByLabelText("Zugangstoken"), "falsch");
    await userEvent.click(screen.getByRole("button", { name: "Anmelden" }));
    expect(await screen.findByText(/Das Zugangstoken ist ungültig/)).toBeInTheDocument();
  });

  it("nutzt ein gespeichertes Token beim Start", async () => {
    setToken("gespeichert");
    mockServer({});
    render(<App />);
    expect(await screen.findByText(/Angemeldet als Test A/)).toBeInTheDocument();
  });

  it("meldet ab", async () => {
    setToken("x");
    mockServer({});
    render(<App />);
    await userEvent.click(await screen.findByRole("button", { name: "Abmelden" }));
    expect(screen.getByLabelText("Zugangstoken")).toBeInTheDocument();
  });
});
