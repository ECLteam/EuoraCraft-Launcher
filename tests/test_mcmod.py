from __future__ import annotations

import json
from pathlib import Path

from ECL.services.game import GameService
from ECL.services.game.mcmod import McmodTranslator

_SAMPLE_MODS = [
    {"id": 2785, "name": "钠", "english": "Sodium", "abbr": "", "cf": "sodium", "mr": "sodium", "modIds": ["sodium"]},
    {"id": 2021, "name": "机械动力", "english": "Create", "abbr": "", "cf": "create", "mr": "create", "modIds": ["create"]},
    {"id": 459, "name": "JEI物品管理器", "english": "Just Enough Items", "abbr": "JEI", "cf": "jei", "mr": "jei", "modIds": ["jei"]},
    {"id": 9999, "name": "工业时代2", "english": "Industrial Craft 2", "abbr": "IC2", "cf": "industrial-craft", "mr": "industrial-craft", "modIds": ["ic2"]},
]


def _write_sample(tmp_path: Path) -> Path:
    path = tmp_path / "mcmod_data.json"
    path.write_text(json.dumps({"version": 1, "mods": _SAMPLE_MODS}, ensure_ascii=False), encoding="utf-8")
    return path


def test_lookup_by_slug(tmp_path: Path) -> None:
    translator = McmodTranslator(_write_sample(tmp_path))

    assert translator.lookup_by_modrinth_slug("sodium")["name"] == "钠"
    assert translator.lookup_by_curseforge_slug("jei")["id"] == 459
    assert translator.lookup_by_modrinth_slug("SODIUM")["id"] == 2785
    assert translator.lookup_by_modrinth_slug("missing") is None


def test_search_chinese_prefers_exact_and_prefix(tmp_path: Path) -> None:
    translator = McmodTranslator(_write_sample(tmp_path))

    assert [m["id"] for m in translator.search_chinese("钠")] == [2785]
    assert [m["id"] for m in translator.search_chinese("工业")] == [9999]
    assert translator.search_chinese("") == []


def test_to_english_query_uses_exact_match(tmp_path: Path) -> None:
    translator = McmodTranslator(_write_sample(tmp_path))

    assert translator.to_english_query("钠") == "Sodium"
    assert translator.to_english_query("机械动力") == "Create"
    assert translator.to_english_query("工业") == "Industrial Craft"
    assert translator.to_english_query("不存在的模组") == ""


def test_mcmod_url_and_wiki_info(tmp_path: Path) -> None:
    translator = McmodTranslator(_write_sample(tmp_path))

    assert translator.mcmod_url(2785) == "https://www.mcmod.cn/class/2785.html"
    wiki = translator.to_wiki_info(translator.lookup_by_modrinth_slug("sodium"))
    assert wiki == {
        "id": "2785",
        "title": "钠",
        "englishName": "Sodium",
        "summary": "",
        "url": "https://www.mcmod.cn/class/2785.html",
    }


def test_missing_data_file_returns_empty(tmp_path: Path) -> None:
    translator = McmodTranslator(tmp_path / "nonexistent.json")

    assert translator.lookup_by_modrinth_slug("sodium") is None
    assert translator.search_chinese("钠") == []
    assert translator.to_english_query("钠") == ""


def test_corrupted_data_file_returns_empty(tmp_path: Path) -> None:
    path = tmp_path / "mcmod_data.json"
    path.write_text("{broken json", encoding="utf-8")
    translator = McmodTranslator(path)

    assert translator.lookup_by_modrinth_slug("sodium") is None
    assert translator.to_english_query("钠") == ""


class _FakeAccounts:
    def current_account(self):
        return {"id": "offline", "type": "offline"}


