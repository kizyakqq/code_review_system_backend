import asyncio
import json
import logging
import os
import subprocess
import tempfile
from typing import Optional, List

from app.config import settings
from app.models.enums import Severity
from app.schemas.issues import LinterIssueBase

logger = logging.getLogger(__name__)


class LinterService:
    ALLOWED_EXTENSIONS = {".py"}

    SAVE_CHARS = set("abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789_-.")

    def __init__(self):
        self.timeout = settings.LINTER_TIMEOUT
        self.max_code_size = settings.MAX_CODE_SIZE
        self.max_line_length = settings.MAX_LINE_LENGTH

    @classmethod
    def _sanitize_filename(cls, filename: str) -> str:
        if not filename:
            return "code.py"

        sanitized = "".join(char for char in filename if char in cls.SAVE_CHARS)
        if sanitized.startswith(".") and "." not in sanitized[1:]:
            return "code.py"

        sanitized = sanitized.lstrip(".")

        if not sanitized:
            return "code.py"

        if not sanitized.endswith(".py"):
            if "." in sanitized:
                base = sanitized[: sanitized.rfind(".")]
                sanitized = (base or "code") + ".py"
            else:
                sanitized = sanitized + ".py"

        return sanitized or "code.py"

    def _validate_code_size(self, code: str) -> None:
        size = len(code.encode("utf-8"))
        if size > self.max_code_size:
            raise ValueError(
                f"Превышен лимит размера кода: {size} > {settings.MAX_CODE_SIZE} байт"
            )

    async def run(self, code: str, filename: Optional[str] = None) -> List[LinterIssueBase]:
        issues: List[LinterIssueBase] = []
        temp_path = ""
        code = code.replace('\r\n', '\n').replace('\r', '\n')

        try:
            self._validate_code_size(code)
        except ValueError as e:
            logger.warning(f"Code size validation failed: {e}")
            return [LinterIssueBase(
                line_number=0, rule_code="SIZE_ERROR",
                message=str(e), severity=Severity.ERROR
            )]

        try:
            with tempfile.NamedTemporaryFile(
                    mode="w", suffix=".py", delete=False,
                    encoding="utf-8", prefix="pylint_"
            ) as f:
                f.write(code)
                temp_path = f.name

            cmd = [
                "pylint",
                "--output-format=json",
                "--reports=no",
                "--score=no",
                f"--max-line-length={self.max_line_length}",
                "--disable=C0114,C0115,C0116",
                temp_path
            ]

            proc = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )

            try:
                stdout, stderr = await asyncio.wait_for(
                    proc.communicate(),
                    timeout=self.timeout
                )
            except asyncio.TimeoutError:
                logger.error(f"Pylint timeout после {self.timeout}с")
                return [LinterIssueBase(
                    line_number=0, rule_code="TIMEOUT",
                    message=f"Analysis timeout ({self.timeout}s)",
                    severity=Severity.CRITICAL
                )]

            if stdout:
                try:
                    results = json.loads(stdout.decode())
                    if isinstance(results, list):
                        for item in results:
                            issues.append(LinterIssueBase(
                                line_number=item.get("line", 0),
                                column=item.get("column", 0),
                                rule_code=item.get("symbol", "UNKNOWN"),
                                message=item.get("message", ""),
                                severity=self._map_severity(item.get("type", "error")),
                                source="pylint"
                            ))
                except json.JSONDecodeError as e:
                    logger.error(f"Не удалось запарсить вывод: {e}")
                    return [LinterIssueBase(
                        line_number=0, rule_code="PARSE_ERROR",
                        message="Failed to parse linter output",
                        severity=Severity.ERROR
                    )]

        except FileNotFoundError:
            logger.error("Pylint не найден")
            return [LinterIssueBase(
                line_number=0, rule_code="NOT_INSTALLED",
                message="pylint is not installed",
                severity=Severity.CRITICAL
            )]
        except Exception as e:
            logger.exception(f"Ошибка линтера: {e}")
            return [LinterIssueBase(
                line_number=0, rule_code="INTERNAL_ERROR",
                message=str(e), severity=Severity.CRITICAL
            )]
        finally:
            if temp_path and os.path.exists(temp_path):
                try:
                    os.unlink(temp_path)
                except OSError as e:
                    logger.warning(f"Failed to cleanup temp file: {e}")

        return issues

    @staticmethod
    def _map_severity(pylint_type: str) -> Severity:
        mapping = {
            "error": Severity.ERROR,
            "fatal": Severity.CRITICAL,
            "warning": Severity.WARNING,
            "refactor": Severity.INFO,
            "convention": Severity.INFO,
        }
        return mapping.get(pylint_type, Severity.INFO)
