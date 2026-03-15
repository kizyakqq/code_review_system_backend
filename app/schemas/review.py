from datetime import datetime
from typing import Optional, List

from pydantic import BaseModel, Field, ConfigDict

from app.models.enums import ReviewStatus
from app.schemas.issues import LinterIssueResponse, LLMSuggestionResponse


class ReviewCreate(BaseModel):
    filename: str = Field(..., min_length=1, max_length=255)
    model_name: str = Field(default="llama3", max_length=50)


class ReviewBase(BaseModel):
    filename: str
    model_name: str
    status: ReviewStatus
    llm_summary: Optional[str] = None


class ReviewResponse(ReviewBase):
    id: int
    user_id: int
    created_at: datetime
    updated_at: datetime

    linter_issues: List[LinterIssueResponse] = []
    llm_suggestions: List[LLMSuggestionResponse] = []

    model_config = ConfigDict(from_attributes=True)


class ReviewShortResponse(BaseModel):
    id: int
    filename: str
    status: ReviewStatus
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class ReviewDetailResponse(ReviewResponse):
    code_content: str


class ReviewListResponse(BaseModel):
    items: List[ReviewShortResponse]
    total: int
    page: int
    page_size: int
