import shlex
import subprocess
import sys
from collections.abc import Mapping
from pathlib import Path
from threading import Event
from time import monotonic
from typing import Any
from uuid import uuid4

import httpx
from anyio import to_thread

from ECL.game import LaunchConfig
from ECL.services.authlib import AuthlibError

from .base import GameServiceError, _GameState, _RunningGame


class LaunchCoordinator(_GameState):
    def _emit_launch_progress(
        self,
        phase: str,
        message: str,
        percent: int | None = None,
        error_code: str | None = None,
    ) -> None:
        payload: dict[str, Any] = {"phase": phase, "message": message}
        if percent is not None:
            payload["percent"] = percent
        if error_code:
            payload["errorCode"] = error_code
        self.events.emit("game:launch_progress", payload)

    def _resolve_java_path(self, value: Any, required_major: int | None = None) -> str:
        raw_path = str(value or "").strip()
        if raw_path:
            path = Path(raw_path).expanduser()
            if not path.is_file():
                raise GameServiceError("Java 可执行文件不存在", "JAVA_NOT_FOUND")
            return str(path.resolve())

        if not self._java_runtimes:
            self.scan_java()
        candidates = self._java_runtimes
        if required_major:
            candidates = [
                runtime for runtime in candidates if self._java_major_version(runtime.version) >= required_major
            ]
        if not candidates:
            if required_major:
                raise GameServiceError(f"未找到 Java {required_major} 或更高版本", "JAVA_VERSION_NOT_FOUND")
            raise GameServiceError("未找到 Java，请先在设置中选择 Java", "JAVA_NOT_FOUND")
        if required_major:
            runtime = min(
                candidates,
                key=lambda item: (self._java_major_version(item.version), str(item.path).casefold()),
            )
        else:
            runtime = max(candidates, key=lambda item: self._java_major_version(item.version))
        return str(runtime.path)

    async def launch_instance(  # noqa: C901 - launch transaction and cleanup boundary
        self,
        body: Mapping[str, object],
        *,
        game_path: Any,
        source: Any = "official",
        java_path: Any = None,
        memory: Any = 4096,
        width: Any = 854,
        height: Any = 480,
        jvm_args: Any = None,
        game_args: Any = None,
        version_isolation: Any = False,
    ) -> dict[str, str]:
        """
        检查游戏文件并启动实例。

        :param body: 经过边界校验的 IPC 请求数据
        :param game_path: Minecraft 游戏根目录
        :param source: 下载源名称，如 ``official`` 或 ``bmclapi``
        :param java_path: Java 可执行文件路径
        :param memory: 分配给游戏的内存大小，单位为 MiB
        :param width: 游戏窗口宽度
        :param height: 游戏窗口高度
        :param jvm_args: 附加的 JVM 参数列表
        :param game_args: 附加的 Minecraft 参数列表
        :param version_isolation: 是否启用版本目录隔离
        """
        version_name = self._normalize_version_name(body.get("version_id"))
        path = self._normalize_game_path(game_path)
        self.logger.debug(
            "准备启动实例: version=%s, path=%s, memory=%s, java=%s",
            version_name,
            path,
            memory,
            java_path,
        )
        version_json = path / "versions" / version_name / f"{version_name}.json"
        if not version_json.is_file():
            raise GameServiceError("游戏实例不存在或版本 JSON 缺失", "VERSION_NOT_FOUND")
        scanned_versions = self._search_factory(path).search_minecraft()
        version_info = scanned_versions.get(version_name, {}) if isinstance(scanned_versions, dict) else {}
        required_java_value = str(version_info.get("RequestJava") or "")
        required_java = int(required_java_value) if required_java_value.isdigit() else None
        java = self._resolve_java_path(java_path, required_java)
        ram = self._normalize_positive_int(memory, 4096, 256, 131072, "游戏内存")
        window_width = self._normalize_positive_int(width, 854, 320, 16384, "窗口宽度")
        window_height = self._normalize_positive_int(height, 480, 240, 16384, "窗口高度")
        custom_jvm_args = self._normalize_string_list(jvm_args, "JVM 参数")
        custom_game_args = self._normalize_string_list(game_args, "游戏参数")
        context = self._context(path, self._normalize_source(source))
        isolated = bool(version_isolation)

        cancel_event = Event()
        with self._lock:
            if self._launch_cancel_event is not None:
                raise GameServiceError("已有游戏启动任务正在运行", "LAUNCH_ALREADY_RUNNING")
            self._launch_cancel_event = cancel_event

        try:
            self._emit_launch_progress("preparing", f"正在准备启动 {version_name}", 3)
            current_account_getter = getattr(self.accounts, "current_account", None)
            current_account = current_account_getter() if callable(current_account_getter) else None
            account_type = current_account.get("type") if isinstance(current_account, dict) else None
            if account_type == "microsoft":
                self._emit_launch_progress(
                    "microsoft_token",
                    "正在检查正版登录令牌，过期时将自动刷新",
                    7,
                )
            elif account_type == "authlib":
                self._emit_launch_progress(
                    "authlib_token",
                    "正在验证外置登录令牌，过期时将自动刷新",
                    7,
                )
            elif account_type == "offline":
                self._emit_launch_progress("offline_account", "正在读取离线账户信息", 7)
            else:
                self._emit_launch_progress("account", "正在验证游戏账户", 7)
            credentials = await to_thread.run_sync(self.accounts.get_launch_credentials)
            if credentials["user_type"] == "msa":
                self._emit_launch_progress("account_ready", "正版登录令牌已就绪", 17)
            elif credentials["user_type"] == "yggdrasil":
                self._emit_launch_progress("account_ready", "外置登录令牌已就绪", 17)
            else:
                self._emit_launch_progress("account_ready", "离线账户已就绪", 17)
            if cancel_event.is_set():
                raise GameServiceError("启动已取消", "LAUNCH_CANCELLED")

            authlib_path = None
            auth_server = None
            if credentials["user_type"] == "yggdrasil":
                if self.authlib_injector is None:
                    raise GameServiceError("未配置外置登录组件目录", "AUTHLIB_INJECTOR_UNAVAILABLE")
                auth_server = credentials.get("auth_server")
                if not auth_server:
                    raise GameServiceError("外置登录认证服务器地址缺失", "AUTHLIB_SERVER_MISSING")
                self._emit_launch_progress("authlib", "正在准备外置登录组件", 20)
                try:
                    authlib_path = await to_thread.run_sync(self.authlib_injector.ensure)
                except (AuthlibError, OSError, KeyError, TypeError, ValueError, httpx.HTTPError) as exc:
                    raise GameServiceError(f"准备外置登录组件失败: {exc}", "AUTHLIB_INJECTOR_FAILED") from exc

            self._emit_launch_progress("checking", "正在检查游戏文件", 25)
            download_list = await to_thread.run_sync(context.files_checker.check_files, path, version_name)
            if cancel_event.is_set():
                raise GameServiceError("启动已取消", "LAUNCH_CANCELLED")
            self._emit_launch_progress(
                "files_checked",
                f"文件检查完成，共需补全 {len(download_list)} 个文件",
                55,
            )
            if download_list:
                downloader = self._downloader_factory(
                    download_list,
                    progress_callback=lambda done, total: self._emit_launch_progress(
                        "downloading",
                        "正在补全游戏文件",
                        55 + int(done * 15 / total) if total else 55,
                    ),
                )
                with self._lock:
                    self._active_downloads["__launch__"] = downloader
                try:
                    await downloader.run()
                except Exception as exc:
                    if cancel_event.is_set():
                        raise GameServiceError("启动已取消", "LAUNCH_CANCELLED") from exc
                    raise
                finally:
                    with self._lock:
                        self._active_downloads.pop("__launch__", None)
                if cancel_event.is_set():
                    raise GameServiceError("启动已取消", "LAUNCH_CANCELLED")
                if downloader.failed_entries:
                    failed_url, failed_path = next(iter(downloader.failed_entries))
                    raise GameServiceError(
                        f"有 {len(downloader.failed_entries)} 个游戏文件补全失败，例如 {failed_path}（{failed_url}）",
                        "GAME_DOWNLOAD_FAILED",
                    )

            self._emit_launch_progress("building_args", "正在生成启动参数", 72)
            launch_config = LaunchConfig(
                java_path=java,
                game_path=path,
                version_name=version_name,
                use_ram=ram,
                player_name=credentials["player_name"],
                auth_uuid=credentials["uuid"],
                user_type=credentials["user_type"],
                access_token=credentials["access_token"],
                custom_jvm_params=custom_jvm_args or None,
                version_isolation=isolated,
                window_width=window_width,
                window_height=window_height,
                authlib_path=authlib_path,
                yggdrasil_api=auth_server,
            )
            command = await to_thread.run_sync(self._command_builder, launch_config)
            if custom_game_args:
                if sys.platform == "win32":
                    formatted_args = subprocess.list2cmdline(custom_game_args)
                else:
                    formatted_args = shlex.join(custom_game_args)
                command = f"{command} {formatted_args}"
            self._emit_launch_progress("args_built", "启动参数生成完成", 84)
            if cancel_event.is_set():
                raise GameServiceError("启动已取消", "LAUNCH_CANCELLED")

            self._emit_launch_progress("about_to_launch", "即将启动游戏", 94)
            self._emit_launch_progress("launching", "正在创建游戏进程", 97)
            run_token = uuid4().hex
            run = _RunningGame(
                token=run_token,
                version_id=version_name,
                game_path=path,
                started_at=monotonic(),
            )
            with self._lock:
                self._running_games[run_token] = run
            try:
                instance_id = self.instances.create_instance(
                    instance_name=version_name,
                    instance_type="Minecraft",
                    args=command,
                    cwd=path / "versions" / version_name,
                    new_session=True,
                    log_callback=lambda line, current_id: self.logger.debug("[%s] %s", current_id, line),
                    exit_callback=lambda code, name: self._handle_instance_exit(run_token, code, name),
                )
            except Exception:
                with self._lock:
                    self._running_games.pop(run_token, None)
                raise

            with self._lock:
                registered_run = self._running_games.get(run_token)
                if registered_run is not None:
                    registered_run.instance_id = instance_id
            self._version_stats.record_launch(path, version_name)
            with self._lock:
                registered_run = self._running_games.get(run_token)
                if registered_run is not None:
                    registered_run.pending = False
                    already_exited = registered_run.exited
                else:
                    already_exited = True
            if already_exited:
                self._finalize_instance_run(run_token, action="exited")
            else:
                self._emit_instance_change(run, "started")
            self._emit_launch_progress("launched", f"{version_name} 已启动", 100)
            return {
                "instanceId": instance_id,
                "versionId": version_name,
                "gamePath": str(path),
            }
        except GameServiceError as exc:
            if exc.error_code != "LAUNCH_CANCELLED":
                self._emit_launch_progress("error", str(exc), 0, exc.error_code)
            raise
        except Exception as exc:
            self.logger.exception("启动 Minecraft 失败")
            error = GameServiceError(f"启动游戏失败: {exc}", "GAME_LAUNCH_FAILED")
            self._emit_launch_progress("error", str(error), 0, error.error_code)
            raise error from exc
        finally:
            with self._lock:
                self._launch_cancel_event = None

    def cancel_launch(self) -> bool:
        """
        取消正在执行的启动或文件补全任务。

        """
        with self._lock:
            cancel_event = self._launch_cancel_event
            downloader = self._active_downloads.get("__launch__")
        if cancel_event is None:
            return False
        cancel_event.set()
        if downloader is not None:
            downloader.stop()
        return True

    def _emit_instance_change(self, run: _RunningGame, action: str) -> None:
        if not run.instance_id:
            return
        self.events.emit(
            "game:instances_changed",
            {
                "action": action,
                "instanceId": run.instance_id,
                "versionId": run.version_id,
                "gamePath": str(run.game_path),
            },
        )

    def _handle_instance_exit(self, run_token: str, exit_code: int, instance_name: str) -> None:
        """
        接收进程管理器线程的唯一退出通知，并在启动注册完成后结算统计。

        :param run_token: 启动前创建的会话内令牌
        :param exit_code: Minecraft 进程退出码
        :param instance_name: 供日志识别的版本名称
        """
        self.logger.info("Minecraft %s 已退出，退出码: %s", instance_name, exit_code)
        with self._lock:
            run = self._running_games.get(run_token)
            if run is None:
                return
            run.exited = True
            run.exit_code = exit_code
            if run.pending:
                return
            action = "stopped" if run.stopping else "exited"
        self._finalize_instance_run(run_token, action=action)

    def _finalize_instance_run(self, run_token: str, *, action: str) -> None:
        """
        从内存运行表移除一次运行，并恰好一次地累计已观察时长。

        该方法同时服务于自然退出、用户终止、列表校正和应用关闭。先从共享表移除再
        写入统计，确保并发回调不会重复累计。

        :param run_token: 会话内运行令牌
        :param action: ``exited``、``stopped`` 或 ``launcher_closed``
        """
        with self._lock:
            run = self._running_games.get(run_token)
            if run is None or run.pending:
                return
            self._running_games.pop(run_token, None)
        duration_seconds = max(0, int(monotonic() - run.started_at))
        self._version_stats.record_duration(run.game_path, run.version_id, duration_seconds)
        self.logger.debug(
            "游戏运行已结算: version=%s, action=%s, duration=%ss",
            run.version_id,
            action,
            duration_seconds,
        )
        if action != "launcher_closed":
            self._emit_instance_change(run, action)

    def get_version_stats(self, game_path: Any, version_id: Any) -> dict[str, int]:
        """
        返回指定版本目录中的运行统计。

        :param game_path: Minecraft 游戏根目录
        :param version_id: 版本目录名称
        :return: 启动次数、上次运行秒数和总运行秒数
        """
        path = self._normalize_game_path(game_path)
        name = self._normalize_version_name(version_id)
        if not (path / "versions" / name).is_dir():
            raise GameServiceError("游戏实例不存在", "VERSION_NOT_FOUND")
        return dict(self._version_stats.read(path, name))

    def list_instances(self) -> list[dict[str, Any]]:
        """
        返回由启动器管理的运行中 Minecraft 实例。

        """
        raw_instances = self.instances.get_instances_info()
        with self._lock:
            runs_by_instance = {
                run.instance_id: (token, run)
                for token, run in self._running_games.items()
                if run.instance_id is not None and not run.pending
            }

        result = []
        for item in raw_instances:
            if item.get("Type") != "Minecraft":
                continue
            instance_id = str(item.get("ID") or "")
            process = item.get("Instance")
            mapped = runs_by_instance.get(instance_id)
            is_running = bool(process is not None and process.poll() is None)
            if not is_running:
                if mapped is not None:
                    token, run = mapped
                    self._finalize_instance_run(token, action="stopped" if run.stopping else "exited")
                continue
            run = mapped[1] if mapped is not None else None
            version_id = run.version_id if run is not None else str(item.get("Name") or "")
            result.append(
                {
                    "id": instance_id,
                    "name": str(item.get("Name") or version_id or "Minecraft"),
                    "type": "Minecraft",
                    "isRunning": True,
                    "version": version_id,
                    "versionId": version_id,
                    "gamePath": str(run.game_path) if run is not None else "",
                }
            )
        return result

    def stop_instance(self, instance_id: Any) -> None:
        """
        通知指定的运行中 Minecraft 实例退出，超时后才强制结束。

        :param instance_id: 运行中游戏实例的标识
        """
        if not isinstance(instance_id, str) or not instance_id.strip():
            raise GameServiceError("实例 ID 不能为空", "INVALID_INSTANCE_ID")
        existing_ids = {
            str(item.get("ID")) for item in self.instances.get_instances_info() if item.get("Type") == "Minecraft"
        }
        if instance_id not in existing_ids:
            raise GameServiceError("游戏实例不存在", "INSTANCE_NOT_FOUND")
        with self._lock:
            matched = next(
                (
                    (token, run)
                    for token, run in self._running_games.items()
                    if run.instance_id == instance_id and not run.pending
                ),
                None,
            )
            if matched is not None:
                matched[1].stopping = True
        self.instances.request_instance_exit(instance_id, wait_timeout=3.0)
        if matched is not None:
            self._finalize_instance_run(matched[0], action="stopped")
