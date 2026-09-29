from __future__ import annotations

from collections.abc import Callable
import os
from pathlib import Path

from ..ner import EntityResult


LABEL_MAP = {"name": "PERSON", "company": "ORG", "government": "ORG", "organization": "ORG"}


class UerRecognizer:
    """CLUENER adapter with token-aware overlapping chunks and global offsets."""

    def __init__(self, tokenizer, predict_chunk: Callable[[str], list[dict]], model_name: str = "uer-cluener",
                 max_tokens: int = 510, overlap_tokens: int = 64):
        if not 0 < overlap_tokens < max_tokens:
            raise ValueError("overlap_tokens must be between zero and max_tokens")
        self.tokenizer = tokenizer
        self.predict_chunk = predict_chunk
        self.model_name = model_name
        self.max_tokens = max_tokens
        self.overlap_tokens = overlap_tokens

    @classmethod
    def from_local_path(cls, model_path: str | Path) -> "UerRecognizer":
        """Load only local files; this method never downloads missing resources."""
        os.environ["HF_HUB_OFFLINE"] = "1"
        os.environ["TRANSFORMERS_OFFLINE"] = "1"
        from transformers import AutoModelForTokenClassification, AutoTokenizer, pipeline

        path = str(Path(model_path).resolve())
        tokenizer = AutoTokenizer.from_pretrained(path, local_files_only=True, use_fast=True)
        model = AutoModelForTokenClassification.from_pretrained(path, local_files_only=True)
        classifier = pipeline("token-classification", model=model, tokenizer=tokenizer,
                              aggregation_strategy="average")
        return cls(tokenizer, classifier)

    def recognize(self, text: str) -> list[EntityResult]:
        found: dict[tuple[str, int, int, str], EntityResult] = {}
        chunks = self._chunks(text)
        for chunk_index, (chunk_start, chunk_end) in enumerate(chunks):
            chunk = text[chunk_start:chunk_end]
            for raw in self.predict_chunk(chunk):
                label = str(raw.get("entity_group", raw.get("entity", ""))).removeprefix("B-").removeprefix("I-").lower()
                category = LABEL_MAP.get(label)
                if not category:
                    continue
                local_start, local_end = int(raw["start"]), int(raw["end"])
                if (chunk_index > 0 and local_start == 0) or (chunk_index < len(chunks) - 1 and local_end == len(chunk)):
                    continue
                start, end = chunk_start + local_start, chunk_start + local_end
                value = text[start:end]
                result = EntityResult(category, start, end, value, float(raw["score"]), self.model_name)
                key = (category, start, end, value)
                if key not in found or (found[key].confidence or 0) < (result.confidence or 0):
                    found[key] = result
        return sorted(found.values(), key=lambda item: (item.start, item.end, item.category))

    def _chunks(self, text: str) -> list[tuple[int, int]]:
        encoded = self.tokenizer(text, add_special_tokens=False, return_offsets_mapping=True,
                                 truncation=False)
        offsets = encoded["offset_mapping"]
        if not offsets:
            return []
        chunks = []
        token_start = 0
        while token_start < len(offsets):
            token_end = min(token_start + self.max_tokens, len(offsets))
            chunks.append((offsets[token_start][0], offsets[token_end - 1][1]))
            if token_end == len(offsets):
                break
            token_start = token_end - self.overlap_tokens
        return chunks


def load_local(model_path: str | Path) -> UerRecognizer:
    return UerRecognizer.from_local_path(model_path)
