// Zentrale Routenliste. Jede Seite liegt in `src/pages/<Name>/index.tsx` und exportiert `default`.
// Neue Seiten hier ergänzen (und nur hier). Die Reihenfolge bestimmt die Navigation.
import { type ComponentType, type LazyExoticComponent, lazy } from "react";

export type AppRoute = {
  path: string;
  label: string;
  Component: LazyExoticComponent<ComponentType>;
};

export const routes: AppRoute[] = [
  { path: "/", label: "Übersicht", Component: lazy(() => import("./pages/Dashboard")) },
  { path: "/ziele", label: "Tagesziel", Component: lazy(() => import("./pages/Targets")) },
  { path: "/rezepte", label: "Rezepte", Component: lazy(() => import("./pages/Recipes")) },
  { path: "/fruehstueck", label: "Frühstück", Component: lazy(() => import("./pages/Breakfast")) },
  { path: "/zutaten", label: "Zutaten", Component: lazy(() => import("./pages/Ingredients")) },
  { path: "/importe", label: "Importe", Component: lazy(() => import("./pages/Imports")) },
  { path: "/labor", label: "Labor", Component: lazy(() => import("./pages/Labs")) },
  { path: "/supplemente", label: "Supplemente", Component: lazy(() => import("./pages/Supplements")) },
  { path: "/regeln", label: "Ernährungsregeln", Component: lazy(() => import("./pages/NutrientRules")) },
  { path: "/training", label: "Training", Component: lazy(() => import("./pages/TrainingPlan")) },
  { path: "/laborregeln", label: "Laborregeln", Component: lazy(() => import("./pages/LabRules")) },
  { path: "/einstellungen", label: "Einstellungen", Component: lazy(() => import("./pages/Settings")) },
];
