from typing import List

from sqlalchemy import String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from database import Base, int_pk, created_at


class User(Base):
    id: Mapped[int_pk]
    username: Mapped[str] = mapped_column(String(100), index=True, nullable=False)
    user_email: Mapped[str] = mapped_column(String(255), unique=True, index=True, nullable=False)
    hashed_password: Mapped[str] = mapped_column(String(255), nullable=False)
    created_at: Mapped[created_at]

    reviews: Mapped[List["Review"]] = relationship(
        "Review",
        back_populates="user",
        cascade="all, delete-orphan",
        lazy="selectin"
    )

    def __repr__(self):
        return f"<User(id={self.id}, username={self.username}, email={self.user_email})>"
