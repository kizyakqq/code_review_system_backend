import functools
import logging
import pathlib
from dataclasses import dataclass
from typing import Optional

import httpx

from app.config import settings

logger = logging.getLogger(__name__)


@dataclass
class LLMResponse:
    content: str
    model: str
    success: bool
    error_message: Optional[str] = None


class LLMService:
    def __init__(self) -> None:
        self.base_url = settings.OLLAMA_HOST.rstrip("/")
        self.timeout = settings.OLLAMA_TIMEOUT
        self.default_model = settings.OLLAMA_MODEL

        self._client: Optional[httpx.AsyncClient] = None

    async def _get_client(self) -> httpx.AsyncClient:
        if self._client is None or self._client.is_closed:
            self._client = httpx.AsyncClient(timeout=self.timeout)
        return self._client

    async def close(self):
        if self._client and not self._client.is_closed:
            await self._client.aclose()

    @staticmethod
    @functools.lru_cache(maxsize=10)
    def _load_prompt_template(filename: str) -> str:
        prompt_path = pathlib.Path(__file__).parent.parent / "prompts" / f"{filename}.txt"
        if not prompt_path.is_file():
            raise FileNotFoundError(f"Промт не найден: {prompt_path}")
        return prompt_path.read_text(encoding="utf-8")

    def _build_prompt(self, code: str, template_name: str) -> str:
        template = self._load_prompt_template(template_name)
        return f"""
### INSTRUCTION ###
{template}

### USER CODE INPUT ###
{code}

### END OF INPUT ###
"""

    async def generate_review(
            self,
            code: str,
            template_name: str = "system",
            model: Optional[str] = None,
    ) -> LLMResponse:
        model = model or self.default_model

        try:
            prompt = self._build_prompt(code, template_name)

            client = await self._get_client()
            url = f"{self.base_url}/api/generate"

            payload = {
                "model": model,
                "prompt": prompt,
                "stream": False,
                "options": {
                    "temperature": settings.OLLAMA_TEMPERATURE,
                    "num_predict": settings.OLLAMA_MAX_TOKENS,
                    "top_p": settings.OLLAMA_TOP_P,
                },
            }

            logger.info(f"Запрос отправлен LLM (model={model})")

            response = await client.post(url, json=payload)
            response.raise_for_status()
            result = response.json()

            if "response" not in result:
                logger.error(f"В ответе LLM нет ключа 'response': {result}")
                return LLMResponse(
                    content="", model=model, success=False,
                    error_message="Invalid LLM response structure"
                )

            logger.info(f"Получен ответ от LLM (длина={len(result['response'])})")

            return LLMResponse(
                content=result["response"],
                model=model,
                success=True
            )

        except httpx.TimeoutException as e:
            logger.error(f"Таймаут ответа от LLM: {e}")
            return LLMResponse("", model, False, f"Таймаут ответа от LLM ({self.timeout}s)")
        except httpx.ConnectError as e:
            logger.error(f"Не удалось подключиться к Ollama. Убедитесь, что сервис запущен.: {e}")
            return LLMResponse("", model, False, "Не удалось подключиться к Ollama.")
        except Exception as e:
            logger.exception(f"Ошибка при работе с LLM: {e}")
            return LLMResponse("", model, False, str(e))
