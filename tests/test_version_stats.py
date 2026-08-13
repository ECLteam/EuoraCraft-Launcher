from __future__ import annotations

import json

from ECL.services.game.version_stats import VersionStatsStore


def test_version_stats_store_creates_defaults_and_accumulates_runs(tmp_path) -> None:
    game_path = tmp_path / ".minecraft"
    version_path = game_path / "versions" / "1.21.8"
    version_path.mkdir(parents=True)
    store = VersionStatsStore()

    assert store.read(game_path, "1.21.8") == {
        "launchCount": 0,
        "lastRunDurationSeconds": 0,
        "totalRunDurationSeconds": 0,
    }

    store.record_launch(game_path, "1.21.8")
    store.record_launch(game_path, "1.21.8")
    store.record_duration(game_path, "1.21.8", 65)
    store.record_duration(game_path, "1.21.8", 5)

    assert json.loads((version_path / "eclversion.json").read_text(encoding="utf-8")) == {
        "launchCount": 2,
        "lastRunDurationSeconds": 5,
        "totalRunDurationSeconds": 70,
    }


def test_version_stats_store_recovers_malformed_file_on_next_write(tmp_path) -> None:
    game_path = tmp_path / ".minecraft"
    version_path = game_path / "versions" / "broken"
    version_path.mkdir(parents=True)
    stats_file = version_path / "eclversion.json"
    stats_file.write_text("{invalid", encoding="utf-8")
    store = VersionStatsStore()

    assert store.read(game_path, "broken")["launchCount"] == 0

    store.record_launch(game_path, "broken")

    assert json.loads(stats_file.read_text(encoding="utf-8")) == {
        "launchCount": 1,
        "lastRunDurationSeconds": 0,
        "totalRunDurationSeconds": 0,
    }
