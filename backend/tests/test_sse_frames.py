"""Pure frame helpers: bytes in, bytes out. No database, no event loop, no Redis."""

import pytest

from game.services import events
from game.sse import RESYNC_FRAME, build_frame, parse_xread, resume_plan


def test_build_frame_wire_format():
    frame = build_frame(b"1762000000000-0", {b"t": b"board.graded", b"d": b'{"node":"L3_7"}'})

    assert frame.payload == (b'id: 1762000000000-0\nevent: board.graded\ndata: {"node":"L3_7"}\n\n')
    assert frame.id == "1762000000000-0"
    assert frame.event == "board.graded"
    assert frame.mentor_only is False


def test_build_frame_marks_mentor_only_events():
    frame = build_frame(b"1-0", {b"t": events.SUBMISSION_CREATED.encode(), b"d": b"{}"})

    assert frame.mentor_only is True


def test_build_frame_tolerates_missing_fields():
    frame = build_frame(b"1-0", {})

    assert frame.event == events.RESYNC
    assert frame.payload.endswith(b"data: {}\n\n")


def test_resync_frame_carries_no_id():
    assert RESYNC_FRAME.payload == b"event: resync\ndata: {}\n\n"


@pytest.mark.parametrize(
    ("response", "expected"),
    [
        ([], []),
        (None, []),
        ([[b"karsoogh:board", [(b"1-0", {b"t": b"a"})]]], [(b"1-0", {b"t": b"a"})]),
        (
            [[b"karsoogh:board", [(b"1-0", {b"t": b"a"}), (b"2-0", {b"t": b"b"})]]],
            [(b"1-0", {b"t": b"a"}), (b"2-0", {b"t": b"b"})],
        ),
    ],
)
def test_parse_xread(response, expected):
    assert parse_xread(response) == expected


@pytest.mark.parametrize(
    ("last_event_id", "oldest", "expected"),
    [
        (None, "5-0", "tail"),
        ("", "5-0", "tail"),
        ("not-an-id", "5-0", "tail"),
        ("5-0", None, "replay"),
        ("5-0", "5-0", "replay"),
        ("5-0", "6-0", "resync"),
        ("5-1", "5-2", "resync"),
        # Numeric compare, not lexicographic: "9" > "10" as strings.
        ("9-0", "10-0", "resync"),
        ("10-0", "9-0", "replay"),
    ],
)
def test_resume_plan(last_event_id, oldest, expected):
    assert resume_plan(last_event_id, oldest) == expected
