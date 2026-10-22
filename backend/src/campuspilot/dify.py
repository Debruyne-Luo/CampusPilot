"""Dify transport adapter. No prompts, routing decisions, or tool execution here."""

import asyncio
import json
from dataclasses import dataclass, field
from typing import Annotated
from urllib.parse import urlsplit
from uuid import UUID

import httpx
from pydantic import BaseModel, Field, ValidationError

from campuspilot.contracts import Contract
from campuspilot.presentation import AnswerEnvelope


class RetrievalExcerpt(Contract):
    document: str
    content: str


class ChatAnswer(Contract):
    answer: str
    excerpts: tuple[RetrievalExcerpt, ...] = ()
    references: AnswerEnvelope | None = None


class ChatUnavailable(Exception):
    """Only controlled error codes cross the integration boundary."""

    def __init__(self, code: str = "upstream_unavailable") -> None:
        super().__init__(code)
        self.code = code


class _Resource(BaseModel):
    document_name: str = "知识库片段"
    content: str = ""


class _Metadata(BaseModel):
    retriever_resources: list[_Resource] = Field(default_factory=list, max_length=100)


class _Reply(BaseModel):
    answer: Annotated[str, Field(min_length=1, max_length=100_000, pattern=r"\S")]
    conversation_id: UUID
    metadata: _Metadata = Field(default_factory=_Metadata)


@dataclass(frozen=True)
class DifyClient:
    api_key: str = field(repr=False)
    base_url: str = "https://api.dify.ai/v1"
    transport: httpx.AsyncBaseTransport | None = field(default=None, repr=False)
    structured_answers: bool = False

    def __post_init__(self) -> None:
        url = urlsplit(self.base_url)
        if (
            url.scheme != "https"
            or not url.hostname
            or url.username
            or url.password
            or url.query
            or url.fragment
        ):
            raise ValueError("Dify requires a configured HTTPS API base URL")
        if not self.api_key or not self.api_key.isascii() or any(x.isspace() for x in self.api_key):
            raise ValueError("Invalid Dify application credential")

    async def send(self, query: str, *, user: str, conversation_id: str) -> tuple[ChatAnswer, str]:
        payload = {
            "inputs": {},
            "query": query,
            "user": user,
            "conversation_id": conversation_id,
            "response_mode": "blocking",
            "auto_generate_name": False,
        }
        try:
            async with asyncio.timeout(95):
                async with httpx.AsyncClient(
                    timeout=httpx.Timeout(90, connect=10),
                    follow_redirects=False,
                    transport=self.transport,
                ) as client:
                    async with client.stream(
                        "POST",
                        self.base_url.rstrip("/") + "/chat-messages",
                        headers={"Authorization": "Bearer " + self.api_key},
                        json=payload,
                    ) as response:
                        if response.status_code in {401, 403}:
                            raise ChatUnavailable("upstream_credentials")
                        if response.status_code == 429:
                            raise ChatUnavailable("upstream_limit")
                        if response.status_code != 200:
                            raise ChatUnavailable()
                        body = bytearray()
                        async for chunk in response.aiter_bytes():
                            body.extend(chunk)
                            if len(body) > 1_000_000:
                                raise ChatUnavailable("invalid_response")
            reply = _Reply.model_validate(json.loads(body))
            if conversation_id and str(reply.conversation_id) != conversation_id:
                raise ChatUnavailable("invalid_response")
            envelope = (
                AnswerEnvelope.model_validate_json(reply.answer)
                if self.structured_answers
                else None
            )
            if envelope and envelope.status == "unavailable":
                raise ChatUnavailable("directory_unavailable")
            answer = ChatAnswer(
                answer=envelope.answer if envelope else reply.answer,
                references=envelope,
                excerpts=tuple(
                    RetrievalExcerpt(document=r.document_name[:300], content=r.content[:4000])
                    for r in reply.metadata.retriever_resources[:10]
                ),
            )
            return answer, str(reply.conversation_id)
        except (httpx.TimeoutException, TimeoutError):
            raise ChatUnavailable("upstream_timeout") from None
        except (httpx.HTTPError, ValueError, ValidationError):
            raise ChatUnavailable("invalid_response") from None
