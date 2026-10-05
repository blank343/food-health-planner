from app.api.crud import crud_router
from app.api.schemas import LabRuleIn, LabRuleOut
from app.models import LabRule

router = crud_router(
    db_model=LabRule,
    create=LabRuleIn,
    read=LabRuleOut,
    order_by=(LabRule.analyte, LabRule.id),
    prefix="/me/lab-rules",
    tag="Laborregeln",
)
