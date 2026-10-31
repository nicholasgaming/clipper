from unittest.mock import patch

import pytest

from rocket_league_clips.windows_displays import output_index


def test_primary_and_selected_monitor_indices():
    found = [{"name": "screen-a", "index": 0, "primary": False}, {"name": "screen-b", "index": 1, "primary": True}]
    with patch("rocket_league_clips.windows_displays.displays", return_value=found):
        assert output_index(None) == 1
        assert output_index("screen-a") == 0
        with pytest.raises(RuntimeError, match="selected display"):
            output_index("missing")
