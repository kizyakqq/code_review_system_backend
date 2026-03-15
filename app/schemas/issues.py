from datetime import datetime
from typing import Optional

from pydantic import BaseModel, ConfigDict

from app.models.enums import Severity, SuggestionType


class LinterIssueBase(BaseModel):
    line_number: int
    message: str
    rule_code: Optional[str] = None
    severity: Severity
    tool_name: Optional[str] = None


class LinterIssueResponse(LinterIssueBase):
    id: int
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class LLMSuggestionBase(BaseModel):
    line_number: int
    suggestion_type: SuggestionType
    text: str
    severity: Severity


class LLMSuggestionResponse(LLMSuggestionBase):
    id: int
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)
