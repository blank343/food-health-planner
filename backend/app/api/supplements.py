from app.api.crud import crud_router
from app.api.schemas import SupplementIn, SupplementOut
from app.models import Supplement

router = crud_router(
    db_model=Supplement,
    create=SupplementIn,
    read=SupplementOut,
    order_by=(Supplement.name, Supplement.id),
    prefix="/me/supplements",
    tag="Supplemente",
)
