from fastapi import APIRouter, status, UploadFile, File, Form, Depends, HTTPException
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.config import settings
from app.dependencies import get_current_user, get_db
from app.models import User, Review, LinterRule, LinterIssue, LLMSuggestion
from app.models.enums import ReviewStatus
from app.schemas.review import ReviewResponse, ReviewListResponse, ReviewShortResponse, ReviewDetailResponse
from app.services.linters.pylint_linter import LinterService
from app.services.llm import LLMService

router = APIRouter(prefix="/reviews", tags=["Code Reviews"])


@router.post(
    "/upload",
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
    if not file.filename.endswith(".py"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Only .py files are allowed"
        )

    content_bytes = await file.read()
    try:
        code = content_bytes.decode("utf-8")
    except UnicodeDecodeError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="File must be UTF-8 encoded"
        )

    if len(content_bytes) > settings.MAX_CODE_SIZE:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="File too large. Maximum size is 500 KB"
        )

    review = Review(
        user_id=current_user.id,
        filename=file.filename,
        code_content=code,
        model_name=model_name,
        status=ReviewStatus.PROCESSING
    )
    db.add(review)
    await db.flush()
    await db.refresh(review)

    try:
        linter_service = LinterService()
        linter_issues = await linter_service.run(code, file.filename)

        rule_codes = {issue.rule_code for issue in linter_issues}
        existing_rules = await db.execute(
            select(LinterRule).where(
                (LinterRule.tool_name == "pylint") &
                (LinterRule.rule_code.in_(rule_codes))
            )
        )
        rules_map = {r.rule_code: r for r in existing_rules.scalars().all()}

        new_rules = []
        for issue in linter_issues:
            rule = rules_map.get(issue.rule_code)
            if not rule:
                rule = LinterRule(
                    tool_name="pylint",
                    rule_code=issue.rule_code,
                    description=issue.message,
                    severity=issue.severity
                )
                db.add(rule)
                new_rules.append(rule)
                rules_map[issue.rule_code] = rule

        if new_rules:
            await db.flush()

        for issue in linter_issues:
            rule = rules_map[issue.rule_code]
            linter_issue = LinterIssue(
                review_id=review.id,
                rule_id=rule.id,
                line_number=issue.line_number,
                message=issue.message
            )
            db.add(linter_issue)

        llm_service = LLMService()
        llm_response = await llm_service.generate_review(
            code=code,
            template_name="system",
            model=model_name
        )

        if llm_response.success:
            review.llm_summary = llm_response.content[:10000]
            review.status = ReviewStatus.COMPLETED
        else:
            review.status = ReviewStatus.FAILED

        await db.commit()
        await db.refresh(review)

    except Exception as e:
        review.status = ReviewStatus.FAILED
        await db.commit()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Analysis failed: {str(e)}"
        )

    return review


@router.get("", response_model=ReviewListResponse)
async def list_reviews(
        page: int = 1,
        page_size: int = 10,
        current_user: User = Depends(get_current_user),
        db: AsyncSession = Depends(get_db)
):
    offset = (page - 1) * page_size

    count_query = select(func.count()).select_from(Review).where(
        Review.user_id == current_user.id
    )
    total_result = await db.execute(count_query)
    total = total_result.scalar()

    query = (
        select(Review)
        .where(Review.user_id == current_user.id)
        .order_by(Review.created_at.desc())
        .offset(offset)
        .limit(page_size)
    )
    result = await db.execute(query)
    reviews = result.scalars().all()

    return ReviewListResponse(
        items=[ReviewShortResponse.model_validate(r) for r in reviews],
        total=total,
        page=page,
        page_size=page_size
    )


@router.get("/{review_id}", response_model=ReviewDetailResponse)
async def get_review(
        review_id: int,
        current_user: User = Depends(get_current_user),
        db: AsyncSession = Depends(get_db)
):
    query = (
        select(Review)
        .options(
            selectinload(Review.linter_issues).selectinload(LinterIssue.rule),
            selectinload(Review.llm_suggestions)
        )
        .where(Review.id == review_id)
    )
    result = await db.execute(query)
    review = result.scalar_one_or_none()

    if not review:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Review not found"
        )

    if review.user_id != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You don't have access to this review"
        )

    return review


@router.delete("/{review_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_review(
        review_id: int,
        current_user: User = Depends(get_current_user),
        db: AsyncSession = Depends(get_db)
):
    result = await db.execute(
        select(Review).where(Review.id == review_id)
    )
    review = result.scalar_one_or_none()

    if not review:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Review not found"
        )

    if review.user_id != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You don't have access to this review"
        )

    await db.delete(review)
    await db.commit()
