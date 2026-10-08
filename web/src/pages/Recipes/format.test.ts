import { describe, expect, it } from "vitest";
import {
  defaultSlotForHour,
  deviationText,
  existingRecipeId,
  factorText,
  fitLevel,
  guessName,
  macroShares,
  minutesDetail,
  minutesText,
  quantityText,
  satietyLevel,
  scaleNutrients,
  splitLines,
} from "./format";
import { parseId } from "./index";

describe("Hilfsfunktionen der Rezeptseiten", () => {
  it("wählt die Mahlzeit nach Tageszeit", () => {
    expect([0, 9, 10, 14, 15, 20, 21, 23].map(defaultSlotForHour)).toEqual([
      "breakfast",
      "breakfast",
      "lunch",
      "lunch",
      "dinner",
      "dinner",
      "snack",
      "snack",
    ]);
  });

  it("formuliert den Portionsfaktor", () => {
    expect(factorText(1.3)).toBe("1,3-fache Portion");
    expect(factorText(2)).toBe("2-fache Portion");
    expect(factorText(0.55)).toBe("0,55-fache Portion");
  });

  it("stuft den Fit-Score in Worte ein", () => {
    expect(fitLevel(95)).toEqual({ label: "sehr gut", kind: "ok" });
    expect(fitLevel(80).label).toBe("sehr gut");
    expect(fitLevel(79.9).label).toBe("gut");
    expect(fitLevel(45).kind).toBe("warn");
    expect(fitLevel(10)).toEqual({ label: "schlecht", kind: "error" });
    expect(satietyLevel(70)).toBe("hoch");
    expect(satietyLevel(50)).toBe("mittel");
    expect(satietyLevel(10)).toBe("niedrig");
  });

  it("berechnet Anteil und Abweichung am Ziel und schützt vor Ziel 0", () => {
    const rows = macroShares(
      { kcal: 450, protein_g: 66, fat_g: 10, carb_g: 5 },
      { kcal: 900, protein_g: 60, fat_g: 10, carb_g: 0 },
    );
    expect(rows.map((r) => (r.pct === null ? null : Math.round(r.pct)))).toEqual([50, 110, 100, null]);
    expect(rows.map((r) => deviationText(r.deviation))).toEqual([
      "50 % unter dem Ziel",
      "10 % über dem Ziel",
      "trifft das Ziel",
      "kein Ziel",
    ]);
  });

  it("skaliert Nährwerte einschließlich Mikros", () => {
    const n = scaleNutrients(
      { kcal: 100, protein_g: 10, fat_g: 5, carb_g: 20, fiber_g: 2, salt_g: 1, micros: { zinc_mg: 3 } },
      1.5,
    );
    expect(n).toEqual({ kcal: 150, protein_g: 15, fat_g: 7.5, carb_g: 30, fiber_g: 3, salt_g: 1.5, micros: { zinc_mg: 4.5 } });
  });

  it("formatiert Zeiten und Mengen", () => {
    expect(minutesText(null, null)).toBe("–");
    expect(minutesText(10, null)).toBe("10 Min.");
    expect(minutesText(10, 35)).toBe("45 Min.");
    expect(minutesDetail(10, 35)).toBe("10 Min. Vorbereitung, 35 Min. Kochen");
    expect(minutesDetail(null, 20)).toBe("20 Min. Kochen");
    expect(minutesDetail(null, null)).toBe("");
    expect(quantityText(1.5, "EL")).toBe("1,5 EL");
    expect(quantityText(2, null)).toBe("2");
    expect(quantityText(null, "g")).toBe("–");
  });

  it("rät den Zutatennamen aus einer Zeile", () => {
    expect(guessName("200 g Mehl")).toBe("Mehl");
    expect(guessName("1 Zwiebel")).toBe("Zwiebel");
    expect(guessName("2 EL Olivenöl")).toBe("Olivenöl");
    expect(guessName("½ Bund Petersilie")).toBe("Petersilie");
    expect(guessName("3-4 Karotten")).toBe("Karotten");
    expect(guessName("500 ml Milch (3,5 % Fett)")).toBe("Milch");
    expect(guessName("1 Liter Brühe")).toBe("Brühe");
    expect(guessName("Salz und Pfeffer")).toBe("Salz und Pfeffer");
    expect(guessName("1 Einheit Suppengrün: Karotte, Sellerie")).toBe("Einheit Suppengrün");
    expect(guessName("200 g Tomaten, gehackt")).toBe("Tomaten");
    expect(guessName("")).toBe("");
  });

  it("zerlegt Text in Zeilen ohne Leerzeilen", () => {
    expect(splitLines(" a \r\n\r\n b\n")).toEqual(["a", "b"]);
    expect(splitLines("")).toEqual([]);
  });

  it("liest die ID aus der 409-Meldung", () => {
    expect(existingRecipeId("Dieses Rezept ist schon vorhanden (ID 12).")).toBe(12);
    expect(existingRecipeId("Anderer Text")).toBeNull();
  });

  it("liest die Rezept-ID aus der Adresse nur bei gültigen Werten", () => {
    expect(parseId("12")).toBe(12);
    expect(parseId("0")).toBeNull();
    expect(parseId("-3")).toBeNull();
    expect(parseId("abc")).toBeNull();
    expect(parseId("1.5")).toBeNull();
    expect(parseId(null)).toBeNull();
  });
});
