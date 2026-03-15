from pydantic import BaseModel, EmailStr


class Token(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user_id: int
    username: str
    expires_at: int


class TokenData(BaseModel):
    sub: str
    email: EmailStr
    exp: int
