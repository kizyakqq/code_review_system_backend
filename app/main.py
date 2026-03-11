from fastapi import FastAPI

from app.config import BASE_DIR

app = FastAPI(
    title="Code Review",
    version="1.0.0"
)


@app.get("/")
def home_page():
    return {"message": "Система рецензирования кода с LLM"}
