from app.api.crud import crud_router
from app.api.schemas import NutrientRuleIn, NutrientRuleOut
from app.models import NutrientRule

router = crud_router(
    db_model=NutrientRule,
    create=NutrientRuleIn,
    read=NutrientRuleOut,
    order_by=(NutrientRule.subject, NutrientRule.id),
    prefix="/me/nutrient-rules",
    tag="Ernährungsregeln",
)
