from concurrent.futures import ThreadPoolExecutor
from threading import Event
import pytest

from rocket_league_clips.replay_buffer import ReplayBuffer, Segment


def add(buffer, tmp_path, number):
    path = tmp_path / f"{number}.ts"
    path.write_bytes(bytes([number]))
    buffer.add_closed(Segment(path, number * 2, number * 2 + 2))
    return path


def test_cleanup_retains_two_overlapping_saves(tmp_path):
    buffer = ReplayBuffer(4)
    files = [add(buffer, tmp_path, number) for number in range(4)]
    with buffer.snapshot(4) as first:
        with buffer.snapshot(6) as second:
            assert [s.path for s in first] == files[:2]
            assert [s.path for s in second] == files[1:3]
            buffer.cleanup(20)
            assert all(path.exists() for path in files[:3])
            assert not files[3].exists()
        buffer.cleanup(20)
        assert files[0].exists() and files[1].exists()
        assert not files[2].exists()
    buffer.cleanup(20)
    assert not any(path.exists() for path in files)


def test_snapshot_keeps_segment_until_worker_finishes(tmp_path):
    buffer = ReplayBuffer(2)
    file = add(buffer, tmp_path, 0)
    ready, release = Event(), Event()
    def save():
        with buffer.snapshot(2) as segments:
            ready.set()
            assert release.wait(5)
            assert segments[0].path.read_bytes() == b"\x00"
    with ThreadPoolExecutor() as pool:
        future = pool.submit(save)
        assert ready.wait(5)
        buffer.cleanup(10)
        assert file.exists()
        release.set()
        future.result()
    buffer.cleanup(10)
    assert not file.exists()


def test_small_timestamp_rounding_overlap_is_normalized(tmp_path):
    buffer = ReplayBuffer(10)
    first = tmp_path / "first.mkv"; first.write_bytes(b"a")
    second = tmp_path / "second.mkv"; second.write_bytes(b"b")
    buffer.add_closed(Segment(first, 0, 1.001))
    buffer.add_closed(Segment(second, 1.000, 2.000))
    with buffer.snapshot(2) as segments:
        assert segments[1].start == segments[0].end


def test_real_overlap_is_rejected(tmp_path):
    buffer = ReplayBuffer(10)
    first = tmp_path / "first.mkv"; first.write_bytes(b"a")
    second = tmp_path / "second.mkv"; second.write_bytes(b"b")
    buffer.add_closed(Segment(first, 0, 1))
    with pytest.raises(ValueError, match="non-overlapping"):
        buffer.add_closed(Segment(second, 0.9, 2))


def test_snapshot_reserves_segments_closed_after_it_begins(tmp_path):
    buffer = ReplayBuffer(4)
    first = add(buffer, tmp_path, 0)
    with buffer.snapshot(6):
        later = add(buffer, tmp_path, 1)
        buffer.cleanup(100)
        assert later.exists()
        assert not first.exists()
    buffer.cleanup(100)
    assert not later.exists()
