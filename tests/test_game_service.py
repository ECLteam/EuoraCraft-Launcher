from __future__ import annotations

import asyncio
import json
import shlex
import time
from concurrent.futures import ThreadPoolExecutor
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from ECL.events import EventBus
from ECL.game import LaunchConfig, build_minecraft_cmd
from ECL.services.game import GameService, GameServiceError


class FakeAccounts:
    def current_account(self):
        return {"id": "offline", "type": "offline"}

    def get_launch_credentials(self):
        return {
            "player_name": "Steve",
            "uuid": "0123456789abcdef0123456789abcdef",
            "user_type": "legacy",
            "access_token": "None",
        }


class EmptySearchMinecraft:
    def __init__(self, _path):
        pass

    def search_minecraft(self):
        return {}


class FakeProcess:
    def __init__(self):
        self.running = True
        self.pid = 24680

    def poll(self):
        return None if self.running else 0


class FakeInstances:
    def __init__(self):
        self.items = []
        self.created = None
        self.exit_requests = []
        self.shutdown_calls = []
        self._create_count = 0

    def create_instance(self, **options):
        self._create_count += 1
        instance_id = "minecraft-instance" if self._create_count == 1 else f"minecraft-instance-{self._create_count}"
        self.created = options
        self.items.append(
            {
                "ID": instance_id,
                "Name": options["instance_name"],
                "Type": options["instance_type"],
                "Instance": FakeProcess(),
                "ExitCallback": options["exit_callback"],
            }
        )
        return instance_id

    def exit_instance(self, instance_id, exit_code=0):
        for item in list(self.items):
            if item["ID"] != instance_id:
                continue
            item["Instance"].running = False
            self.items.remove(item)
            item["ExitCallback"](exit_code, item["Name"])
            return

    def get_instances_info(self):
        return list(self.items)

    def stop_instance(self, instance_id, **_options):
        for item in self.items:
            if item["ID"] == instance_id:
                item["Instance"].running = False
        return True

    def request_instance_exit(self, instance_id, **options):
        self.exit_requests.append((instance_id, options))
        return self.stop_instance(instance_id, **options)

    def shutdown_all(self, **options):
        self.shutdown_calls.append(options)


class FakeDownloader:
    def __init__(self, download_list, progress_callback=None, **_options):
        self.download_list = download_list
        self.progress_callback = progress_callback
        self.failed_entries = set()
        self.client = None
        self.concurrency = 0
        self.semaphore = None

    async def run(self):
        if self.progress_callback:
            self.progress_callback(len(self.download_list), len(self.download_list))

    def stop(self):
        return None


def _reset_event_bus() -> None:
    EventBus._instance = None
    EventBus._initialized = False


def _build_service(**options) -> GameService:
    return GameService(
        FakeAccounts(),
        search_factory=options.pop("search_factory", EmptySearchMinecraft),
        instances_manager=options.pop("instances_manager", FakeInstances()),
        downloader_factory=options.pop("downloader_factory", FakeDownloader),
        **options,
    )


def _launch_lifecycle_fixture(tmp_path, monkeypatch, clock):
    game_path = tmp_path / ".minecraft"
    version_path = game_path / "versions" / "1.21.8"
    version_path.mkdir(parents=True)
    (version_path / "1.21.8.json").write_text("{}", encoding="utf-8")
    java_path = tmp_path / "java.exe"
    java_path.write_bytes(b"")
    instances = FakeInstances()
    service = _build_service(
        instances_manager=instances,
        command_builder=lambda _config: '"java.exe" game.Main',
    )
    monkeypatch.setattr("ECL.services.game.launch.monotonic", lambda: clock[0])
    monkeypatch.setattr(
        service,
        "_context",
        lambda *_args: SimpleNamespace(files_checker=SimpleNamespace(check_files=lambda *_args: [])),
    )
    result = asyncio.run(
        service.launch_instance(
            {"version_id": "1.21.8"},
            game_path=game_path,
            java_path=java_path,
        )
    )
    instances.created["log_callback"]("[Render thread/INFO]: Sound engine started", result["instanceId"])
    return service, instances, game_path, java_path, result


def test_scan_versions_is_owned_by_game_service(tmp_path) -> None:
    game_path = tmp_path / ".minecraft"
    (game_path / "versions").mkdir(parents=True)
    requested_paths = []

    class FakeSearchMinecraft:
        def __init__(self, path):
            requested_paths.append(path)

        def search_minecraft(self):
            return {}

    service = _build_service(search_factory=FakeSearchMinecraft)

    assert service.scan_versions([str(game_path)]) == []
    assert service.scan_versions([str(game_path)]) == []
    assert requested_paths == [game_path]

    assert service.scan_versions([str(game_path)], force=True) == []
    assert requested_paths == [game_path, game_path]


