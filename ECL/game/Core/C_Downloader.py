import threading
import time
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

import requests


class Downloader:
    def __init__(self, max_retries: int = 3, chunk_size: int = 8192, user_agent: str = "Euora Craft Launcher"):
        self.download_status = True
        self.__download_total: list[tuple[str, str]] = []
        self.__download_done: list[str] = []
        self.output_progress = self.__default_output_progress
        self.output_log: Callable[[str], None] = print
        self.event_callback: Callable[[dict], None] | None = None
        self.lock = threading.Lock()
        self.max_retries = max_retries
        self.chunk_size = chunk_size

        # 配置requests会话
        self.session = requests.Session()
        self.session.headers.update(
            {
                # "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
                "User-Agent": user_agent
            }
        )

    def close(self):
        self.session.close()

    def __default_output_progress(self, total_files: list, downloaded_files: list):
        with self.lock:
            total = len(total_files)
            done = len(downloaded_files)
            if total > 0:
                print(f"下载进度: {done}/{total} ({done / total * 100:.1f}%)")

    def set_output_progress(self, output_function: Callable[[list, list], None]) -> None:
        def safe_output(total: list, done: list):
            with self.lock:
                output_function(total, done)

        self.output_progress = safe_output

    def set_output_log(self, output_function: Callable[[str], None]) -> None:
        self.output_log = output_function

    def set_download_status(self, set_status: bool) -> None:
        with self.lock:
            self.download_status = set_status

    def __get_file_size(self, url: str) -> int | None:
        """获取文件大小，支持重试"""
        for attempt in range(self.max_retries):
            try:
                response = self.session.head(url, timeout=10, allow_redirects=True)
                response.raise_for_status()

                # 尝试从响应头获取文件大小
                content_length = response.headers.get("Content-Length")
                if content_length:
                    return int(content_length)

                # 如果HEAD请求没有Content-Length，尝试GET请求
                with self.session.get(url, stream=True, timeout=10) as response:
                    response.raise_for_status()
                    content_length = response.headers.get("Content-Length")
                    if content_length:
                        return int(content_length)
                return 0  # 未知大小，返回0

            except requests.exceptions.RequestException as e:
                if attempt == self.max_retries - 1:
                    self.output_log(f"获取文件大小失败 {url}: {e!s}")
                    return None
                time.sleep(2**attempt)
        return None

    def __download_stream(self, url: str, file_path: Path, start_byte: int = 0) -> bool:
        """流式下载文件"""
        for attempt in range(self.max_retries):
            try:
                headers = {}
                if start_byte > 0:
                    headers["Range"] = f"bytes={start_byte}-"

                # 确保父目录存在
                file_path.parent.mkdir(parents=True, exist_ok=True)

                with self.session.get(url, headers=headers, stream=True, timeout=30) as response:
                    response.raise_for_status()

                    # 检查是否支持断点续传
                    if start_byte > 0 and response.status_code != 206:
                        # self.output_log(f"服务器不支持断点续传: {url}")
                        return False

                    with file_path.open("ab" if start_byte > 0 else "wb") as f:
                        for chunk in response.iter_content(chunk_size=self.chunk_size):
                            # 检查下载状态
                            with self.lock:
                                if not self.download_status:
                                    return False

                            if chunk:
                                f.write(chunk)
                    return True

            except requests.exceptions.RequestException as e:
                if attempt == self.max_retries - 1:
                    self.output_log(f"下载失败 {url}: {e!s}")
                    return False
                time.sleep(2**attempt)
            except OSError as e:
                self.output_log(f"文件写入失败 {file_path}: {e!s}")
                return False
        return False

    def __download_single_file(self, download_url: str, save_path: str) -> bool:
        """下载单个文件"""
        save_file_path = Path(save_path)
        temp_path = save_file_path.with_name(save_file_path.name + ".tmp")

        # self.output_log(f"开始下载: {download_url} -> {save_path}")

        # 1. 确保父目录存在
        try:
            save_file_path.parent.mkdir(parents=True, exist_ok=True)
            # self.output_log(f"创建目录: {save_file_path.parent}")
        except Exception as e:
            self.output_log(f"创建目录失败 {save_file_path.parent}: {e!s}")
            return False

        # 2. 获取文件大小（如果失败，尝试直接下载）
        file_size = self.__get_file_size(download_url)
        if file_size is None:
            # self.output_log(f"无法获取文件大小，尝试直接下载: {download_url}")
            # 直接下载，不检查大小
            return self.__download_stream(download_url, save_file_path)

        # self.output_log(f"文件大小: {file_size} bytes")

        # 3. 检查是否已部分下载
        downloaded_size = 0
        if temp_path.exists():
            try:
                downloaded_size = temp_path.stat().st_size
                # self.output_log(f"发现未完成下载，已下载: {downloaded_size} bytes")

                # 如果临时文件大小超过文件大小，重新下载
                if downloaded_size >= file_size > 0:
                    # self.output_log("临时文件已损坏，重新下载")
                    temp_path.unlink(missing_ok=True)
                    downloaded_size = 0
            except Exception as e:
                self.output_log(f"检查临时文件失败: {e!s}")
                temp_path.unlink(missing_ok=True)
                downloaded_size = 0

        # 4. 下载文件
        success = self.__download_stream(download_url, temp_path, downloaded_size)

        if not success:
            # self.output_log(f"下载失败: {download_url}")
            # 保留临时文件以便续传
            return False

        # 5. 验证文件大小
        try:
            final_size = temp_path.stat().st_size
            if 0 < file_size != final_size:
                self.output_log(f"文件大小不匹配: 期望 {file_size}, 实际 {final_size}")
                return False
        except Exception as e:
            self.output_log(f"验证文件大小失败: {e!s}")

        # 6. 重命名临时文件
        try:
            # 如果目标文件已存在，先删除
            if save_file_path.exists():
                save_file_path.unlink(missing_ok=True)

            temp_path.rename(save_file_path)
            # self.output_log(f"下载完成: {save_path}")
            return True
        except Exception as e:
            self.output_log(f"重命名文件失败 {save_path}: {e!s}")
            return False

    def cancel_all_downloads(self) -> None:
        with self.lock:
            self.download_status = False

    def download_manager(self, download_list: list[tuple[str, str]], max_threads: int) -> bool:
        """下载管理器"""
        if not download_list or max_threads <= 0:
            self.output_log("下载列表为空或线程数无效")
            return False

        with self.lock:
            self.download_status = True  # 每次启动下载时重置状态

        self.output_log(f"开始下载 {len(download_list)} 个文件，使用 {max_threads} 个线程")

        with self.lock:
            self.__download_total = download_list
            self.__download_done.clear()

        # 使用线程池
        successful_downloads = 0
        try:
            with ThreadPoolExecutor(max_workers=max_threads) as executor:
                # 提交所有任务
                future_to_url = {
                    executor.submit(self.__download_single_file, url, save_path): (url, save_path)
                    for url, save_path in self.__download_total
                }

                # 处理完成的任务
                for future in as_completed(future_to_url):
                    url, save_path = future_to_url[future]
                    try:
                        success = future.result()
                        if success:
                            with self.lock:
                                self.__download_done.append(save_path)
                                successful_downloads += 1

                            # 更新进度
                            self.output_progress(self.__download_total, self.__download_done)
                            self.output_log(f"成功下载: {save_path}")

                            # 事件回调
                            if self.event_callback:
                                total = len(self.__download_total)
                                done = len(self.__download_done)
                                try:
                                    self.event_callback({
                                        "type": "download_progress",
                                        "done": done,
                                        "total": total,
                                        "current_file": save_path,
                                    })
                                except Exception as e:
                                    print(f"事件回调异常: {e}")
                        else:
                            self.output_log(f"失败下载: {save_path}")

                    except Exception as e:
                        self.output_log(f"任务执行异常 {url}: {e!s}")

        except Exception as e:
            self.output_log(f"下载管理器异常: {e!s}")

        # 检查是否所有文件都下载完成
        total_files = len(self.__download_total)
        downloaded_files = successful_downloads

        self.output_log(f"下载统计: {downloaded_files}/{total_files}")

        with self.lock:
            return downloaded_files == total_files