def test_map_search_hits_fills_wiki_and_chinese_title(tmp_path: Path) -> None:
    resources = tmp_path / "resources"
    resources.mkdir()
    (resources / "mcmod_data.json").write_text(
        json.dumps({"version": 1, "mods": _SAMPLE_MODS}, ensure_ascii=False), encoding="utf-8"
    )
    service = GameService(_FakeAccounts(), resource_path=tmp_path)

    hits = [{
        "project_id": "AANobbMI",
        "slug": "sodium",
        "title": "Sodium",
        "description": "desc",
        "author": "jellysquid3",
        "downloads": 1,
        "follows": 0,
        "date_modified": "2026-01-01T00:00:00Z",
        "categories": ["fabric"],
        "versions": ["1.20.1"],
        "icon_url": "https://example.com/icon.png",
    }]
    items = service.map_search_hits("modrinth", hits, "mod")

    assert items[0]["displayTitle"] == "钠"
    assert items[0]["title"] == "Sodium"
    assert items[0]["wiki"]["id"] == "2785"
    assert items[0]["wiki"]["url"] == "https://www.mcmod.cn/class/2785.html"


def test_map_search_hits_skips_wiki_for_unknown_slug(tmp_path: Path) -> None:
    service = GameService(_FakeAccounts(), resource_path=tmp_path)

    hits = [{
        "project_id": "X",
        "slug": "unknown-mod",
        "title": "Unknown Mod",
        "description": "desc",
        "author": "a",
        "downloads": 0,
        "follows": 0,
        "categories": [],
        "versions": [],
    }]
    items = service.map_search_hits("modrinth", hits, "mod")

    assert items[0]["displayTitle"] == "Unknown Mod"
    assert items[0]["wiki"] is None


def test_map_search_hits_maps_curseforge_format(tmp_path: Path) -> None:
    resources = tmp_path / "resources"
    resources.mkdir()
    (resources / "mcmod_data.json").write_text(
        json.dumps({"version": 1, "mods": _SAMPLE_MODS}, ensure_ascii=False), encoding="utf-8"
    )
    service = GameService(_FakeAccounts(), resource_path=tmp_path)

    hits = [{
        "id": 394468,
        "name": "Sodium",
        "slug": "sodium",
        "summary": "cf desc",
        "downloadCount": 42,
        "dateModified": "2026-01-01T00:00:00Z",
        "authors": [{"name": "jellysquid3"}],
        "logo": {"url": "https://example.com/logo.png"},
    }]
    items = service.map_search_hits("curseforge", hits, "mod")

    assert items[0]["title"] == "Sodium"
    assert items[0]["displayTitle"] == "钠"
    assert items[0]["description"] == "cf desc"
    assert items[0]["author"] == "jellysquid3"
    assert items[0]["downloads"] == 42
    assert items[0]["iconUrl"] == "https://example.com/logo.png"
    assert items[0]["projectUrl"] == "https://www.curseforge.com/minecraft/mc-mods/sodium"
    assert items[0]["wiki"]["id"] == "2785"


def test_search_online_resources_mod_facet_excludes_modpack(tmp_path: Path) -> None:
    from unittest.mock import patch

    service = GameService(_FakeAccounts(), resource_path=tmp_path)
    captured: dict[str, object] = {}

    def fake_get(url, params=None, headers=None, timeout=None):
        captured["url"] = url
        captured["params"] = params
        response = type("R", (), {})()
        response.raise_for_status = lambda: None
        response.json = lambda: {"hits": [], "total_hits": 0}
        return response

    with patch("httpx.get", side_effect=fake_get):
        service.search_online_resources("sodium", "1.20.1", "fabric", resource_type="mod")

    import json as json_module

    facets = json_module.loads(captured["params"]["facets"])
    assert ["project_type:mod"] in facets


def test_search_online_resources_omits_empty_facets(tmp_path: Path) -> None:
    from unittest.mock import patch

    service = GameService(_FakeAccounts(), resource_path=tmp_path)
    captured: dict[str, object] = {}

    def fake_get(url, params=None, headers=None, timeout=None):
        captured["url"] = url
        captured["params"] = params
        response = type("R", (), {})()
        response.raise_for_status = lambda: None
        response.json = lambda: {"hits": [], "total_hits": 0}
        return response

    with patch("httpx.get", side_effect=fake_get):
        service.search_online_resources("", "", "", resource_type="mod")

    import json as json_module

    facets = json_module.loads(captured["params"]["facets"])
    assert facets == [["project_type:mod"]]
