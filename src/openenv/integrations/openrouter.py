"""OpenRouter integration for improving bot markdown documents with tool calling."""

from __future__ import annotations

import json
import urllib.error
import urllib.request
from collections.abc import Callable
from typing import Any

from openenv.core.errors import OpenEnvError


OPENROUTER_API_URL = "https://openrouter.ai/api/v1/chat/completions"
DEFAULT_OPENROUTER_MODEL = "google/gemini-2.0-flash-001"
DEFAULT_OUTPUT_LANGUAGE = "English"
DEFAULT_DOCUMENT_BATCH_SIZE = 2
MAX_TOOL_CALL_ROUNDS = 8


def improve_markdown_documents_with_openrouter(
    *,
    api_key: str,
    bot_name: str,
    context_payload: dict[str, Any],
    instruction: str,
    write_document: Callable[[str, str], None],
    model: str | None = None,
    output_language: str = DEFAULT_OUTPUT_LANGUAGE,
    batch_size: int = DEFAULT_DOCUMENT_BATCH_SIZE,
) -> str:
    """Use OpenRouter tool calling to inspect and rewrite bot markdown files."""
    documents = context_payload.get("documents")
    if not isinstance(documents, dict):
        raise OpenEnvError("context_payload.documents must be an object mapping files to text.")
    if batch_size < 1:
        raise OpenEnvError("batch_size must be at least 1.")

    working_context = _clone_context_payload(context_payload)
    allowed_files = sorted(working_context["documents"].keys())
    if not allowed_files:
        return "No markdown documents were available for improvement."

    batches = list(_document_batches(allowed_files, batch_size))
    summaries: list[str] = []

    def tracked_write_document(file_name: str, content: str) -> None:
        """Persist one updated file and refresh the working context for later batches."""
        write_document(file_name, content)
        working_context["documents"][file_name] = content

    for index, batch_files in enumerate(batches, start=1):
        batch_context = _context_payload_for_batch(
            working_context,
            batch_files=batch_files,
            batch_index=index,
            total_batches=len(batches),
        )
        summary = _improve_markdown_documents_batch(
            api_key=api_key,
            bot_name=bot_name,
            context_payload=batch_context,
            instruction=instruction,
            write_document=tracked_write_document,
            model=model,
            output_language=output_language,
        )
        if summary:
            summaries.append(summary)

    if len(summaries) == 1:
        return summaries[0]
    return " | ".join(
        f"Batch {index}: {summary}" for index, summary in enumerate(summaries, start=1)
    )


