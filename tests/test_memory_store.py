import pytest

from hawkeye_assistant.memory import store


class FakeCollection:
    def __init__(self):
        self.added = None
        self.updated = None
        self.score = 99
        self.query_result = {
            "ids": [["low-score", "high-score", "too-far"]],
            "metadatas": [
                [
                    {"rule": "low score rule", "score": 0},
                    {"rule": "high score rule", "score": 100},
                    {"rule": "distant rule", "score": 100},
                ]
            ],
            "documents": [["example 1", "example 2", "example 3"]],
            "distances": [[0.25, 0.30, 0.46]],
        }

    def count(self):
        return 3

    def query(self, **kwargs):
        return self.query_result

    def add(self, **kwargs):
        self.added = kwargs

    def get(self, ids=None):
        return {"metadatas": [{"rule": "kept rule", "score": self.score}]}

    def update(self, **kwargs):
        self.updated = kwargs


@pytest.mark.parametrize(
    ("starting_score", "reward", "expected_score"),
    [(99, 5, 100), (2, -3, 0)],
)
def test_score_is_clamped_and_rule_metadata_is_preserved(
    monkeypatch, starting_score, reward, expected_score
):
    collection = FakeCollection()
    collection.score = starting_score
    monkeypatch.setattr(store, "_get_collection", lambda: collection)

    store.update("lesson", reward)

    assert collection.updated == {
        "ids": ["lesson"],
        "metadatas": [{"rule": "kept rule", "score": expected_score}],
    }


def test_search_filters_by_distance_and_reranks_by_score(monkeypatch):
    collection = FakeCollection()
    monkeypatch.setattr(store, "_get_collection", lambda: collection)

    results = store.search_with_distance("  normalized   example ")

    assert results == [
        ("high-score", "high score rule", 0.30),
        ("low-score", "low score rule", 0.25),
    ]


def test_add_indexes_example_and_keeps_rule_in_metadata(monkeypatch):
    collection = FakeCollection()
    collection.count = lambda: 0
    monkeypatch.setattr(store, "_get_collection", lambda: collection)

    store.add("generated rule", example="original message")

    assert collection.added["documents"] == ["original message"]
    assert collection.added["metadatas"] == [
        {"rule": "generated rule", "score": 0}
    ]


def test_collection_uses_bge_embeddings_and_cosine_distance(monkeypatch):
    collection = object()
    collection_args = {}
    embedding_args = {}

    class FakeDatabase:
        def get_or_create_collection(self, name, **kwargs):
            collection_args["name"] = name
            collection_args.update(kwargs)
            return collection

    monkeypatch.setattr(store.chromadb, "PersistentClient", lambda **kwargs: FakeDatabase())
    monkeypatch.setattr(
        store,
        "SentenceTransformerEmbeddingFunction",
        lambda **kwargs: embedding_args.update(kwargs),
    )
    store._get_collection.cache_clear()

    try:
        assert store._get_collection() is collection
    finally:
        store._get_collection.cache_clear()

    assert embedding_args == {"model_name": "BAAI/bge-small-en-v1.5"}
    assert collection_args["name"] == "lessons"
    assert collection_args["metadata"] == {"hnsw:space": "cosine"}