def test_version_directory_change_invalidates_cache_and_emits_event(tmp_path) -> None:
    game_path = tmp_path / ".minecraft"
    versions_path = game_path / "versions"
    versions_path.mkdir(parents=True)
    scan_count = 0

    class FakeSearchMinecraft:
        def __init__(self, _path):
            pass

        def search_minecraft(self):
            nonlocal scan_count
            scan_count += 1
            return {}

    service = _build_service(
        search_factory=FakeSearchMinecraft,
        enable_version_watcher=True,
        version_watch_interval=60,
        version_watch_debounce=0,
        event_bus=(event_bus := EventBus()),
    )
    events = []
    event_bus.subscribe("game:versions_changed", events.append)
    try:
        service.scan_versions([str(game_path)])
        (versions_path / "1.21.1").mkdir()

        changed_paths = service._poll_version_changes(now=1)

        assert changed_paths == [str(game_path.resolve())]
        assert events == [{"gamePath": str(game_path.resolve())}]
        service.scan_versions([str(game_path)])
        assert scan_count == 2
    finally:
        service.close()


def test_java_scanner_result_is_exposed_and_used_for_required_version(tmp_path) -> None:
    java8 = SimpleNamespace(
        path=tmp_path / "java8.exe",
        version="1.8.0_451",
        vendor="Eclipse Adoptium",
        architecture="amd64",
        is_jdk=False,
    )
    java21 = SimpleNamespace(
        path=tmp_path / "java21.exe",
        version="21.0.7",
        vendor="Microsoft",
        architecture="aarch64",
        is_jdk=True,
    )
    scanner_options = {}

    class FakeJavaScanner:
        def __init__(self, **options):
            scanner_options.update(options)

        def scan(self):
            return [java8, java21]

    service = _build_service(java_scanner_factory=FakeJavaScanner, data_path=tmp_path)

    installations = service.scan_java([str(java8.path)])

    assert [item["major_version"] for item in installations] == [21, 8]
    assert installations[0]["arch"] == "arm64"
    assert installations[1]["sources"] == ["user"]
    assert scanner_options["cache_file"] == tmp_path / "java_cache.json"
    assert service._resolve_java_path(None, 8) == str(java8.path)


def test_automatic_java_selection_uses_nearest_compatible_higher_version(tmp_path) -> None:
    java21 = SimpleNamespace(
        path=tmp_path / "java21.exe",
        version="21.0.7",
        vendor="Microsoft",
        architecture="amd64",
        is_jdk=True,
    )
    java25 = SimpleNamespace(
        path=tmp_path / "java25.exe",
        version="25.0.1",
        vendor="Eclipse Adoptium",
        architecture="amd64",
        is_jdk=True,
    )

    class FakeJavaScanner:
        def __init__(self, **_options):
            pass

        def scan(self):
            return [java25, java21]

    service = _build_service(java_scanner_factory=FakeJavaScanner)

    assert service._resolve_java_path(None, 17) == str(java21.path)
    assert service._resolve_java_path(None, 21) == str(java21.path)


def test_install_version_builds_and_downloads_with_progress(tmp_path, monkeypatch) -> None:
    _reset_event_bus()
    events = []
    event_bus = EventBus()
    event_bus.subscribe("game:install_progress", events.append)
    built = []

    class FakeGames:
        def build_minecraft_download_list(self, version_id, save_name):
            built.append((version_id, save_name))
            return [("https://example.com/client.jar", str(tmp_path / "client.jar"))]

    service = _build_service(event_bus=event_bus)
    service.logger = Mock()
    monkeypatch.setattr(
        service,
        "_context",
        lambda *_args: SimpleNamespace(games=FakeGames()),
    )

    async def install():
        result = service.install_version(
            {
                "version_id": "1.21.8",
                "version_name": "My 1.21.8",
                "task_id": "install-task",
            },
            game_path=tmp_path,
        )
        await service._install_tasks[result["taskId"]]
        return result

    result = asyncio.run(install())

    assert result == {
        "taskId": "install-task",
        "versionId": "1.21.8",
        "versionName": "My 1.21.8",
    }
    assert built == [("1.21.8", "My 1.21.8")]
    assert [event["phase"] for event in events] == ["install", "download", "download", "done"]
    assert events[-1]["task_id"] == "install-task"
    log_messages = [call.args[0] for call in service.logger.info.call_args_list]
    assert any("开始安装" in message for message in log_messages)
    assert any("版本安装完成" in message for message in log_messages)


