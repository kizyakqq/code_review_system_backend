import pytest
from app.services.llm import LLMService


@pytest.mark.asyncio
async def test_generate_review_success():
    llm = LLMService()
    response = await llm.generate_review(
        code="print('hello')",
        template_name="system",
        model="llama3"
    )
    assert response.success is True
    assert response.content != ""
    assert response.model == "llama3"
    print(response.success)
    print(response.error_message)
    await llm.close()


@pytest.mark.asyncio
async def test_invalid_template():
    llm = LLMService()
    response = await llm.generate_review(
        code="print('hello')",
        template_name="nonexistent"
    )
    assert response.success is False
    assert "не найден" in response.error_message.lower()
    await llm.close()
