from benchmarks.ner_dataset import samples


def test_benchmark_gold_offsets_and_coverage():
    rows = samples()
    assert all(entity["text"] == row["text"][entity["start"]:entity["end"]]
               for row in rows for entity in row["entities"])
    assert {entity["category"] for row in rows for entity in row["entities"]} == {"PERSON", "ORG"}
    assert any(not row["entities"] for row in rows)
    assert any(len(row["text"]) >= 1000 for row in rows)
    counts = {category: sum(entity["category"] == category for row in rows for entity in row["entities"])
              for category in ("PERSON", "ORG")}
    assert 50 <= len(rows) <= 80
    assert counts["PERSON"] >= 30 and counts["ORG"] >= 30
    assert sum(not row["entities"] for row in rows) >= 15
