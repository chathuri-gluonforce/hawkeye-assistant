from hawkeye_assistant.evaluation import evaluate
from hawkeye_assistant.api import app as api_app


def test_evaluation_rewards_correct_lessons_and_penalizes_mistakes(monkeypatch):
    updates = []
    predictions = iter(
        [
            ("match_invoice", ["helpful"]),
            ("other", ["unhelpful"]),
        ]
    )
    monkeypatch.setattr(evaluate, "classify", lambda *args, **kwargs: next(predictions))
    monkeypatch.setattr(
        evaluate.memory,
        "update",
        lambda memory_id, reward: updates.append((memory_id, reward)),
    )

    score, mistakes = evaluate.evaluate(
        [
            {"text": "first", "intent": "match_invoice"},
            {"text": "second", "intent": "match_invoice"},
        ],
        "prompt",
        learn=True,
    )

    assert score == 0.5
    assert len(mistakes) == 1
    assert updates == [("helpful", 1), ("unhelpful", -3)]


def test_feedback_penalizes_used_lesson_and_indexes_message(monkeypatch):
    updates = []
    additions = []
    monkeypatch.setattr(api_app, "get_prompt", lambda: "prompt")
    monkeypatch.setattr(api_app, "classify", lambda *args, **kwargs: ("other", ["lesson"]))
    monkeypatch.setattr(
        api_app.memory,
        "update",
        lambda memory_id, reward: updates.append((memory_id, reward)),
    )
    monkeypatch.setattr(api_app, "make_lesson", lambda _: "Use the correct intent.")
    monkeypatch.setattr(
        api_app.memory,
        "add",
        lambda lesson, example="": additions.append((lesson, example)),
    )

    result = api_app.feedback(
        api_app.Feedback(
            text="The invoice amount is wrong",
            predicted="other",
            correct="amount_mismatch",
        )
    )

    assert result["learned"] == "corrected"
    assert updates == [("lesson", -3)]
    assert additions == [
        ("Use the correct intent.", "The invoice amount is wrong")
    ]
