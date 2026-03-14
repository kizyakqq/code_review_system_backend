from typing import Optional, List

from sqlalchemy import ForeignKey, Text, String, Enum, Index, UniqueConstraint, CheckConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base, int_pk
from app.models.enums import ReviewStatus, Severity


class Review(Base):
    __tablename__ = "reviews"

    id: Mapped[int_pk]
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id"),
        nullable=False,
        index=True
    )
    code_content: Mapped[str] = mapped_column(Text, nullable=False)
    filename: Mapped[str] = mapped_column(String(255), nullable=False)
    model_name: Mapped[str] = mapped_column(String(50), nullable=False, default="llama3")
    status: Mapped[ReviewStatus] = mapped_column(
        Enum(ReviewStatus),
        nullable=False,
        default=ReviewStatus.PENDING,
        index=True
    )
    llm_summary: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    __table_args__ = (
        CheckConstraint("octet_length(code_content) <= 524288", name="check_code_content_size"),
        Index("ix_reviews_user_created", "user_id", "created_at"),
    )

    user: Mapped["User"] = relationship("User", back_populates="reviews")
    linter_issues: Mapped[List["LinterIssue"]] = relationship(
        "LinterIssue",
        back_populates="review",
        cascade="all, delete-orphan",
        lazy="selectin"
    )
    llm_suggestions: Mapped[List["LLMSuggestion"]] = relationship(
        "LLMSuggestion",
        back_populates="review",
        cascade="all, delete-orphan",
        lazy="selectin"
    )

    def __str__(self):
        return (f"{self.__class__.__name__}(id={self.id}, "
                f"filename={self.filename!r}, "
                f"status={self.status!r})")

    def __repr__(self):
        return str(self)


class LinterRule(Base):
    __tablename__ = "linter_rules"

    id: Mapped[int_pk]
    tool_name: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    rule_code: Mapped[str] = mapped_column(String(50), nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text)
    severity: Mapped[Severity] = mapped_column(
        Enum(Severity),
        nullable=False,
        default=Severity.INFO,
        index=True
    )

    __table_args__ = (
        UniqueConstraint("tool_name", "rule_code", name="uq_linter_rules_tool_code"),
    )

    issues: Mapped[List["LinterIssue"]] = relationship("LinterIssue", back_populates="rule")

    def __str__(self):
        return (f"{self.__class__.__name__}(id={self.id}, "
                f"tool={self.tool_name!r}, "
                f"code={self.rule_code!r})")

    def __repr__(self):
        return str(self)


class LinterIssue(Base):
    __tablename__ = "linter_issues"

    id: Mapped[int_pk]
    review_id: Mapped[int] = mapped_column(
        ForeignKey("reviews.id"),
        index=True,
        nullable=False
    )
    rule_id: Mapped[int] = mapped_column(
        ForeignKey("linter_rules.id"),
        index=True,
        nullable=False
    )
    line_number: Mapped[int] = mapped_column(nullable=False)
    message: Mapped[str] = mapped_column(Text, nullable=False)

    review: Mapped["Review"] = relationship("Review", back_populates="linter_issues")
    rule: Mapped["LinterRule"] = relationship("LinterRule", back_populates="linter_issues")

    def __str__(self):
        return (f"{self.__class__.__name__}(id={self.id}, "
                f"review_id={self.review_id!r}, "
                f"message={self.message!r})")

    def __repr__(self):
        return str(self)


class LLMSuggestion(Base):
    __tablename__ = "llm_suggestions"

    id: Mapped[int_pk]
    review_id: Mapped[int] = mapped_column(
        ForeignKey("reviews.id"),
        index=True,
        nullable=False
    )
    line_number: Mapped[int] = mapped_column(nullable=False)
    suggestion_type: Mapped[str] = mapped_column(String(20), default="comment")
    text: Mapped[str] = mapped_column(Text, nullable=False)
    severity: Mapped[Severity] = mapped_column(
        Enum(Severity),
        nullable=False,
        default=Severity.INFO
    )

    review: Mapped["Review"] = relationship("Review", back_populates="llm_suggestions")

    def __str__(self):
        return (f"{self.__class__.__name__}(id={self.id}, "
                f"review_id={self.review_id!r}, "
                f"suggestion={self.text!r})")

    def __repr__(self):
        return str(self)
