from __future__ import annotations

import asyncio
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from ECL.Events import EventBus
from ECL.Services.game import GameService, GameServiceError, _ResumableDownloader


class FakeAccounts:
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

    def poll(self):
        return None if self.running else 0


class FakeInstances:
    def __init__(self):
        self.items = []
        self.created = None

    def create_instance(self, **options):
        instance_id = "minecraft-instance"
        self.created = options
        self.items.append(
            {
                "ID": instance_id,
                "Name": options["instance_name"],
                "Type": options["instance_type"],
                "Instance": FakeProcess(),
            }
        )
        return instance_id

    def get_instances_info(self):
        return list(self.items)

    def stop_instance(self, instance_id, **_options):
        for item in self.items:
            if item["ID"] == instance_id:
                item["Instance"].running = False
        return True

    def shutdown_all(self, **_options):
        return None


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


class FakeStreamResponse:
    status_code = 206

    def __init__(self, chunks):
        self.headers = {"content-length": str(sum(len(chunk) for chunk in chunks))}
        self._chunks = chunks

    async def __aenter__(self):
        return self

    async def __aexit__(self, *_args):
        return None

    def raise_for_status(self):
        return None

    async def aiter_bytes(self, _chunk_size):
        for chunk in self._chunks:
            yield chunk


class FakeDownloadClient:
    def __init__(self, chunks):
        self.chunks = chunks
        self.headers = None

    def stream(self, _method, _url, *, headers, timeout):
        self.headers = headers
        assert timeout.read == 120.0
        return FakeStreamResponse(self.chunks)


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
    assert requested_paths == [game_path]


def test_install_version_builds_and_downloads_with_progress(tmp_path, monkeypatch) -> None:
    _reset_event_bus()
    events = []
    EventBus().subscribe("game:install_progress", events.append)
    built = []

    class FakeGames:
        def build_minecraft_download_list(self, version_id, save_name):
            built.append((version_id, save_name))
            return [("https://example.com/client.jar", str(tmp_path / "client.jar"))]

    service = _build_service()
    service.logger = Mock()
    monkeypatch.setattr(
        service,
        "_context",
        lambda *_args: SimpleNamespace(games=FakeGames()),
    )

    asyncio.run(
        service.install_version(
            {
                "version_id": "1.21.8",
                "version_name": "My 1.21.8",
                "task_id": "install-task",
            },
            game_path=tmp_path,
            download_threads=12,
        )
    )

    assert built == [("1.21.8", "My 1.21.8")]
    assert [event["phase"] for event in events] == ["install", "download", "download", "done"]
    assert events[-1]["task_id"] == "install-task"
    log_messages = [call.args[0] for call in service.logger.info.call_args_list]
    assert any("开始执行安装任务" in message for message in log_messages)
    assert any("安装文件列表生成完成" in message for message in log_messages)
    assert any("开始下载游戏文件" in message for message in log_messages)
    assert any("安装任务完成" in message for message in log_messages)


def test_install_version_reports_downloader_failures(tmp_path, monkeypatch) -> None:
    _reset_event_bus()
    events = []
    EventBus().subscribe("game:install_progress", events.append)

    class FailedDownloader(FakeDownloader):
        async def run(self):
            self.failed_entries.add(("https://example.com/client.jar", "client.jar"))

    service = _build_service(downloader_factory=FailedDownloader)
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

    with pytest.raises(GameServiceError) as error:
        asyncio.run(
            service.install_version(
                {"version_id": "1.21.8", "task_id": "failed-task"},
                game_path=tmp_path,
            )
        )

    assert error.value.error_code == "GAME_DOWNLOAD_FAILED"
    assert events[-1]["phase"] == "error"


def test_start_install_returns_immediately_and_rejects_duplicate_task(tmp_path, monkeypatch) -> None:
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
        task_id = service.start_install(
            {"version_id": "1.21.8", "task_id": "background-install"},
            game_path=tmp_path,
        )
        assert task_id == "background-install"
        assert started.is_set() is False
        assert any(
            "安装任务已创建" in call.args[0]
            for call in service.logger.info.call_args_list
        )

        await asyncio.wait_for(started.wait(), timeout=1)
        install_task = service._install_tasks[task_id]
        assert install_task.done() is False
        with pytest.raises(GameServiceError) as error:
            service.start_install(
                {"version_id": "1.21.8", "task_id": task_id},
                game_path=tmp_path,
            )
        assert error.value.error_code == "INSTALL_ALREADY_RUNNING"

        release.set()
        await install_task
        await asyncio.sleep(0)
        assert task_id not in service._install_tasks

    asyncio.run(scenario())


def test_resumable_downloader_continues_existing_temp_file(tmp_path) -> None:
    target = tmp_path / "client.jar"
    target.with_suffix(".jar.tmp").write_bytes(b"abcd")

    async def run_download():
        downloader = _ResumableDownloader([("https://example.com/client.jar", target)])
        client = FakeDownloadClient([b"efgh"])
        downloader.client = client
        downloader.total_bytes = 8
        result = await downloader._download_file_once(
            "https://example.com/client.jar",
            target,
            8,
        )
        await asyncio.sleep(0)
        return result, client

    result, client = asyncio.run(run_download())

    assert result is True
    assert client.headers["Range"] == "bytes=4-"
    assert target.read_bytes() == b"abcdefgh"
    assert not target.with_suffix(".jar.tmp").exists()


def test_launch_instance_checks_files_builds_command_and_tracks_process(tmp_path, monkeypatch) -> None:
    game_path = tmp_path / ".minecraft"
    version_path = game_path / "versions" / "1.21.8"
    version_path.mkdir(parents=True)
    (version_path / "1.21.8.json").write_text("{}", encoding="utf-8")
    java_path = tmp_path / "java.exe"
    java_path.write_bytes(b"")
    instances = FakeInstances()
    captured_configs = []
    service = _build_service(
        instances_manager=instances,
        command_builder=lambda config: captured_configs.append(config) or '"java.exe" game.Main',
    )
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
            game_args=["--demo"],
        )
    )

    assert instance_id == "minecraft-instance"
    assert captured_configs[0].player_name == "Steve"
    assert captured_configs[0].use_ram == 6144
    assert instances.created["args"].endswith("--demo")
    assert service.list_instances() == [
        {
            "id": "minecraft-instance",
            "name": "1.21.8",
            "type": "Minecraft",
            "isRunning": True,
            "version": "1.21.8",
        }
    ]


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
