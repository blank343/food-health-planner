"""API unter `/api`. Neue Router bitte nur in der Liste unten ergänzen."""

from fastapi import APIRouter

from app.api import (
    components,
    dashboard,
    goals,
    health_data,
    imports,
    ingredient_preferences,
    ingredients,
    lab_rules,
    labs,
    me,
    measurements,
    nutrient_rules,
    recipes,
    supplements,
    targets,
    training,
)

router = APIRouter(prefix="/api")

# --- Router-Liste (neue Router hier ergänzen) ---
for _sub in (
    me.router,
    goals.router,
    supplements.router,
    nutrient_rules.router,
    training.router,
    lab_rules.router,
    imports.router,
    health_data.router,
    labs.router,
    dashboard.router,
    targets.router,
    measurements.router,
    ingredients.router,
    recipes.router,
    components.router,
    ingredient_preferences.router,
):
    router.include_router(_sub)
# --- Ende Router-Liste ---
