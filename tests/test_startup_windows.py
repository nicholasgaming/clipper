import os
import uuid
import winreg
from unittest.mock import patch

import pytest

from rocket_league_clips.app import APP_NAME, set_startup


@pytest.mark.skipif(os.name != "nt", reason="Windows registry only")
def test_startup_registration_uses_a_user_registry_entry():
    temporary_key = "Software\\RocketLeagueClipsTest-" + uuid.uuid4().hex
    create_key = winreg.CreateKey
    def isolated_create(root, unused):
        assert root == winreg.HKEY_CURRENT_USER
        return create_key(root, temporary_key)
    try:
        with patch.object(winreg, "CreateKey", side_effect=isolated_create):
            set_startup(True)
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, temporary_key) as key:
                command, value_type = winreg.QueryValueEx(key, APP_NAME)
                assert value_type == winreg.REG_SZ
                assert "pythonw.exe" in command and "run_app.py" in command and "--background" in command
            set_startup(False)
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, temporary_key) as key:
                with pytest.raises(FileNotFoundError):
                    winreg.QueryValueEx(key, APP_NAME)
    finally:
        try:
            winreg.DeleteKey(winreg.HKEY_CURRENT_USER, temporary_key)
        except FileNotFoundError:
            pass
