"""Local ONNX UIE Nano backend for the Hybrid Lite source profile.

The tokenizer and span decoder are behavior-compatible adaptations of
PaddleNLP 2.6.1's Apache-2.0 licensed ERNIE/UIE helpers.  C0b freezes their
behavior; keep changes synchronized with its golden preprocessing suite.
"""

from __future__ import annotations

import socket
import unicodedata
from contextlib import contextmanager
from pathlib import Path

import numpy as np

from ..ner import EntityResult


SPECIAL = {"pad": "[PAD]", "cls": "[CLS]", "sep": "[SEP]", "mask": "[MASK]", "unk": "[UNK]"}
SCHEMAS = {"PERSON": "人名", "ORG": "组织机构"}
MAX_SEQUENCE_LENGTH = 512
MAX_TEXT_CHUNK_LENGTH = 240
CHUNK_OVERLAP = 32
POSITION_PROBABILITY = 0.5


def _is_whitespace(char: str) -> bool:
    return char in " \t\n\r" or unicodedata.category(char) == "Zs"


def _is_control(char: str) -> bool:
    return char not in "\t\n\r" and unicodedata.category(char) in {"Cc", "Cf"}


def _is_punctuation(char: str) -> bool:
    cp = ord(char)
    return (33 <= cp <= 47 or 58 <= cp <= 64 or 91 <= cp <= 96
            or 123 <= cp <= 126 or unicodedata.category(char).startswith("P"))


def _is_symbol(char: str) -> bool:
    return unicodedata.category(char).startswith("S")


def _is_chinese(cp: int) -> bool:
    return (0x4E00 <= cp <= 0x9FFF or 0x3400 <= cp <= 0x4DBF
            or 0x20000 <= cp <= 0x2A6DF or 0x2A700 <= cp <= 0x2B73F
            or 0x2B740 <= cp <= 0x2B81F or 0x2B820 <= cp <= 0x2CEAF
            or 0xF900 <= cp <= 0xFAFF or 0x2F800 <= cp <= 0x2FA1F)


