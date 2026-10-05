import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { useState } from "react";
import { describe, expect, it, vi } from "vitest";
import { ApiError } from "../../api/client";
import { ConfirmDelete } from "./ConfirmDelete";
import { FormShell } from "./FormShell";
import { EmptyList, ResourceList } from "./ResourceList";
import { QuickToggle, SuggestField } from "./fields";
import { cleanMessage, errorText, hhmm, numDe, optText } from "./format";

describe("Hilfsfunktionen", () => {
  it("formatiert deutsch und bereinigt Meldungen", () => {
    expect(numDe(1234.5)).toBe("1.234,5");
    expect(optText("  ")).toBeNull();
    expect(optText(" a ")).toBe("a");
    expect(hhmm("07:30:00")).toBe("07:30");
    expect(hhmm(null)).toBe("");
    expect(cleanMessage("Value error, Für diese Regelart ist ein Wert erforderlich.")).toBe(
      "Für diese Regelart ist ein Wert erforderlich.",
    );
    expect(cleanMessage("a: Value error, b; c: Value error, d")).toBe("a: b; c: d");
    expect(errorText(new ApiError("Nicht gefunden.", 404))).toBe("Nicht gefunden.");
    expect(errorText(new Error("x"))).toBe("Unbekannter Fehler.");
  });
});

describe("ConfirmDelete", () => {
  it("fragt nach, setzt den Fokus auf Abbrechen und löscht erst nach Bestätigung", async () => {
    const onConfirm = vi.fn().mockResolvedValue(undefined);
    const onCancel = vi.fn();
    render(<ConfirmDelete name="Zink" onConfirm={onConfirm} onCancel={onCancel} />);
    const dialog = screen.getByRole("alertdialog");
    expect(dialog).toHaveTextContent("„Zink“ wirklich löschen?");
    expect(screen.getByRole("button", { name: "Abbrechen" })).toHaveFocus();
    expect(onConfirm).not.toHaveBeenCalled();
    await userEvent.click(screen.getByRole("button", { name: "Ja, löschen" }));
    expect(onConfirm).toHaveBeenCalledTimes(1);
  });

  it("bricht ab", async () => {
    const onCancel = vi.fn();
    render(<ConfirmDelete name="Zink" onConfirm={vi.fn()} onCancel={onCancel} />);
    await userEvent.click(screen.getByRole("button", { name: "Abbrechen" }));
    expect(onCancel).toHaveBeenCalled();
  });

  it("zeigt Fehler und sperrt die Tasten während des Löschens", async () => {
    let reject: (e: unknown) => void = () => {};
    const onConfirm = vi.fn(() => new Promise<void>((_, r) => (reject = r)));
    render(<ConfirmDelete name="Zink" onConfirm={onConfirm} onCancel={vi.fn()} />);
    await userEvent.click(screen.getByRole("button", { name: "Ja, löschen" }));
    expect(screen.getByRole("button", { name: "Löscht …" })).toBeDisabled();
    expect(screen.getByRole("button", { name: "Abbrechen" })).toBeDisabled();
    reject(new ApiError("Nicht gefunden.", 404));
    expect(await screen.findByRole("alert")).toHaveTextContent("Nicht gefunden.");
    expect(screen.getByRole("button", { name: "Ja, löschen" })).toBeEnabled();
  });
});

describe("FormShell", () => {
  it("speichert, zeigt Servermeldungen (ohne englische Vorsilbe) und sperrt während des Speicherns", async () => {
    let reject: (e: unknown) => void = () => {};
    const onSubmit = vi.fn(() => new Promise<void>((_, r) => (reject = r)));
    render(
      <FormShell title="Test" onSubmit={onSubmit} onCancel={vi.fn()}>
        <input aria-label="Feld" />
      </FormShell>,
    );
    expect(screen.getByRole("form", { name: "Test" })).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "Speichern" }));
    expect(screen.getByRole("button", { name: "Speichert …" })).toBeDisabled();
    expect(screen.getByRole("button", { name: "Abbrechen" })).toBeDisabled();
    reject(new ApiError("Value error, Für diese Regelart ist ein Wert erforderlich.", 422));
    expect(await screen.findByRole("alert")).toHaveTextContent("Für diese Regelart ist ein Wert erforderlich.");
    expect(screen.getByRole("alert")).not.toHaveTextContent("Value error");
    expect(screen.getByRole("button", { name: "Speichern" })).toBeEnabled();
  });

  it("prüft vor dem Senden und sendet bei Fehler nicht", async () => {
    const onSubmit = vi.fn().mockResolvedValue(undefined);
    render(
      <FormShell title="Test" onSubmit={onSubmit} onCancel={vi.fn()} validate={() => "Bitte einen Namen angeben."}>
        <input aria-label="Feld" />
      </FormShell>,
    );
    await userEvent.click(screen.getByRole("button", { name: "Speichern" }));
    expect(screen.getByRole("alert")).toHaveTextContent("Bitte einen Namen angeben.");
    expect(onSubmit).not.toHaveBeenCalled();
  });

  it("ruft Abbrechen auf", async () => {
    const onCancel = vi.fn();
    render(
      <FormShell title="Test" onSubmit={vi.fn()} onCancel={onCancel}>
        <span />
      </FormShell>,
    );
    await userEvent.click(screen.getByRole("button", { name: "Abbrechen" }));
    expect(onCancel).toHaveBeenCalled();
  });
});

