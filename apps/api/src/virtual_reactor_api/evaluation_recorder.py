"""Run-scoped evaluation event recorder shared by orchestration boundaries."""

from __future__ import annotations

from contextvars import ContextVar, Token
from typing import Any, Mapping

from virtual_reactor_api.agent_models import ReactionGenerationRequest
from virtual_reactor_api.evaluation_store import EvaluationStore


class EvaluationRecorder:
    def __init__(self, store: EvaluationStore, run_id: str) -> None:
        self.store = store
        self.run_id = run_id

    @classmethod
    def start(
        cls,
        store: EvaluationStore,
        request: ReactionGenerationRequest,
        metadata: Mapping[str, Any],
    ) -> "EvaluationRecorder":
        request_payload = request.model_dump(mode="json")
        run_id = store.create_run(request_payload, metadata)
        recorder = cls(store, run_id)
        recorder.record("request_received", {"request": request_payload})
        return recorder

    def record(self, event_type: str, payload: Mapping[str, Any]) -> None:
        self.store.append_event(
            self.run_id,
            event_type,
            serialize_for_evaluation(payload),
        )

    def complete(self, result: Any) -> None:
        payload = serialize_for_evaluation(result)
        self.record("final_result", {"result": payload})
        self.store.complete_run(
            self.run_id,
            result.status,
            final_result=payload,
        )

    def fail(self, error: BaseException) -> None:
        message = str(error) or error.__class__.__name__
        self.record(
            "run_failed",
            {"errorType": error.__class__.__name__, "message": message},
        )
        self.store.complete_run(self.run_id, "failed", error=message)


_CURRENT_RECORDER: ContextVar[EvaluationRecorder | None] = ContextVar(
    "virtual_reactor_evaluation_recorder",
    default=None,
)


def set_current_recorder(
    recorder: EvaluationRecorder,
) -> Token[EvaluationRecorder | None]:
    return _CURRENT_RECORDER.set(recorder)


def reset_current_recorder(token: Token[EvaluationRecorder | None]) -> None:
    _CURRENT_RECORDER.reset(token)


def current_evaluation_recorder() -> EvaluationRecorder | None:
    return _CURRENT_RECORDER.get()


def record_evaluation_event(event_type: str, payload: Mapping[str, Any]) -> None:
    recorder = current_evaluation_recorder()
    if recorder is not None:
        recorder.record(event_type, payload)


def serialize_for_evaluation(value: Any) -> Any:
    if hasattr(value, "model_dump"):
        return serialize_for_evaluation(value.model_dump(mode="json"))
    if isinstance(value, Mapping):
        return {
            str(key): serialize_for_evaluation(child)
            for key, child in value.items()
        }
    if isinstance(value, (list, tuple)):
        return [serialize_for_evaluation(child) for child in value]
    if isinstance(value, bytes):
        return value.decode("utf-8", errors="replace")
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    return repr(value)

