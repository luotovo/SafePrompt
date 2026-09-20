from __future__ import annotations

import socket
from contextlib import contextmanager
from pathlib import Path

from ..ner import EntityResult


UIE_SCHEMA_MAP = {"人名": "PERSON", "组织机构": "ORG", "组织": "ORG"}
TASKFLOW_LABEL_MAP = {"PER": "PERSON", "ORG": "ORG"}


@contextmanager
def deny_network():
    """Fail closed if a supposedly local model attempts any network connection while loading."""
    original_socket = socket.socket
    original_create_connection = socket.create_connection

    class OfflineSocket(original_socket):
        def connect(self, address):
            raise RuntimeError(f"network access blocked while loading local benchmark model: {address!r}")

    def blocked_create_connection(address, *args, **kwargs):
        raise RuntimeError(f"network access blocked while loading local benchmark model: {address!r}")

    socket.socket = OfflineSocket
    socket.create_connection = blocked_create_connection
    try:
        yield
    finally:
        socket.socket = original_socket
        socket.create_connection = original_create_connection


class UieNanoRecognizer:
    def __init__(self, predictor, model_name: str = "uie-nano"):
        self.predictor = predictor
        self.model_name = model_name

    @classmethod
    def from_local_path(cls, model_path: str | Path) -> "UieNanoRecognizer":
        from paddlenlp import Taskflow

        path = str(Path(model_path).resolve())
        with deny_network():
            predictor = Taskflow("information_extraction", schema=["人名", "组织机构"],
                                 model="uie-nano", task_path=path, is_static_model=True, device_id=-1)
        return cls(predictor)

    def recognize(self, text: str) -> list[EntityResult]:
        with deny_network():
            output = self.predictor(text)
        row = output[0] if isinstance(output, list) and output else output
        results = []
        for label, entities in row.items():
            category = UIE_SCHEMA_MAP.get(label)
            if not category:
                continue
            for entity in entities:
                results.append(EntityResult(category, int(entity["start"]), int(entity["end"]),
                                            str(entity["text"]), float(entity["probability"]), self.model_name))
        return results


class TaskflowNerRecognizer:
    """Unscored PER/ORG baseline; confidence intentionally remains None."""

    def __init__(self, predictor, model_name: str = "taskflow-ner-fast"):
        self.predictor = predictor
        self.model_name = model_name

    @classmethod
    def from_local_path(cls, model_path: str | Path) -> "TaskflowNerRecognizer":
        from paddlenlp import Taskflow

        path = str(Path(model_path).resolve())
        with deny_network():
            predictor = Taskflow("ner", mode="fast", task_path=path, is_static_model=True, device_id=-1)
        return cls(predictor)

    def recognize(self, text: str) -> list[EntityResult]:
        with deny_network():
            output = self.predictor(text)
        entities = output[0] if isinstance(output, list) and output and isinstance(output[0], list) else output
        results = []
        cursor = 0
        for entity in entities:
            if isinstance(entity, dict):
                value, label = str(entity.get("text", "")), str(entity.get("label", ""))
            elif isinstance(entity, (tuple, list)) and len(entity) >= 2:
                value, label = str(entity[0]), str(entity[1])
            else:
                continue
            if not value:
                continue
            start = text.find(value, cursor)
            if start < 0:
                start = text.find(value)
            if start < 0:
                continue
            end = start + len(value)
            cursor = end
            category = TASKFLOW_LABEL_MAP.get(label.upper())
            if not category:
                continue
            results.append(EntityResult(category, start, end, value, None, self.model_name))
        return results


def load_uie_local(model_path: str | Path) -> UieNanoRecognizer:
    return UieNanoRecognizer.from_local_path(model_path)


def load_taskflow_local(model_path: str | Path) -> TaskflowNerRecognizer:
    return TaskflowNerRecognizer.from_local_path(model_path)
