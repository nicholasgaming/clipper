from unittest.mock import patch

from rocket_league_clips.app import clip_folder


def test_new_installation_uses_clipper_folder(tmp_path):
    with patch("rocket_league_clips.app.Path.home", return_value=tmp_path):
        assert clip_folder() == tmp_path / "Videos" / "Clipper"


def test_existing_installation_keeps_its_old_folder(tmp_path):
    old_folder = tmp_path / "Videos" / "Rocket League Clips"
    old_folder.mkdir(parents=True)
    with patch("rocket_league_clips.app.Path.home", return_value=tmp_path):
        assert clip_folder() == old_folder