class LightweightErnieTokenizer:
    def __init__(self, vocab_path: Path, max_length: int = MAX_SEQUENCE_LENGTH):
        tokens = vocab_path.read_text(encoding="utf-8").splitlines()
        self.token_to_id = {token: index for index, token in enumerate(tokens)}
        self.max_length = max_length
        self.unk_id = self.token_to_id[SPECIAL["unk"]]

    def _basic(self, text: str) -> list[str]:
        cleaned = []
        for char in text:
            if ord(char) in {0, 0xFFFD} or _is_control(char):
                continue
            cleaned.append(" " if _is_whitespace(char) else char)
        spaced = []
        for char in cleaned:
            if _is_chinese(ord(char)):
                spaced.extend((" ", char, " "))
            else:
                spaced.append(char)
        result = []
        for token in "".join(spaced).strip().split():
            normalized = unicodedata.normalize("NFD", token.lower())
            normalized = "".join(char for char in normalized if unicodedata.category(char) != "Mn")
            current = []
            for char in normalized:
                if _is_punctuation(char) or _is_symbol(char):
                    if current:
                        result.append("".join(current))
                        current = []
                    result.append(char)
                else:
                    current.append(char)
            if current:
                result.append("".join(current))
        return result

    def tokenize(self, text: str) -> list[str]:
        output = []
        for token in self._basic(text):
            if len(token) > 100:
                output.append(SPECIAL["unk"])
                continue
            pieces, start, bad = [], 0, False
            while start < len(token):
                end, match = len(token), None
                while start < end:
                    candidate = token[start:end]
                    if start:
                        candidate = "##" + candidate
                    if candidate in self.token_to_id:
                        match = candidate
                        break
                    end -= 1
                if match is None:
                    bad = True
                    break
                pieces.append(match)
                start = end
            output.extend([SPECIAL["unk"]] if bad else pieces)
        return output

    def offsets(self, text: str, tokens: list[str]) -> list[tuple[int, int]]:
        normalized, char_mapping = "", []
        for index, char in enumerate(text):
            char = unicodedata.normalize("NFD", char.lower())
            char = "".join(value for value in char if unicodedata.category(value) != "Mn")
            char = "".join(value for value in char
                           if not (ord(value) in {0, 0xFFFD} or _is_control(value)))
            normalized += char
            char_mapping.extend([index] * len(char))
        cursor, raw = 0, []
        special_tokens = set(SPECIAL.values())
        for index, original_token in enumerate(tokens):
            token = original_token[2:] if original_token.startswith("##") else original_token
            if token in special_tokens:
                token = token.lower()
            haystack = normalized[cursor:]
            if token in haystack:
                start = haystack.index(token) + cursor
            elif index < len(tokens) - 1 and tokens[index + 1] in special_tokens:
                start, token = cursor, " "
            else:
                start = -1
            end = start + len(token)
            raw.append([start, end])
            if start != -1:
                cursor = end
        result = []
        for index, (start, end) in enumerate(raw):
            if start == -1:
                start = 0 if index == 0 else raw[index - 1][1]
                end = len(char_mapping) if index == len(raw) - 1 else raw[index + 1][0]
            result.append((char_mapping[start], char_mapping[end - 1] + 1))
        return result

    def encode_pair(self, prompt: str, text: str) -> dict[str, list]:
        prompt_tokens = self.tokenize(prompt)
        text_tokens = self.tokenize(text)
        prompt_offsets = self.offsets(prompt, prompt_tokens)
        text_offsets = self.offsets(text, text_tokens)
        while len(prompt_tokens) + len(text_tokens) + 3 > self.max_length:
            if len(text_tokens) >= len(prompt_tokens):
                text_tokens.pop(); text_offsets.pop()
            else:
                prompt_tokens.pop(); prompt_offsets.pop()
        tokens = [SPECIAL["cls"], *prompt_tokens, SPECIAL["sep"], *text_tokens, SPECIAL["sep"]]
        input_ids = [self.token_to_id.get(token, self.unk_id) for token in tokens]
        prompt_length = len(prompt_tokens) + 2
        token_type_ids = [0] * prompt_length + [1] * (len(text_tokens) + 1)
        offset_mapping = [(0, 0), *prompt_offsets, (0, 0), *text_offsets, (0, 0)]
        sequence_length = len(input_ids)
        padding_length = self.max_length - sequence_length
        return {
            "input_ids": input_ids + [0] * padding_length,
            "token_type_ids": token_type_ids + [0] * padding_length,
            "position_ids": list(range(sequence_length)) + [0] * padding_length,
            "attention_mask": [1] * sequence_length + [0] * padding_length,
            "offset_mapping": [list(value) for value in offset_mapping] + [[0, 0]] * padding_length,
        }


def split_text(text: str, prompt: str, max_length: int = MAX_SEQUENCE_LENGTH,
               overlap: int = CHUNK_OVERLAP) -> list[dict]:
    max_text_length = min(max_length - len(prompt) - 3, MAX_TEXT_CHUNK_LENGTH)
    overlap = min(overlap, max_text_length - 1)
    step = max_text_length - overlap
    chunks = []
    for start in range(0, len(text), step):
        value = text[start:start + max_text_length]
        chunks.append({"text": value, "start": start, "end": start + len(value)})
        if start + len(value) >= len(text):
            break
    return chunks or [{"text": "", "start": 0, "end": 0}]


