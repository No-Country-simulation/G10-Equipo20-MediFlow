"""OpenAI transport using the same documentary prompts and contracts as Gemini."""
import base64
import json
import subprocess
import sys
import tempfile
from pathlib import Path

import httpx
from pydantic import ValidationError

from app.providers.base import ProviderError
from app.providers.gemini import GeminiProvider, SYSTEM_INSTRUCTION


def strict_schema(schema):
    if isinstance(schema, list):
        return [strict_schema(value) for value in schema]
    if not isinstance(schema, dict):
        return schema
    result = {key: strict_schema(value) for key, value in schema.items() if key != "default"}
    if "properties" in result:
        result["required"] = list(result["properties"])
        result["additionalProperties"] = False
    return result


class OpenAIProvider(GeminiProvider):
    name = "openai"

    @property
    def model(self):
        return self.settings.openai_model

    def _images(self, binary):
        data, mime = binary
        if len(data) > self.settings.max_upload_bytes:
            raise ProviderError("OCR_PAYLOAD_TOO_LARGE", 413)
        if mime != "application/pdf":
            return [f"data:{mime};base64," + base64.b64encode(data).decode("ascii")]
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "ocr.pdf"
            path.write_bytes(data)
            try:
                rendered = subprocess.run([sys.executable, "-m", "app.services.pdf_ocr_images", str(path),
                    str(self.settings.processing_max_pages), str(self.settings.max_upload_bytes)],
                    timeout=self.settings.pdf_timeout_seconds, capture_output=True, check=True)
                result = json.loads(rendered.stdout)
            except subprocess.TimeoutExpired:
                raise ProviderError("PDF_READ_TIMEOUT", 504) from None
            except (subprocess.CalledProcessError, ValueError):
                raise ProviderError("PDF_CONTENT_UNREADABLE", 422) from None
            if result.get("error"):
                raise ProviderError(result["error"], 422)
            return ["data:image/png;base64," + image for image in result["images"]]

    def _generate(self, prompt, schema, binary=None):
        key = self.settings.openai_api_key.get_secret_value().strip()
        if not key:
            raise ProviderError("OPENAI_NOT_CONFIGURED", 503)
        content = [{"type": "text", "text": prompt}]
        if binary is not None:
            content.extend({"type": "image_url", "image_url": {"url": image, "detail": "high"}}
                           for image in self._images(binary))
        payload = {"model": self.model, "temperature": 0, "max_completion_tokens": 16384,
                   "messages": [{"role": "system", "content": SYSTEM_INSTRUCTION},
                                {"role": "user", "content": content}],
                   "response_format": {"type": "json_schema", "json_schema": {
                       "name": schema.__name__, "strict": True, "schema": strict_schema(schema.model_json_schema())}}}
        try:
            with httpx.Client(timeout=self.settings.gemini_timeout_seconds) as client:
                response = client.post("https://api.openai.com/v1/chat/completions",
                    headers={"Authorization": "Bearer " + key}, json=payload)
            if response.status_code in (401, 403):
                raise ProviderError("OPENAI_ACCESS_DENIED", 503)
            if response.status_code == 429:
                raise ProviderError("OPENAI_QUOTA_EXCEEDED", 503)
            if response.status_code >= 400:
                raise ProviderError("OPENAI_REQUEST_FAILED", 503)
            choice = response.json()["choices"][0]
            if choice["message"].get("refusal"):
                raise ProviderError("OPENAI_REFUSED", 422)
            if choice.get("finish_reason") != "stop":
                raise ProviderError("OPENAI_INCOMPLETE_RESPONSE", 502)
            return schema.model_validate_json(choice["message"]["content"])
        except ProviderError:
            raise
        except httpx.TimeoutException:
            raise ProviderError("OPENAI_TIMEOUT", 504) from None
        except httpx.HTTPError:
            raise ProviderError("OPENAI_UNAVAILABLE", 503) from None
        except (ValidationError, ValueError, KeyError, IndexError, TypeError):
            raise ProviderError("OPENAI_INVALID_RESPONSE", 502) from None
