from types import SimpleNamespace

from rocket_league_clips.capture import ReplayCaptureBase


def test_segment_journal_reads_only_new_complete_rows(tmp_path):
    path = tmp_path / "segments.csv"
    path.write_text('"segment00000000.mkv",0,1\n', encoding="utf-8")
    capture = ReplayCaptureBase(ffmpeg="ffmpeg")
    capture._csv = path
    assert capture._read_segment_rows() == [["segment00000000.mkv", "0", "1"]]
    assert capture._read_segment_rows() == []
    with path.open("a", encoding="utf-8") as writer:
        writer.write('"segment00000001.mkv",1,')
        writer.flush()
        assert capture._read_segment_rows() == []
        writer.write('2\n')
        writer.flush()
        assert capture._read_segment_rows() == [["segment00000001.mkv", "1", "2"]]


def test_capture_warning_does_not_mark_a_running_recorder_as_failed():
    capture = ReplayCaptureBase(ffmpeg="ffmpeg")
    capture._process = SimpleNamespace(poll=lambda: None)
    capture._errors.append("A temporary playlist warning")
    assert capture.failure is None
    capture._stop.set()
    assert capture.failure == "A temporary playlist warning"