def decode_probabilities(text: str, chunk_start: int, offsets: list[list[int]],
                         start_prob: np.ndarray, end_prob: np.ndarray,
                         threshold: float = POSITION_PROBABILITY) -> list[dict]:
    starts = [(index, float(value)) for index, value in enumerate(start_prob) if value > threshold]
    ends = [(index, float(value)) for index, value in enumerate(end_prob) if value > threshold]
    start_pointer = end_pointer = 0
    pairs = {}
    while start_pointer < len(starts) and end_pointer < len(ends):
        start, end = starts[start_pointer], ends[end_pointer]
        if start[0] == end[0]:
            pairs[end] = start; start_pointer += 1; end_pointer += 1
        elif start[0] < end[0]:
            pairs[end] = start; start_pointer += 1
        else:
            end_pointer += 1
    prompt_end = offsets[1:].index([0, 0])
    bias = offsets[prompt_end][1] + 1
    adjusted = [list(value) for value in offsets]
    for index in range(1, prompt_end + 1):
        adjusted[index][0] -= bias
        adjusted[index][1] -= bias
    results = []
    for end, start in set((end, start) for end, start in pairs.items()):
        char_start, char_end = adjusted[start[0]][0], adjusted[end[0]][1]
        if char_start < 0 and char_end >= 0 or char_end < 0:
            continue
        results.append({"start": char_start + chunk_start, "end": char_end + chunk_start,
                        "text": text[char_start:char_end], "score": start[1] * end[1]})
    return results


@contextmanager
def deny_network():
    original_socket = socket.socket
    original_create_connection = socket.create_connection

    class OfflineSocket(original_socket):
        def connect(self, address):
            raise RuntimeError(f"network access blocked while loading local ONNX model: {address!r}")

    def blocked_create_connection(address, *args, **kwargs):
        raise RuntimeError(f"network access blocked while loading local ONNX model: {address!r}")

    socket.socket = OfflineSocket
    socket.create_connection = blocked_create_connection
    try:
        yield
    finally:
        socket.socket = original_socket
        socket.create_connection = original_create_connection


class OnnxUieNanoRecognizer:
    model_name = "uie-nano-onnx"

    def __init__(self, session, tokenizer: LightweightErnieTokenizer):
        self.session = session
        self.tokenizer = tokenizer
        self.input_names = {item.name for item in session.get_inputs()}

    @classmethod
    def from_local_path(cls, model_dir: str | Path) -> "OnnxUieNanoRecognizer":
        directory = Path(model_dir).resolve()
        required = [directory / name for name in
                    ("model.onnx", "vocab.txt", "tokenizer_config.json", "config.json")]
        missing = [path.name for path in required if not path.is_file()]
        if missing:
            raise FileNotFoundError(f"incomplete local ONNX UIE model: {directory}; missing {', '.join(missing)}")
        try:
            import onnxruntime as ort
        except ImportError as error:
            raise RuntimeError("onnxruntime is required for the local ONNX UIE backend") from error
        with deny_network():
            session = ort.InferenceSession(str(directory / "model.onnx"), providers=["CPUExecutionProvider"])
        return cls(session, LightweightErnieTokenizer(directory / "vocab.txt"))

    def recognize(self, text: str) -> list[EntityResult]:
        results = []
        with deny_network():
            for category, prompt in SCHEMAS.items():
                for chunk in split_text(text, prompt):
                    encoded = self.tokenizer.encode_pair(prompt, chunk["text"])
                    inputs = {name: np.asarray([encoded[name]], dtype=np.int64)
                              for name in ("input_ids", "token_type_ids", "position_ids", "attention_mask")
                              if name in self.input_names}
                    start_prob, end_prob = self.session.run(None, inputs)
                    decoded = decode_probabilities(chunk["text"], chunk["start"], encoded["offset_mapping"],
                                                   start_prob[0], end_prob[0])
                    results.extend(EntityResult(category, item["start"], item["end"], item["text"],
                                                item["score"], self.model_name) for item in decoded)
        unique = {}
        for result in results:
            key = (result.category, result.start, result.end, result.text)
            if key not in unique or (result.confidence or 0) > (unique[key].confidence or 0):
                unique[key] = result
        return list(unique.values())


def load_onnx_uie_local(model_dir: str | Path) -> OnnxUieNanoRecognizer:
    return OnnxUieNanoRecognizer.from_local_path(model_dir)
