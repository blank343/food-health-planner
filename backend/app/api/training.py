from app.api.crud import crud_router
from app.api.schemas import TrainingItemIn, TrainingItemOut
from app.models import TrainingPlanItem

router = crud_router(
    db_model=TrainingPlanItem,
    create=TrainingItemIn,
    read=TrainingItemOut,
    order_by=(TrainingPlanItem.weekday, TrainingPlanItem.start_time, TrainingPlanItem.id),
    prefix="/me/training-plan",
    tag="Trainingsplan",
)