def test_install_version_reports_downloader_failures(tmp_path, monkeypatch) -> None:
    _reset_event_bus()
    events = []
    event_bus = EventBus()
    event_bus.subscribe("game:install_progress", events.append)

    class FailedDownloader(FakeDownloader):
        async def run(self):
            self.failed_entries.add(("https://example.com/client.jar", "client.jar"))

    service = _build_service(downloader_factory=FailedDownloader, event_bus=event_bus)
    monkeypatch.setattr(
        service,
        "_context",
        lambda *_args: SimpleNamespace(
            games=SimpleNamespace(
                build_minecraft_download_list=lambda *_args: [
                    ("https://example.com/client.jar", str(tmp_path / "client.jar"))
                ]
            )
        ),
    )

    async def install():
        result = service.install_version(
            {"version_id": "1.21.8", "task_id": "failed-task"},
            game_path=tmp_path,
        )
        await service._install_tasks[result["taskId"]]

    asyncio.run(install())

    assert events[-1]["phase"] == "error"
    assert events[-1]["errorCode"] == "GAME_DOWNLOAD_FAILED"
    assert "client.jar" in events[-1]["message"]


def test_install_version_returns_immediately_and_rejects_duplicate_task(tmp_path, monkeypatch) -> None:
    started = asyncio.Event()
    release = asyncio.Event()

    class BlockingDownloader(FakeDownloader):
        async def run(self):
            started.set()
            await release.wait()
            await super().run()

    service = _build_service(downloader_factory=BlockingDownloader)
    service.logger = Mock()
    monkeypatch.setattr(
        service,
        "_context",
        lambda *_args: SimpleNamespace(
            games=SimpleNamespace(
                build_minecraft_download_list=lambda *_args: [
                    ("https://example.com/client.jar", str(tmp_path / "client.jar"))
                ]
            )
        ),
    )

    async def scenario():
        result = service.install_version(
            {"version_id": "1.21.8", "task_id": "background-install"},
            game_path=tmp_path,
        )
        task_id = result["taskId"]
        assert result == {
            "taskId": "background-install",
            "versionId": "1.21.8",
            "versionName": "1.21.8",
        }
        assert started.is_set() is False
        assert any("开始安装" in call.args[0] for call in service.logger.info.call_args_list)

        await asyncio.wait_for(started.wait(), timeout=1)
        install_task = service._install_tasks[task_id]
        assert install_task.done() is False
        with pytest.raises(GameServiceError) as error:
            service.install_version(
                {"version_id": "1.21.8", "task_id": task_id},
                game_path=tmp_path,
            )
        assert error.value.error_code == "INSTALL_ALREADY_RUNNING"

        release.set()
        await install_task
        await asyncio.sleep(0)
        assert task_id not in service._install_tasks

    asyncio.run(scenario())


def test_install_version_rejects_incomplete_loader_options(tmp_path) -> None:
    service = _build_service()

    with pytest.raises(GameServiceError) as error:
        service.install_version(
            {"version_id": "1.21.8", "loader_type": "fabric"},
            game_path=tmp_path,
        )

    assert error.value.error_code == "LOADER_VERSION_REQUIRED"
    assert service._install_tasks == {}


def test_launch_instance_checks_files_builds_command_and_tracks_process(tmp_path, monkeypatch) -> None:
    game_path = tmp_path / ".minecraft"
    version_path = game_path / "versions" / "1.21.8"
    version_path.mkdir(parents=True)
    (version_path / "1.21.8.json").write_text("{}", encoding="utf-8")
    java_path = tmp_path / "java.exe"
    java_path.write_bytes(b"")
    instances = FakeInstances()
    captured_configs = []
    clock = [100.0]
    monkeypatch.setattr("ECL.services.game.launch.monotonic", lambda: clock[0])
    service = _build_service(
        instances_manager=instances,
        command_builder=lambda config: captured_configs.append(config) or '"java.exe" game.Main',
    )
    service._search_factory = lambda _path: SimpleNamespace(
        search_minecraft=lambda: {"1.21.8": {"LoaderType": "NeoForge"}}
    )
    crashes = []
    service.events.subscribe("launcher:error", crashes.append)
    monkeypatch.setattr(
        service,
        "_context",
        lambda *_args: SimpleNamespace(
            files_checker=SimpleNamespace(check_files=lambda *_args: []),
        ),
    )

    instance_id = asyncio.run(
        service.launch_instance(
            {"version_id": "1.21.8"},
            game_path=game_path,
            java_path=java_path,
            memory=6144,
            width=1280,
            height=720,
            jvm_args=["-Dexample=true"],
            game_args=["--demo", "hello world"],
        )
    )

    assert instance_id == {
        "instanceId": "minecraft-instance",
        "versionId": "1.21.8",
        "gamePath": str(game_path.resolve()),
    }
    assert captured_configs[0].player_name == "Steve"
    assert captured_configs[0].use_ram == 6144
    assert shlex.split(instances.created["args"])[-2:] == ["--demo", "hello world"]
    assert instances.created["cwd"] == version_path
    assert instances.created["new_session"] is True
    assert service.list_instances() == [
        {
            "id": "minecraft-instance",
            "name": "1.21.8",
            "type": "Minecraft",
            "isRunning": True,
            "pid": 24680,
            "version": "1.21.8",
            "versionId": "1.21.8",
            "loader": "NeoForge",
            "gamePath": str(game_path.resolve()),
        }
    ]
    stats_file = version_path / "eclversion.json"
    launch_stats = json.loads(stats_file.read_text(encoding="utf-8"))
    assert launch_stats["launchCount"] == 1
    assert launch_stats["lastRunDurationSeconds"] == 0
    assert launch_stats["totalRunDurationSeconds"] == 0
    assert launch_stats["lastLaunchedAt"]

    exit_callback = instances.created["exit_callback"]
    clock[0] = 142.9
    instances.exit_instance("minecraft-instance", exit_code=1)
    exit_callback(1, "1.21.8")

    assert service.list_instances() == []
    settled_stats = service.get_version_stats(game_path, "1.21.8")
    assert settled_stats["launchCount"] == 1
    assert settled_stats["lastRunDurationSeconds"] == 42
    assert settled_stats["totalRunDurationSeconds"] == 42
    deadline = time.monotonic() + 3
    while not crashes and time.monotonic() < deadline:
        time.sleep(0.01)
    assert len(crashes) == 1
    assert crashes[0]["title"] == "Minecraft 实例崩溃"
    assert crashes[0]["message"] == "实例“1.21.8”异常退出，退出码：1"
    assert crashes[0]["error_id"]
    assert crashes[0]["kind"] == "game_crash"
    assert crashes[0]["crash"]["reportId"] == crashes[0]["error_id"]
    service.close()