def _improve_markdown_documents_batch(
    *,
    api_key: str,
    bot_name: str,
    context_payload: dict[str, Any],
    instruction: str,
    write_document: Callable[[str, str], None],
    model: str | None = None,
    output_language: str = DEFAULT_OUTPUT_LANGUAGE,
) -> str:
    """Use OpenRouter tool calling to inspect and rewrite one document batch."""
    allowed_files = sorted(context_payload["documents"].keys())
    batch_info = _batch_prompt_suffix(context_payload.get("document_batch"))
    messages: list[dict[str, Any]] = [
        {
            "role": "system",
            "content": (
                "You improve markdown documents for an OpenClaw bot. "
                "Always call get_bot_context first. Then decide whether to call "
                "write_bot_documents to update one or more files. "
                "Keep the docs concise, internally consistent, and aligned with "
                "the bot manifest, skills, access notes, and runtime constraints. "
                f"All resulting markdown files must be written in {output_language}. "
                "If source documents use another language, translate and normalize "
                f"them into consistent {output_language}. "
                "Do not expose or invent secret values. "
                "Only write the allowed markdown files. "
                f"{batch_info}"
                "After finishing, respond with a brief summary of what changed."
            ),
        },
        {
            "role": "user",
            "content": (
                f"Improve the markdown files for bot `{bot_name}`.\n"
                "The final versions of every markdown document must be consistently "
                f"written in {output_language}.\n"
                f"{batch_info}"
                f"User instruction: {instruction.strip() or 'Improve overall quality and consistency.'}"
            ),
        },
    ]
    tools = _tool_definitions(allowed_files)

    for _ in range(MAX_TOOL_CALL_ROUNDS):
        response_message = _openrouter_chat_completion(
            api_key=api_key,
            model=model or DEFAULT_OPENROUTER_MODEL,
            messages=messages,
            tools=tools,
        )
        assistant_message = _normalize_assistant_message(response_message)
        messages.append(assistant_message)
        tool_calls = assistant_message.get("tool_calls") or []
        if not tool_calls:
            return _assistant_text(assistant_message) or "Markdown documents reviewed."
        for tool_call in tool_calls:
            tool_name = tool_call["function"]["name"]
            arguments = _decode_tool_arguments(tool_call["function"].get("arguments", "{}"))
            if tool_name == "get_bot_context":
                result = context_payload
            elif tool_name == "write_bot_documents":
                result = _apply_document_updates(
                    arguments,
                    allowed_files=allowed_files,
                    write_document=write_document,
                )
            else:
                raise OpenEnvError(f"Unsupported OpenRouter tool call: {tool_name}")
            messages.append(
                {
                    "role": "tool",
                    "tool_call_id": tool_call["id"],
                    "content": json.dumps(result, ensure_ascii=False),
                }
            )
    raise OpenEnvError("OpenRouter did not finish the document update flow.")


def _clone_context_payload(context_payload: dict[str, Any]) -> dict[str, Any]:
    """Copy the mutable document mapping so batching can update it safely in place."""
    documents = context_payload.get("documents")
    if not isinstance(documents, dict):
        raise OpenEnvError("context_payload.documents must be an object mapping files to text.")
    cloned = dict(context_payload)
    cloned["documents"] = dict(documents)
    return cloned


def _document_batches(files: list[str], batch_size: int) -> list[list[str]]:
    """Split allowed document names into deterministic fixed-size batches."""
    return [files[index : index + batch_size] for index in range(0, len(files), batch_size)]


def _context_payload_for_batch(
    context_payload: dict[str, Any],
    *,
    batch_files: list[str],
    batch_index: int,
    total_batches: int,
) -> dict[str, Any]:
    """Narrow the context payload to the files processed in one OpenRouter request."""
    documents = context_payload["documents"]
    return {
        **context_payload,
        "document_batch": {
            "batch_index": batch_index,
            "total_batches": total_batches,
            "batch_files": list(batch_files),
            "all_files": sorted(documents.keys()),
        },
        "documents": {file_name: documents[file_name] for file_name in batch_files},
    }


def _batch_prompt_suffix(batch_payload: Any) -> str:
    """Render additional prompt instructions that constrain one batch to its file subset."""
    if not isinstance(batch_payload, dict):
        return ""
    batch_index = batch_payload.get("batch_index")
    total_batches = batch_payload.get("total_batches")
    batch_files = batch_payload.get("batch_files")
    if (
        not isinstance(batch_index, int)
        or not isinstance(total_batches, int)
        or total_batches <= 1
        or not isinstance(batch_files, list)
    ):
        return ""
    files_text = ", ".join(file_name for file_name in batch_files if isinstance(file_name, str))
    return (
        f"You are processing batch {batch_index} of {total_batches}. "
        f"Only update these files in this batch: {files_text}. "
    )


