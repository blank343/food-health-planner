"""Verteilung eines Tagesziels auf Mahlzeiten-Slots und Prüfung einzelner Mahlzeiten."""

from app.calc.types import DayTarget, PersonSettings, SlotTarget, Warning


def _split(total_units: int, weights: dict[str, float], largest: str) -> dict[str, int]:
    """Teilt eine ganze Zahl nach Gewichten; der Rest (Rundung) geht an den größten Slot."""
    weight_sum = sum(weights.values())
    parts = {name: round(total_units * w / weight_sum) for name, w in weights.items()}
    parts[largest] += total_units - sum(parts.values())
    return parts


def distribute_to_slots(target: DayTarget, shares: dict[str, float]) -> dict[str, SlotTarget]:
    """Verteilt kcal, Protein, Fett und Kohlenhydrate nach Anteilen auf Slots.

    Die Anteile werden normalisiert. Gerundet wird auf 1 kcal bzw. 0,1 g; die Summe jedes Werts
    entspricht danach exakt dem Tagesziel (Rest im größten Slot). Slots mit Anteil 0 erhalten
    nur Nullen. Negative Anteile oder eine Summe von 0 sind ein ValueError.
    """
    if any(s < 0 for s in shares.values()):
        raise ValueError("Anteile dürfen nicht negativ sein.")
    active = {name: s for name, s in shares.items() if s > 0}
    if not active:
        raise ValueError("Mindestens ein Slot braucht einen Anteil über 0.")
    largest = max(active, key=lambda n: active[n])  # bei Gleichstand der erste
    kcal = _split(round(target.kcal), active, largest)
    protein = _split(round(target.protein_g * 10), active, largest)
    fat = _split(round(target.fat_g * 10), active, largest)
    carb = _split(round(target.carb_g * 10), active, largest)
    result: dict[str, SlotTarget] = {}
    for name in shares:
        if name in active:
            result[name] = SlotTarget(
                kcal=float(kcal[name]),
                protein_g=protein[name] / 10,
                fat_g=fat[name] / 10,
                carb_g=carb[name] / 10,
            )
        else:
            result[name] = SlotTarget(kcal=0.0, protein_g=0.0, fat_g=0.0, carb_g=0.0)
    return result


def single_meal_check(
    slot_target: SlotTarget, limits: PersonSettings, *, protein_floor_g: float | None = None
) -> list[Warning]:
    """Prüft eine Mahlzeit gegen die Obergrenze für Energie und eine Protein-Mindestmenge.

    Ohne `limits.single_meal_max_kcal` bzw. `protein_floor_g` entfällt die jeweilige Prüfung.
    """
    warnings: list[Warning] = []
    max_kcal = limits.single_meal_max_kcal
    if max_kcal is not None and slot_target.kcal > max_kcal:
        warnings.append(
            Warning(
                "meal_too_large",
                "warn",
                f"Diese Mahlzeit hat {slot_target.kcal:.0f} kcal und liegt über deiner Obergrenze von "
                f"{max_kcal:.0f} kcal. Eine so große Portion ist schwer zu essen; verteile sie besser "
                "auf mehrere Mahlzeiten.",
            )
        )
    if protein_floor_g is not None and slot_target.protein_g < protein_floor_g:
        warnings.append(
            Warning(
                "meal_protein_low",
                "info",
                f"Diese Mahlzeit hat nur {slot_target.protein_g:.0f} g Protein, empfohlen sind mindestens "
                f"{protein_floor_g:.0f} g, damit die Muskeleiweißbildung gut angeregt wird.",
            )
        )
    return warnings
