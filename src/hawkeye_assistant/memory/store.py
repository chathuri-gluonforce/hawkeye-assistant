from functools import lru_cache
import uuid

import chromadb
from chromadb.utils.embedding_functions import SentenceTransformerEmbeddingFunction

from hawkeye_assistant.config import MEMORY_DB_DIR


EMBED_MODEL = "BAAI/bge-small-en-v1.5"
MAX_DIST = 0.45
DUPLICATE_MAX_DIST = 0.08


@lru_cache(maxsize=1)
def _get_collection():
    db = chromadb.PersistentClient(path=str(MEMORY_DB_DIR))
    embedding_function = SentenceTransformerEmbeddingFunction(model_name=EMBED_MODEL)
    # Changing the embedding model or distance requires rebuilding storage/memory_db.
    return db.get_or_create_collection(
        "lessons",
        embedding_function=embedding_function,
        metadata={"hnsw:space": "cosine"},
    )


def add(text, example=""):  # Create
    key = example or text
    collection = _get_collection()
    if collection.count() > 0:
        r = collection.query(query_texts=[key], n_results=1)
        if r["distances"][0][0] < DUPLICATE_MAX_DIST:
            return
    collection.add(
        ids=[str(uuid.uuid4())],
        documents=[key],
        metadatas=[{"rule": text, "score": 0}],
    )


def search_with_distance(query, k=3, max_dist=MAX_DIST):
    collection = _get_collection()
    count = collection.count()
    if count == 0 or k <= 0:
        return []
    normalized_query = " ".join(query.strip().split())
    n_results = min(max(k * 3, 10), count)
    r = collection.query(query_texts=[normalized_query], n_results=n_results)
    candidates = []
    for item_id, metadata, document, distance in zip(
        r["ids"][0], r["metadatas"][0], r["documents"][0], r["distances"][0]
    ):
        if distance > max_dist:
            continue
        rule = metadata.get("rule", document)
        score = metadata.get("score", 0)
        rank_value = distance - 0.1 * (score / 100)
        candidates.append((rank_value, item_id, rule, distance))
    candidates.sort(key=lambda candidate: candidate[0])
    return [(item_id, rule, distance) for _, item_id, rule, distance in candidates[:k]]


def search(query, k=3, max_dist=MAX_DIST):  # Read
    return [
        (item_id, rule)
        for item_id, rule, _ in search_with_distance(query, k, max_dist)
    ]


def update(mem_id, reward):  # Update
    collection = _get_collection()
    metadata = collection.get(ids=[mem_id])["metadatas"][0]
    score = max(0, min(100, metadata.get("score", 0) + reward))
    collection.update(
        ids=[mem_id],
        metadatas=[{**metadata, "score": score}],
    )


def cleanup(min_score=-1):  # Delete
    collection = _get_collection()
    items = collection.get()
    bad = [
        item_id
        for item_id, metadata in zip(items["ids"], items["metadatas"])
        if metadata.get("score", 0) <= min_score
    ]
    if bad:
        collection.delete(ids=bad)


def all_lessons():
    collection = _get_collection()
    items = collection.get()
    lessons = [
        (metadata.get("rule", document), metadata.get("score", 0))
        for document, metadata in zip(items["documents"], items["metadatas"])
    ]
    for lesson, score in lessons:
        print(f"score={score}  {lesson}")
    return lessons


def lessons_by_ids(ids):
    """Read lesson text and score for ids already returned by search. Does not write."""
    if not ids:
        return []
    found = _get_collection().get(ids=list(ids))
    by_id = {
        item_id: {
            "lesson": meta.get("rule", doc),
            "score": meta.get("score", 0),
        }
        for item_id, doc, meta in zip(found["ids"], found["documents"], found["metadatas"])
    }
    return [{"lesson": by_id[item_id]["lesson"], "score": by_id[item_id]["score"]}
            for item_id in ids if item_id in by_id]