def test_close_keeps_running_game_instances_alive_and_settles_observed_duration(tmp_path, monkeypatch) -> None:
    clock = [10.0]
    service, instances, game_path, _java_path, _result = _launch_lifecycle_fixture(tmp_path, monkeypatch, clock)

    clock[0] = 25.8

    service.close()

    assert instances.shutdown_calls == []
    assert instances.items[0]["Instance"].running is True
    stats = service.get_version_stats(game_path, "1.21.8")
    assert stats["launchCount"] == 1
    assert stats["lastRunDurationSeconds"] == 15
    assert stats["totalRunDurationSeconds"] == 15


def test_stop_instance_removes_runtime_record_and_settles_duration(tmp_path, monkeypatch) -> None:
    clock = [50.0]
    service, instances, game_path, _java_path, result = _launch_lifecycle_fixture(tmp_path, monkeypatch, clock)
    crashes = []
    service.events.subscribe("launcher:error", crashes.append)

    clock[0] = 58.2
    service.stop_instance(result["instanceId"])

    assert service.list_instances() == []
    assert instances.items[0]["Instance"].running is False
    assert instances.exit_requests == [(result["instanceId"], {"wait_timeout": 3.0})]
    assert crashes == []
    stats = service.get_version_stats(game_path, "1.21.8")
    assert stats["launchCount"] == 1
    assert stats["lastRunDurationSeconds"] == 8
    assert stats["totalRunDurationSeconds"] == 8


def test_clean_exit_after_startup_marker_does_not_trigger_crash(tmp_path, monkeypatch) -> None:
    clock = [50.0]
    service, instances, _game_path, _java_path, result = _launch_lifecycle_fixture(tmp_path, monkeypatch, clock)
    crashes = []
    service.events.subscribe("launcher:error", crashes.append)

    instances.created["log_callback"]("[Render thread/INFO]: Sound engine started", result["instanceId"])
    instances.exit_instance(result["instanceId"], exit_code=0)

    assert crashes == []
    service.close()


def test_launch_handles_process_that_exits_before_instance_registration_finishes(tmp_path, monkeypatch) -> None:
    class ImmediateExitInstances(FakeInstances):
        def create_instance(self, **options):
            instance_id = super().create_instance(**options)
            options["exit_callback"](1, options["instance_name"])
            self.items[0]["Instance"].running = False
            return instance_id

    game_path = tmp_path / ".minecraft"
    version_path = game_path / "versions" / "broken"
    version_path.mkdir(parents=True)
    (version_path / "broken.json").write_text("{}", encoding="utf-8")
    java_path = tmp_path / "java.exe"
    java_path.write_bytes(b"")
    events = []
    service = _build_service(
        instances_manager=ImmediateExitInstances(),
        command_builder=lambda _config: '"java.exe" broken.Main',
    )
    service.events.subscribe("launcher:error", events.append)
    monkeypatch.setattr(
        service,
        "_context",
        lambda *_args: SimpleNamespace(files_checker=SimpleNamespace(check_files=lambda *_args: [])),
    )
    monkeypatch.setattr(
        service._crash_analyzer,
        "analyze_runtime",
        lambda **_kwargs: {
            "reportId": "instant-crash",
            "versionId": "broken",
            "exitCode": 1,
            "detectedBy": ["exit_code", "startup_incomplete"],
            "reasons": [],
            "sourceFiles": [],
            "hasOutput": False,
        },
    )

    asyncio.run(service.launch_instance({"version_id": "broken"}, game_path=game_path, java_path=java_path))

    deadline = time.monotonic() + 1
    while not events and time.monotonic() < deadline:
        time.sleep(0.01)
    assert events[0]["kind"] == "game_crash"
    assert events[0]["error_id"] == "instant-crash"
    assert service.list_instances() == []
    service.close()


