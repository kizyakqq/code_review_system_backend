import asyncio
import logging

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

logger = logging.getLogger(__name__)

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

    logger.info(f"Review created: id={review.id}, user_id={current_user.id}, filename={file.filename}")

    try:
        linter_task = LinterService().run(code, file.filename)
        llm_task = LLMService().generate_structured_review(code, "system", model_name)

        linter_issues, llm_result = await asyncio.gather(linter_task, llm_task, return_exceptions=True)

        if isinstance(linter_issues, Exception):
            logger.error(f"Linter failed: {linter_issues}")
            linter_issues = []

        llm_failed = isinstance(llm_result, Exception) or not llm_result.success
        if llm_failed:
            error_msg = str(llm_result) if isinstance(llm_result, Exception) else llm_result.error_message
            logger.warning(f"LLM failed: {error_msg}")

        rule_codes = {issue.rule_code for issue in linter_issues if issue.rule_code}
        rules_map = {}

        if rule_codes:
            existing_rules = await db.execute(
                select(LinterRule).where(
                    (LinterRule.tool_name == "pylint") &
                    (LinterRule.rule_code.in_(rule_codes))
                )
            )
            rules_map = {r.rule_code: r for r in existing_rules.scalars().all()}

        for issue in linter_issues:
            if not issue.rule_code:
                continue

            rule = rules_map.get(issue.rule_code)
            if not rule:
                rule = LinterRule(
                    tool_name="pylint",
                    rule_code=issue.rule_code,
                    description=issue.message,
                    severity=issue.severity
                )
                db.add(rule)
                await db.flush()
                rules_map[issue.rule_code] = rule

            db.add(LinterIssue(
                review_id=review.id,
                rule_id=rule.id,
                line_number=issue.line_number,
                message=issue.message,
                severity=issue.severity
            ))

        max_lines = len(code.splitlines())
        if not llm_failed and llm_result.suggestions:
            for suggestion in llm_result.suggestions:
                if 1 <= suggestion.line_number <= max_lines:
                    db.add(LLMSuggestion(
                        review_id=review.id,
                        line_number=suggestion.line_number,
                        suggestion_type=suggestion.suggestion_type,
                        text=suggestion.text,
                        severity=suggestion.severity
                    ))

        if llm_failed and not linter_issues:
            review.status = ReviewStatus.FAILED
            review.llm_summary = f"LLM error: {getattr(llm_result, 'error_message', str(llm_result))}"
        else:
            review.status = ReviewStatus.COMPLETED
            review.llm_summary = getattr(
                llm_result,
                "summary",
                "Analysis completed with partial data.")[
                                 :10000] if not llm_failed else "LLM analysis failed. Linter results only."

        await db.commit()

        review_with_relations = await db.execute(
            select(Review)
            .options(
                selectinload(Review.linter_issues).joinedload(LinterIssue.rule),
                selectinload(Review.llm_suggestions)
            )
            .where(Review.id == review.id)
        )
        review = review_with_relations.scalar_one()

    except Exception as e:
        await db.rollback()
        review.status = ReviewStatus.FAILED
        await db.commit()
        logger.exception(f"Review analysis failed: id={review.id}, error={e}")
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
    if page < 1:
        page = 1
    if page_size < 1 or page_size > 100:
        page_size = 10

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
            selectinload(Review.linter_issues).joinedload(LinterIssue.rule),
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
