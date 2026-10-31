import os
import subprocess
import sys
import uuid

import pytest

from rocket_league_clips.single_instance import ActivationEvent, signal_existing

pytestmark = pytest.mark.skipif(os.name != "nt", reason="Windows named events")


def test_second_process_wakes_first_instance():
    name = "Local\\RocketLeagueClipsTest-" + uuid.uuid4().hex
    event = ActivationEvent(name)
    try:
        assert not event.requested()
        result = subprocess.run([sys.executable, "-c",
            "import sys; from rocket_league_clips.single_instance import signal_existing; sys.exit(0 if signal_existing(sys.argv[1], timeout=1) else 1)", name],
            capture_output=True, timeout=5)
        assert result.returncode == 0, result.stderr.decode(errors="replace")
        assert event.requested()
        assert not event.requested()
    finally:
        event.close()


def test_missing_instance_does_not_report_success():
    assert not signal_existing("Local\\RocketLeagueClipsMissing-" + uuid.uuid4().hex, timeout=0)