def test_launch_environment_rejects_java_below_minimum(tmp_path) -> None:
    service = _build_service()
    java_path = tmp_path / "java.exe"
    java_path.write_bytes(b"java")
    service._java_runtimes = [
        SimpleNamespace(path=java_path, version="21.0.8", architecture="amd64", vendor="OpenJDK", is_jdk=True)
    ]

    with pytest.raises(GameServiceError) as error:
        service._validate_launch_environment(str(java_path), 25, 4096)

    assert error.value.error_code == "JAVA_VERSION_INCOMPATIBLE"
    assert "Java 25" in str(error.value)


def test_launch_environment_accepts_java_newer_than_minimum(tmp_path) -> None:
    service = _build_service()
    java_path = tmp_path / "java.exe"
    java_path.write_bytes(b"java")
    service._java_runtimes = [
        SimpleNamespace(path=java_path, version="26-ea", architecture="amd64", vendor="OpenJDK", is_jdk=True)
    ]

    service._validate_launch_environment(str(java_path), 25, 4096)


def test_command_builder_rejects_missing_inherited_version_metadata(tmp_path) -> None:
    game_path = tmp_path / ".minecraft"
    version_path = game_path / "versions" / "neoforge"
    version_path.mkdir(parents=True)
    (version_path / "neoforge.json").write_text(
        json.dumps(
            {
                "id": "neoforge",
                "inheritsFrom": "26.2",
                "mainClass": "net.neoforged.fml.startup.Client",
                "arguments": {"game": ["--fml.neoForgeVersion", "26.2.0.25-beta"]},
                "libraries": [],
            }
        ),
        encoding="utf-8",
    )
    config = LaunchConfig(
        java_path="java.exe",
        game_path=game_path,
        version_name="neoforge",
        use_ram=4096,
        player_name="Player",
        auth_uuid="0" * 32,
    )

    with pytest.raises(FileNotFoundError, match=r"缺少基础版本 26\.2"):
        build_minecraft_cmd(config)


def test_command_builder_places_neoforge_game_arguments_after_main_class(tmp_path) -> None:
    game_path = tmp_path / ".minecraft"
    version_path = game_path / "versions" / "neoforge"
    version_path.mkdir(parents=True)
    (version_path / "neoforge.json").write_text(
        json.dumps(
            {
                "id": "neoforge",
                "inheritsFrom": "26.2",
                "mainClass": "net.neoforged.fml.startup.Client",
                "arguments": {"game": ["--fml.neoForgeVersion", "26.2.0.25-beta"]},
                "libraries": [],
            }
        ),
        encoding="utf-8",
    )
    (version_path / "26.2.json").write_text(
        json.dumps(
            {
                "id": "26.2",
                "arguments": {
                    "jvm": ["-Djava.library.path=${natives_directory}", "-cp", "${classpath}"],
                    "game": ["--username", "${auth_player_name}"],
                },
                "libraries": [],
            }
        ),
        encoding="utf-8",
    )
    (version_path / "26.2.jar").write_bytes(b"jar")
    config = LaunchConfig(
        java_path="java.exe",
        game_path=game_path,
        version_name="neoforge",
        use_ram=4096,
        player_name="Player",
        auth_uuid="0" * 32,
    )

    command = build_minecraft_cmd(config)

    assert command.index('"net.neoforged.fml.startup.Client"') < command.index("--fml.neoForgeVersion")


def test_launch_downloads_missing_inherited_version_metadata_before_file_check(tmp_path, monkeypatch) -> None:
    game_path = tmp_path / ".minecraft"
    version_path = game_path / "versions" / "neoforge"
    version_path.mkdir(parents=True)
    (version_path / "neoforge.json").write_text(
        json.dumps(
            {
                "id": "neoforge",
                "inheritsFrom": "26.2",
                "mainClass": "net.neoforged.fml.startup.Client",
                "arguments": {"game": ["--fml.neoForgeVersion", "26.2.0.25-beta"]},
                "libraries": [],
            }
        ),
        encoding="utf-8",
    )
    java_path = tmp_path / "java.exe"
    java_path.write_bytes(b"")
    calls = []

    class FakeGames:
        def build_minecraft_download_list(self, version_id, save_name, save_version_info):
            calls.append((version_id, save_name, save_version_info))
            (version_path / "26.2.json").write_text('{"id":"26.2"}', encoding="utf-8")
            return "release", {"id": "26.2"}

    class InheritanceCheckingFiles:
        def check_files(self, *_args):
            assert (version_path / "26.2.json").is_file()
            return []

    service = _build_service(
        instances_manager=FakeInstances(),
        command_builder=lambda _config: '"java.exe" game.Main',
    )
    monkeypatch.setattr(
        service,
        "_context",
        lambda *_args: SimpleNamespace(files_checker=InheritanceCheckingFiles(), games=FakeGames()),
    )

    asyncio.run(service.launch_instance({"version_id": "neoforge"}, game_path=game_path, java_path=java_path))

    assert calls == [("26.2", "neoforge", False)]
    service.close()


