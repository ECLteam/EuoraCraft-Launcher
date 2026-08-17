import asyncio
import shutil
from collections.abc import Mapping
from pathlib import Path
from typing import Any
from uuid import uuid4

from anyio import to_thread

from .base import GameServiceError, _GameState


class InstallCoordinator(_GameState):
    def _emit_install_progress(
        self,
        task_id: str,
        phase: str,
        message: str,
        *,
        done: int | None = None,
        total: int | None = None,
        progress_type: str | None = None,
        total_files: int | None = None,
        downloaded_files: int | None = None,
        speed: int | None = None,
        subtask: str | None = None,
        error_code: str | None = None,
    ) -> None:
        payload: dict[str, Any] = {
            "phase": phase,
            "task_id": task_id,
            "message": message,
        }
        if done is not None:
            payload["done"] = done
        if total is not None:
            payload["total"] = total
        if progress_type:
            payload["progress_type"] = progress_type
        if total_files is not None:
            payload["total_files"] = total_files
        if downloaded_files is not None:
            payload["downloaded_files"] = downloaded_files
        if speed is not None:
            payload["speed"] = speed
        if subtask:
            payload["subtask"] = subtask
        if error_code:
            payload["errorCode"] = error_code
        self.events.emit("game:install_progress", payload)

    def install_version(
        self,
        body: Mapping[str, object],
        *,
        game_path: Any,
        source: Any = "official",
        java_path: str | None = None,
    ) -> dict[str, str]:
        """
        开始安装版本，返回任务 ID 和最终保存的版本名称。

        :param body: 经过边界校验的 IPC 请求数据
        :param game_path: Minecraft 游戏根目录
        :param source: 下载源名称，如 ``official`` 或 ``bmclapi``
        :param java_path: Java 可执行文件路径
        """
        path = self._normalize_game_path(game_path)
        normalized_source = self._normalize_source(source)
        version_id = self._normalize_version_name(body.get("version_id"), "Minecraft 版本")
        save_name = self._normalize_version_name(body.get("version_name") or version_id)
        loader = str(body.get("loader_type") or "vanilla").strip().casefold()
        if loader in {"", "none"}:
            loader = "vanilla"
        if loader not in {"vanilla", "fabric", "forge", "neoforge", "quilt"}:
            raise GameServiceError(f"暂不支持安装加载器: {body.get('loader_type')}", "UNSUPPORTED_LOADER")

        self.logger.debug(
            "开始安装版本: version=%s, loader=%s, path=%s, source=%s, save_name=%s",
            version_id,
            loader,
            path,
            normalized_source,
            save_name,
        )

        loader_version = None
        if loader != "vanilla":
            field_name = f"{loader}_version"
            value = body.get(field_name)
            if not isinstance(value, str) or not value.strip():
                raise GameServiceError("未选择加载器版本", "LOADER_VERSION_REQUIRED")
            loader_version = value.strip()
        if loader in {"forge", "neoforge"}:
            java_path = self._resolve_java_path(java_path)

        path.mkdir(parents=True, exist_ok=True)
        (path / "versions").mkdir(parents=True, exist_ok=True)
        requested_task_id = body.get("task_id")
        task_id = requested_task_id.strip() if isinstance(requested_task_id, str) else ""
        if not task_id:
            task_id = f"install-{uuid4().hex}"

        loop = asyncio.get_running_loop()
        with self._lock:
            existing = self._install_tasks.get(task_id)
            if existing is not None and not existing.done():
                raise GameServiceError("相同的安装任务已在运行", "INSTALL_ALREADY_RUNNING")
            task = loop.create_task(
                self._run_install(
                    task_id,
                    version_id,
                    save_name,
                    loader,
                    loader_version,
                    path,
                    normalized_source,
                    java_path,
                ),
                name=f"ECLInstall-{task_id}",
            )
            self._install_tasks[task_id] = task
        self.logger.info("开始安装 %s，保存为 %s，加载器: %s", version_id, save_name, loader)
        return {"taskId": task_id, "versionId": version_id, "versionName": save_name}

    async def _run_install(
        self,
        task_id: str,
        version_id: str,
        save_name: str,
        loader: str,
        loader_version: str | None,
        game_path: Path,
        source: str,
        java_path: str | None,
    ) -> None:
        self._emit_install_progress(task_id, "install", "正在读取实例信息", done=0, total=1)
        try:
            games = self._context(game_path, source).games
            if loader == "vanilla":
                download_list = await to_thread.run_sync(
                    games.build_minecraft_download_list,
                    version_id,
                    save_name,
                )
            elif loader == "fabric":
                download_list = await to_thread.run_sync(
                    games.build_fabric_download_list,
                    version_id,
                    loader_version,
                    save_name,
                )
            elif loader == "quilt":
                download_list = await to_thread.run_sync(
                    games.build_quilt_download_list,
                    version_id,
                    loader_version,
                    save_name,
                )
            elif loader == "forge":
                download_list = await to_thread.run_sync(
                    games.build_forge_download_list,
                    version_id,
                    loader_version,
                    java_path,
                    save_name,
                )
            else:
                download_list = await to_thread.run_sync(
                    games.build_neoforged_download_list,
                    version_id,
                    loader_version,
                    java_path,
                    save_name,
                )

            if not download_list:
                self._emit_install_progress(task_id, "done", f"{save_name} 已安装完成", done=1, total=1)
                return

            # 进度事件闭包：同时上报字节/文件进度、文件计数与实时速度。
            # 通过可变容器持有 downloader 引用，避免闭包在赋值前被调用。
            progress_state: dict[str, Any] = {"downloader": None, "speed": 0}

            def _emit_download_progress(speed: int | None = None) -> None:
                if speed is not None:
                    progress_state["speed"] = speed
                downloader = progress_state["downloader"]
                self._emit_install_progress(
                    task_id,
                    "download",
                    f"正在下载 {save_name}",
                    done=downloader.downloaded_bytes,
                    total=downloader.total_bytes,
                    progress_type="bytes" if downloader.use_byte_progress else "files",
                    total_files=downloader.total_files,
                    downloaded_files=len(downloader.completed_entries),
                    speed=progress_state["speed"],
                    subtask="download_files",
                )

            downloader = self._downloader_factory(
                download_list,
                progress_callback=lambda done, total: _emit_download_progress(),
                speed_callback=lambda speed_mb: _emit_download_progress(int(speed_mb * 1024 * 1024)),
            )
            progress_state["downloader"] = downloader
            with self._lock:
                self._active_downloads[task_id] = downloader

            self._emit_install_progress(
                task_id,
                "download",
                f"准备下载 {len(download_list)} 个文件",
                done=0,
                total=len(download_list),
                progress_type="files",
                total_files=len(download_list),
                downloaded_files=0,
                subtask="download_files",
            )
            await downloader.run()
            if downloader.failed_entries:
                failed_url, failed_path = next(iter(downloader.failed_entries))
                raise GameServiceError(
                    f"有 {len(downloader.failed_entries)} 个文件下载失败，例如 {failed_path}（{failed_url}）",
                    "GAME_DOWNLOAD_FAILED",
                )
            self.logger.info("版本安装完成: %s", save_name)
            self._emit_install_progress(task_id, "done", f"{save_name} 已安装完成", done=1, total=1)
        except asyncio.CancelledError:
            self.logger.info("安装任务已取消: %s", task_id)
            self._emit_install_progress(task_id, "error", "安装已取消", error_code="INSTALL_CANCELLED")
        except GameServiceError as exc:
            self.logger.error("版本安装失败 [%s]: %s", exc.error_code, exc)
            self._emit_install_progress(
                task_id,
                "error",
                str(exc),
                done=0,
                total=1,
                error_code=exc.error_code,
            )
        except Exception as exc:
            self.logger.exception("Core 安装版本失败: %s", save_name)
            self._emit_install_progress(
                task_id,
                "error",
                f"安装 {save_name} 失败: {exc}",
                done=0,
                total=1,
                error_code="VERSION_INSTALL_FAILED",
            )
        finally:
            with self._lock:
                self._active_downloads.pop(task_id, None)
                self._install_tasks.pop(task_id, None)

    def uninstall_version(self, version_id: Any, game_path: Any) -> None:
        """
        从指定 Minecraft 目录卸载版本。

        :param version_id: Minecraft 版本或实例标识
        :param game_path: Minecraft 游戏根目录
        """
        name = self._normalize_version_name(version_id)
        root = self._normalize_game_path(game_path) / "versions"
        target = (root / name).resolve(strict=False)
        self.logger.debug("卸载实例: version=%s, path=%s", name, target)
        if target.parent != root.resolve(strict=False):
            raise GameServiceError("实例目录超出允许范围", "INVALID_VERSION_PATH")
        if not target.exists():
            raise GameServiceError("要卸载的实例不存在", "VERSION_NOT_FOUND")
        try:
            shutil.rmtree(target)
        except OSError as exc:
            raise GameServiceError(f"卸载实例失败: {exc}", "VERSION_UNINSTALL_FAILED") from exc