type Item = { id: number; name: string };

function Harness({ onRemove }: { onRemove: (id: number) => Promise<unknown> }) {
  const [editing, setEditing] = useState<number | null>(null);
  const items: Item[] = [
    { id: 1, name: "Alpha" },
    { id: 2, name: "Beta" },
  ];
  return (
    <ResourceList
      items={items}
      ariaLabel="Einträge"
      label={(i) => i.name}
      renderItem={(i) => <h3>{i.name}</h3>}
      renderExtra={(i) => <span>Extra {i.id}</span>}
      editingId={editing}
      onEdit={(i) => setEditing(i.id)}
      renderEditor={(i) => (
        <div>
          Editor {i.name} <button onClick={() => setEditing(null)}>Zu</button>
        </div>
      )}
      onRemove={onRemove}
    />
  );
}

describe("ResourceList", () => {
  it("zeigt Einträge mit Bearbeiten und Löschen je Eintrag", () => {
    render(<Harness onRemove={vi.fn()} />);
    const list = screen.getByRole("list", { name: "Einträge" });
    expect(within(list).getAllByRole("listitem")).toHaveLength(2);
    expect(screen.getByRole("button", { name: "Alpha bearbeiten" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Beta löschen" })).toBeInTheDocument();
    expect(screen.getByText("Extra 2")).toBeInTheDocument();
  });

  it("ersetzt den Eintrag beim Bearbeiten durch den Editor", async () => {
    render(<Harness onRemove={vi.fn()} />);
    await userEvent.click(screen.getByRole("button", { name: "Alpha bearbeiten" }));
    expect(screen.getByText(/Editor Alpha/)).toBeInTheDocument();
    expect(screen.queryByRole("heading", { name: "Alpha" })).not.toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "Beta" })).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "Zu" }));
    expect(screen.getByRole("heading", { name: "Alpha" })).toBeInTheDocument();
  });

  it("löscht erst nach Rückfrage", async () => {
    const onRemove = vi.fn().mockResolvedValue(undefined);
    render(<Harness onRemove={onRemove} />);
    await userEvent.click(screen.getByRole("button", { name: "Beta löschen" }));
    expect(onRemove).not.toHaveBeenCalled();
    const dialog = screen.getByRole("alertdialog");
    expect(dialog).toHaveTextContent("„Beta“ wirklich löschen?");
    await userEvent.click(within(dialog).getByRole("button", { name: "Abbrechen" }));
    expect(screen.queryByRole("alertdialog")).not.toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "Beta löschen" }));
    await userEvent.click(screen.getByRole("button", { name: "Ja, löschen" }));
    await waitFor(() => expect(onRemove).toHaveBeenCalledWith(2));
    await waitFor(() => expect(screen.queryByRole("alertdialog")).not.toBeInTheDocument());
  });
});

describe("weitere Bausteine", () => {
  it("EmptyList zeigt Text und Aktion", async () => {
    const onAction = vi.fn();
    render(
      <EmptyList actionLabel="Los" onAction={onAction}>
        Noch nichts da.
      </EmptyList>,
    );
    expect(screen.getByText("Noch nichts da.")).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "Los" }));
    expect(onAction).toHaveBeenCalled();
  });

  it("QuickToggle trägt den Eintragsnamen im zugänglichen Namen", async () => {
    const onChange = vi.fn();
    render(<QuickToggle label="aktiv" name="Salz" checked={false} onChange={onChange} />);
    await userEvent.click(screen.getByRole("checkbox", { name: "aktiv: Salz" }));
    expect(onChange).toHaveBeenCalledWith(true);
  });

  it("SuggestField verknüpft die Vorschlagsliste und übernimmt nichts automatisch", () => {
    const { container } = render(
      <SuggestField label="Gegenstand" value="" onChange={() => {}} options={[{ value: "salt_g", label: "Salz (g)" }]} />,
    );
    const input = screen.getByLabelText("Gegenstand");
    expect(input).toHaveValue("");
    const listId = input.getAttribute("list");
    expect(listId).toBeTruthy();
    const options = container.querySelectorAll(`datalist[id="${listId}"] option`);
    expect(options).toHaveLength(1);
    expect(options[0]?.getAttribute("value")).toBe("salt_g");
  });
});
