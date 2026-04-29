from fastapi import APIRouter, status, UploadFile, File, Form, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.dependencies import get_current_user, get_db
from app.models import User
from app.schemas.review import ReviewResponse

router = APIRouter()


@router.post(
    "/reviews",
    response_model=ReviewResponse,
    summary="Отправить код на рецензирование",
    status_code=status.HTTP_201_CREATED
)
async def create_code_review(
        file: UploadFile = File(..., description="Python файл для анализа"),
        model_name: str = Form(default="llama3"),
        current_user: User = Depends(get_current_user),
        db: AsyncSession = Depends(get_db)
):
    pass
