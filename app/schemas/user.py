from pydantic import BaseModel, EmailStr, Field


class UserRegister(BaseModel):
    username: str = Field(..., min_length=3, max_length=20, pattern=r'^[\w\-\.]+$')
    email: EmailStr
    password: str = Field(..., min_length=8, max_length=128)


class UserAuth(BaseModel):
    email: EmailStr
    password: str = Field(..., min_length=1, max_length=128)
