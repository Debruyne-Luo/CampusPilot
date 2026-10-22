"""Backward-compatible shim; the implementation lives in campuspilot.llm.chat_model."""

from campuspilot.llm.chat_model import SYSTEM as SYSTEM
from campuspilot.llm.chat_model import ChatCompletionsModel as ChatCompletionsModel
from campuspilot.llm.chat_model import ChatTurn as ChatTurn
from campuspilot.llm.chat_model import GroundedAnswer as GroundedAnswer
from campuspilot.llm.chat_model import ModelReply as ModelReply
from campuspilot.llm.chat_model import ProductionModel as ProductionModel
from campuspilot.llm.chat_model import bounded_json as bounded_json
from campuspilot.llm.chat_model import validate_endpoint as validate_endpoint