def test_launch_environment_rejects_large_memory_with_32_bit_java(tmp_path) -> None:
    service = _build_service()
    java_path = tmp_path / "java.exe"
    java_path.write_bytes(b"java")
    service._java_runtimes = [
        SimpleNamespace(path=java_path, version="8.0.451", architecture="x86", vendor="OpenJDK", is_jdk=True)
    ]

    with pytest.raises(GameServiceError) as error:
        service._validate_launch_environment(str(java_path), 8, 4096)

    assert error.value.error_code == "JAVA_ARCH_MEMORY_LIMIT"


@pytest.mark.parametrize(
    ("game_version", "expected"),
    [("1.16.5", 8), ("1.17.1", 16), ("1.20.4", 17), ("1.20.5", 21), ("26.2", 25)],
)
def test_fallback_required_java_tracks_minecraft_runtime_generations(game_version, expected) -> None:
    assert GameService._fallback_required_java(game_version) == expected


def test_concurrent_runs_accumulate_independently(tmp_path, monkeypatch) -> None:
    clock = [100.0]
    service, instances, game_path, java_path, first = _launch_lifecycle_fixture(tmp_path, monkeypatch, clock)
    clock[0] = 110.0
    second = asyncio.run(
        service.launch_instance(
            {"version_id": "1.21.8"},
            game_path=game_path,
            java_path=java_path,
        )
    )
    instances.created["log_callback"]("[Render thread/INFO]: Sound engine started", second["instanceId"])

    clock[0] = 125.0
    instances.exit_instance(second["instanceId"])
    clock[0] = 140.0
    instances.exit_instance(first["instanceId"])

    stats = service.get_version_stats(game_path, "1.21.8")
    assert stats["launchCount"] == 2
    assert stats["lastRunDurationSeconds"] == 40
    assert stats["totalRunDurationSeconds"] == 55
    service.close()


def test_authlib_launch_passes_injector_to_game_backend(tmp_path, monkeypatch) -> None:
    class AuthlibAccounts:
        def current_account(self):
            return {"id": "authlib", "type": "authlib"}

        def get_launch_credentials(self):
            return {
                "player_name": "Player",
                "uuid": "0123456789abcdef0123456789abcdef",
                "user_type": "yggdrasil",
                "access_token": "access-token",
                "auth_server": "https://skin.example.com/api/yggdrasil",
            }

    class FakeInjector:
        def __init__(self, path):
            self.path = path

        def ensure(self):
            return self.path

        def close(self):
            pass

    game_path = tmp_path / ".minecraft"
    version_path = game_path / "versions" / "1.21.8"
    version_path.mkdir(parents=True)
    (version_path / "1.21.8.json").write_text("{}", encoding="utf-8")
    java_path = tmp_path / "java.exe"
    java_path.write_bytes(b"")
    injector_path = tmp_path / "authlib-injector.jar"
    injector_path.write_bytes(b"jar")
    captured_configs = []
    _reset_event_bus()
    events = []
    event_bus = EventBus()
    event_bus.subscribe("game:launch_progress", events.append)
    service = GameService(
        AuthlibAccounts(),
        search_factory=EmptySearchMinecraft,
        instances_manager=FakeInstances(),
        downloader_factory=FakeDownloader,
        command_builder=lambda config: captured_configs.append(config) or '"java.exe" game.Main',
        authlib_injector=FakeInjector(injector_path),
        event_bus=event_bus,
    )
    monkeypatch.setattr(
        service,
        "_context",
        lambda *_args: SimpleNamespace(files_checker=SimpleNamespace(check_files=lambda *_args: [])),
    )

    asyncio.run(
        service.launch_instance(
            {"version_id": "1.21.8"},
            game_path=game_path,
            java_path=java_path,
        )
    )

    config = captured_configs[0]
    assert config.user_type == "yggdrasil"
    assert config.authlib_path == injector_path
    assert config.yggdrasil_api == "https://skin.example.com/api/yggdrasil"
    assert [event["phase"] for event in events[:4]] == [
        "preparing",
        "authlib_token",
        "account_ready",
        "authlib",
    ]
    assert events[1]["message"] == "正在验证外置登录令牌，过期时将自动刷新"


