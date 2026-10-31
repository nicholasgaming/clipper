import os
import pytest

from rocket_league_clips.hotkey import GlobalHotkey, HotkeyError, MOD_ALT, MOD_CONTROL, MOD_SHIFT


@pytest.mark.skipif(os.name != "nt", reason="Windows global hotkeys only")
def test_conflict_is_reported_and_registration_is_released():
    first = GlobalHotkey(lambda: None, key=0x7B, modifiers=MOD_CONTROL | MOD_ALT | MOD_SHIFT)
    second = GlobalHotkey(lambda: None, key=0x7B, modifiers=MOD_CONTROL | MOD_ALT | MOD_SHIFT)
    first.start()
    try:
        with pytest.raises(HotkeyError, match="could not be registered"):
            second.start()
    finally:
        first.stop()
        second.stop()
    replacement = GlobalHotkey(lambda: None, key=0x7B, modifiers=MOD_CONTROL | MOD_ALT | MOD_SHIFT)
    replacement.start()
    replacement.stop()
