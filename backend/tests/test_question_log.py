from app.question_log import QuestionLog


# Confirms private logs persist and place missing-answer questions first.
def test_question_log_persists_and_prioritizes_unanswered(tmp_path):
    log = QuestionLog(tmp_path / "ask-katy.private.db")
    log.record("one", "Answered question?", "Yes.", "answered")
    log.record("one", "Unknown question?", "I am not sure.", "unanswered")

    entries = log.recent()

    assert entries[0]["question"] == "Unknown question?"
    assert entries[0]["outcome"] == "unanswered"
    assert entries[1]["outcome"] == "answered"
    assert entries[0]["timestamp"].endswith("+00:00")


# Confirms long recruiter history is split into stable newest-first pages.
def test_question_log_returns_counted_pages(tmp_path):
    log = QuestionLog(tmp_path / "ask-katy.private.db")
    for index in range(12):
        log._insert({
            "timestamp": f"2026-11-20T12:{index:02d}:00+00:00",
            "application_id": "one",
            "question": f"Question {index}",
            "answer": "Answer.",
            "outcome": "answered",
        })

    first = log.page(page=1, page_size=5)
    third = log.page(page=3, page_size=5)

    assert first["total"] == 12
    assert first["total_pages"] == 3
    assert [item["question"] for item in first["questions"]] == [
        "Question 11", "Question 10", "Question 9", "Question 8", "Question 7",
    ]
    assert [item["question"] for item in third["questions"]] == [
        "Question 1", "Question 0",
    ]


# Confirms clearing recruiter history reports its scope and leaves an empty log.
def test_question_log_can_be_cleared(tmp_path):
    log = QuestionLog(tmp_path / "ask-katy.private.db")
    log.record("one", "First?", "Answer.", "answered")
    log.record("one", "Second?", "Unknown.", "unanswered")

    assert log.clear() == 2
    assert log.page(page=1, page_size=10)["questions"] == []