def test_microsoft_launch_reports_token_refresh_progress(tmp_path, monkeypatch) -> None:
    class MicrosoftAccounts:
        def current_account(self):
            return {"id": "microsoft", "type": "microsoft"}

        def get_launch_credentials(self):
            return {
                "player_name": "Player",
                "uuid": "0123456789abcdef0123456789abcdef",
                "user_type": "msa",
                "access_token": "access-token",
            }

    _reset_event_bus()
    events = []
    event_bus = EventBus()
    event_bus.subscribe("game:launch_progress", events.append)
    game_path = tmp_path / ".minecraft"
    version_path = game_path / "versions" / "1.21.8"
    version_path.mkdir(parents=True)
    (version_path / "1.21.8.json").write_text("{}", encoding="utf-8")
    java_path = tmp_path / "java.exe"
    java_path.write_bytes(b"")
    service = GameService(
        MicrosoftAccounts(),
        search_factory=EmptySearchMinecraft,
        instances_manager=FakeInstances(),
        downloader_factory=FakeDownloader,
        command_builder=lambda _config: '"java.exe" game.Main',
        event_bus=event_bus,
    )
    monkeypatch.setattr(
        service,
        "_context",
        lambda *_args: SimpleNamespace(files_checker=SimpleNamespace(check_files=lambda *_args: [])),
    )

    asyncio.run(
        service.launch_instance(
            {"version_id": "1.21.8"},
            game_path=game_path,
            java_path=java_path,
        )
    )

    phases = [event["phase"] for event in events]
    assert phases[:3] == ["preparing", "microsoft_token", "account_ready"]
    assert events[1]["message"] == "正在检查正版登录令牌，过期时将自动刷新"
    assert events[2]["message"] == "正版登录令牌已就绪"


def test_cancel_launch_stops_active_file_download(tmp_path, monkeypatch) -> None:
    class BlockingDownloader(FakeDownloader):
        def __init__(self, *args, **kwargs):
            super().__init__(*args, **kwargs)
            self.stopped = False

        async def run(self):
            while not self.stopped:
                await asyncio.sleep(0.005)
            raise RuntimeError("download stopped")

        def stop(self):
            self.stopped = True

    game_path = tmp_path / ".minecraft"
    version_path = game_path / "versions" / "1.21.8"
    version_path.mkdir(parents=True)
    (version_path / "1.21.8.json").write_text("{}", encoding="utf-8")
    java_path = tmp_path / "java.exe"
    java_path.write_bytes(b"")
    service = _build_service(downloader_factory=BlockingDownloader)
    monkeypatch.setattr(
        service,
        "_context",
        lambda *_args: SimpleNamespace(
            files_checker=SimpleNamespace(
                check_files=lambda *_args: [("https://example.com/client.jar", str(tmp_path / "client.jar"))]
            ),
        ),
    )

    async def launch_then_cancel():
        launch_task = asyncio.create_task(
            service.launch_instance(
                {"version_id": "1.21.8"},
                game_path=game_path,
                java_path=java_path,
            )
        )
        for _ in range(100):
            if "__launch__" in service._active_downloads:
                break
            await asyncio.sleep(0.005)
        assert service.cancel_launch() is True
        with pytest.raises(GameServiceError) as error:
            await launch_task
        return error.value

    error = asyncio.run(launch_then_cancel())

    assert error.error_code == "LAUNCH_CANCELLED"
    assert str(error) == "启动已取消"


def test_launch_instance_reports_core_error_details(tmp_path, monkeypatch) -> None:
    _reset_event_bus()
    events = []
    event_bus = EventBus()
    event_bus.subscribe("game:launch_progress", events.append)
    game_path = tmp_path / ".minecraft"
    version_path = game_path / "versions" / "broken"
    version_path.mkdir(parents=True)
    (version_path / "broken.json").write_text("{}", encoding="utf-8")
    java_path = tmp_path / "java.exe"
    java_path.write_bytes(b"")

    def fail_to_build(_config):
        raise KeyError("mainClass")

    service = _build_service(command_builder=fail_to_build, event_bus=event_bus)
    monkeypatch.setattr(
        service,
        "_context",
        lambda *_args: SimpleNamespace(files_checker=SimpleNamespace(check_files=lambda *_args: [])),
    )

    with pytest.raises(GameServiceError) as error:
        asyncio.run(
            service.launch_instance(
                {"version_id": "broken"},
                game_path=game_path,
                java_path=java_path,
            )
        )

    assert error.value.error_code == "GAME_LAUNCH_FAILED"
    assert "mainClass" in str(error.value)
    assert events[-1]["phase"] == "error"
    assert events[-1]["errorCode"] == "GAME_LAUNCH_FAILED"
    assert "mainClass" in events[-1]["message"]


def test_uninstall_version_only_removes_selected_version(tmp_path) -> None:
    service = _build_service()
    selected = tmp_path / "versions" / "1.20.1"
    other = tmp_path / "versions" / "1.21.8"
    selected.mkdir(parents=True)
    other.mkdir(parents=True)

    service.uninstall_version("1.20.1", tmp_path)

    assert not selected.exists()
    assert other.is_dir()
    with pytest.raises(GameServiceError) as error:
        service.uninstall_version("../outside", tmp_path)
    assert error.value.error_code == "INVALID_VERSION_NAME"


