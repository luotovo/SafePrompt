from safeprompt.adapters.uer import UerRecognizer


class CharacterTokenizer:
    def __call__(self, text, **kwargs):
        return {"offset_mapping": [(index, index + 1) for index in range(len(text))]}


def test_entity_after_512_tokens_is_not_truncated():
    text = "甲" * 520 + "韩静" + "乙" * 10

    def predict(chunk):
        start = chunk.find("韩静")
        return [] if start < 0 else [{"entity_group": "name", "start": start, "end": start + 2, "score": 0.91}]

    results = UerRecognizer(CharacterTokenizer(), predict).recognize(text)
    assert [(item.category, item.start, item.end, item.text) for item in results] == [
        ("PERSON", 520, 522, "韩静")
    ]


def test_overlapping_chunks_deduplicate_same_entity():
    text = "甲" * 480 + "某某公司" + "乙" * 100

    def predict(chunk):
        start = chunk.find("某某公司")
        return [] if start < 0 else [{"entity_group": "company", "start": start, "end": start + 4, "score": 0.88}]

    results = UerRecognizer(CharacterTokenizer(), predict).recognize(text)
    assert len(results) == 1 and results[0].category == "ORG"


def test_truncated_boundary_prediction_is_discarded_in_favor_of_complete_neighbor():
    text = "甲" * 508 + "某某公司" + "乙" * 80

    def predict(chunk):
        if chunk.endswith("某某"):
            return [{"entity_group": "company", "start": len(chunk) - 2, "end": len(chunk), "score": 0.6}]
        start = chunk.find("某某公司")
        return [] if start < 0 else [{"entity_group": "company", "start": start, "end": start + 4, "score": 0.9}]

    results = UerRecognizer(CharacterTokenizer(), predict).recognize(text)
    assert [(item.start, item.end, item.text) for item in results] == [(508, 512, "某某公司")]