def _tool_definitions(allowed_files: list[str]) -> list[dict[str, Any]]:
    """Return the tool schema exposed to OpenRouter for document inspection and writes."""
    return [
        {
            "type": "function",
            "function": {
                "name": "get_bot_context",
                "description": (
                    "Return the current bot configuration and the current markdown documents."
                ),
                "parameters": {
                    "type": "object",
                    "properties": {},
                    "additionalProperties": False,
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "write_bot_documents",
                "description": "Write updated content to one or more bot markdown files.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "updates": {
                            "type": "array",
                            "items": {
                                "type": "object",
                                "properties": {
                                    "file": {
                                        "type": "string",
                                        "enum": allowed_files,
                                    },
                                    "content": {"type": "string"},
                                },
                                "required": ["file", "content"],
                                "additionalProperties": False,
                            },
                        }
                    },
                    "required": ["updates"],
                    "additionalProperties": False,
                },
            },
        },
    ]


def _openrouter_chat_completion(
    *,
    api_key: str,
    model: str,
    messages: list[dict[str, Any]],
    tools: list[dict[str, Any]],
) -> dict[str, Any]:
    """Send one chat-completions request to OpenRouter and return the assistant message."""
    payload = {
        "model": model,
        "messages": messages,
        "tools": tools,
    }
    request = urllib.request.Request(
        OPENROUTER_API_URL,
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
            "X-Title": "OpenClawenv",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(request) as response:
            data = json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        raise OpenEnvError(f"OpenRouter request failed with HTTP {exc.code}: {detail}") from exc
    except urllib.error.URLError as exc:
        raise OpenEnvError(f"OpenRouter is not reachable: {exc.reason}") from exc
    try:
        return data["choices"][0]["message"]
    except (KeyError, IndexError, TypeError) as exc:
        raise OpenEnvError("OpenRouter returned an unexpected response payload.") from exc


def _normalize_assistant_message(message: dict[str, Any]) -> dict[str, Any]:
    """Trim the raw OpenRouter assistant payload to the fields reused in later rounds."""
    normalized: dict[str, Any] = {"role": message.get("role", "assistant")}
    if "content" in message:
        normalized["content"] = message["content"]
    if "tool_calls" in message:
        normalized["tool_calls"] = message["tool_calls"]
    return normalized


def _assistant_text(message: dict[str, Any]) -> str:
    """Extract plain assistant text from either string or structured content payloads."""
    content = message.get("content")
    if isinstance(content, str):
        return content.strip()
    if isinstance(content, list):
        parts: list[str] = []
        for item in content:
            if isinstance(item, dict) and item.get("type") == "text":
                text = item.get("text")
                if isinstance(text, str):
                    parts.append(text)
        return "\n".join(part for part in parts if part).strip()
    return ""


def _decode_tool_arguments(raw_arguments: str) -> dict[str, Any]:
    """Decode JSON tool arguments returned by OpenRouter and enforce object shape."""
    try:
        decoded = json.loads(raw_arguments)
    except json.JSONDecodeError as exc:
        raise OpenEnvError(f"OpenRouter returned invalid tool arguments: {raw_arguments}") from exc
    if not isinstance(decoded, dict):
        raise OpenEnvError("OpenRouter tool arguments must decode to an object.")
    return decoded


def _apply_document_updates(
    arguments: dict[str, Any],
    *,
    allowed_files: list[str],
    write_document: Callable[[str, str], None],
) -> dict[str, Any]:
    """Validate requested document writes and persist them through the caller callback."""
    updates = arguments.get("updates")
    if not isinstance(updates, list):
        raise OpenEnvError("write_bot_documents requires an updates list.")
    written_files: list[str] = []
    allowed = set(allowed_files)
    for update in updates:
        if not isinstance(update, dict):
            raise OpenEnvError("Each write_bot_documents update must be an object.")
        file_name = update.get("file")
        content = update.get("content")
        if not isinstance(file_name, str) or file_name not in allowed:
            raise OpenEnvError(f"OpenRouter tried to write a disallowed file: {file_name!r}")
        if not isinstance(content, str) or not content.strip():
            raise OpenEnvError(f"OpenRouter tried to write empty content to {file_name}.")
        write_document(file_name, content)
        written_files.append(file_name)
    return {"written_files": written_files}