def test_ecl_config_read_write_and_patch(tmp_path) -> None:
    game_path = tmp_path / ".minecraft"
    service = _build_service()

    # 文件不存在时返回空字典
    assert service.read_ecl_config(game_path) == {}

    # 写入完整配置
    service.write_ecl_config(game_path, {"activeVersion": "1.21.1", "customField": 42})
    ecl_file = game_path / "ecl.json"
    assert ecl_file.is_file()
    assert service.read_ecl_config(game_path) == {"activeVersion": "1.21.1", "customField": 42}

    # 增量更新
    updated = service.patch_ecl_config(game_path, {"activeVersion": "1.20.1", "newKey": "hello"})
    assert updated == {"activeVersion": "1.20.1", "customField": 42, "newKey": "hello"}
    assert service.read_ecl_config(game_path) == updated


def test_ecl_config_skips_unchanged_writes(tmp_path, monkeypatch) -> None:
    game_path = tmp_path / ".minecraft"
    service = _build_service()
    writes = []
    original_write = __import__("ECL.services.game.scan", fromlist=["atomic_write_text"]).atomic_write_text

    def tracked_write(path, data):
        writes.append((path, data))
        original_write(path, data)

    monkeypatch.setattr("ECL.services.game.scan.atomic_write_text", tracked_write)
    config = {"activeVersion": "1.21.1", "customField": 42}

    service.write_ecl_config(game_path, config)
    service.write_ecl_config(game_path, dict(config))
    patched = service.patch_ecl_config(game_path, {"activeVersion": "1.21.1"})

    assert patched == config
    assert len(writes) == 1


def test_ecl_config_serializes_concurrent_identical_patches(tmp_path, monkeypatch) -> None:
    game_path = tmp_path / ".minecraft"
    service = _build_service()
    service.write_ecl_config(game_path, {"activeVersion": "old", "customField": 42})
    writes = []
    original_write = __import__("ECL.services.game.scan", fromlist=["atomic_write_text"]).atomic_write_text

    def tracked_write(path, data):
        writes.append((path, data))
        time.sleep(0.02)
        original_write(path, data)

    monkeypatch.setattr("ECL.services.game.scan.atomic_write_text", tracked_write)
    with ThreadPoolExecutor(max_workers=2) as executor:
        results = list(
            executor.map(
                lambda _index: service.patch_ecl_config(game_path, {"activeVersion": "new"}),
                range(2),
            )
        )

    assert results == [
        {"activeVersion": "new", "customField": 42},
        {"activeVersion": "new", "customField": 42},
    ]
    assert len(writes) == 1
    assert service.read_ecl_config(game_path) == results[0]


def test_ecl_active_version_get_and_set(tmp_path) -> None:
    game_path = tmp_path / ".minecraft"
    service = _build_service()

    # 没有 activeVersion 时返回 None
    assert service.get_active_version(game_path) is None

    # 设置后能读回
    service.set_active_version(game_path, "1.21.1")
    assert service.get_active_version(game_path) == "1.21.1"

    # 兼容 snake_case 别名
    service.write_ecl_config(game_path, {"active_version": "1.19.4"})
    assert service.get_active_version(game_path) == "1.19.4"


def test_ecl_config_rejects_invalid_data(tmp_path) -> None:
    game_path = tmp_path / ".minecraft"
    service = _build_service()

    with pytest.raises(GameServiceError) as error:
        service.write_ecl_config(game_path, ["not", "a", "dict"])  # type: ignore[arg-type]
    assert error.value.error_code == "INVALID_ECL_CONFIG"

    with pytest.raises(GameServiceError) as error:
        service.patch_ecl_config(game_path, "not-a-dict")  # type: ignore[arg-type]
    assert error.value.error_code == "INVALID_ECL_CONFIG"


def test_ecl_config_handles_corrupted_file(tmp_path) -> None:
    game_path = tmp_path / ".minecraft"
    game_path.mkdir(parents=True)
    (game_path / "ecl.json").write_text("{invalid json", encoding="utf-8")
    service = _build_service()

    # 损坏的文件返回空字典，不抛异常
    assert service.read_ecl_config(game_path) == {}


def test_local_mod_lifecycle_stays_inside_mods_directory(tmp_path) -> None:
    game_path = tmp_path / ".minecraft"
    source = tmp_path / "example.jar"
    source.write_bytes(b"safe-mod")
    service = _build_service()

    filename = service.add_mod(game_path, source)
    mods = service.list_mods(game_path)
    disabled = service.toggle_mod(game_path, filename)
    service.remove_mod(game_path, f"{filename}.disabled")

    assert filename == "example.jar"
    assert mods[0]["enabled"] is True
    assert disabled is False
    assert service.list_mods(game_path) == []
    with pytest.raises(GameServiceError, match="路径超出允许范围"):
        service.remove_mod(game_path, "../outside.jar")
