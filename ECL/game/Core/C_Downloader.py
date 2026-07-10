from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Callable, List, Tuple, Optional
from pathlib import Path
import threading
import time
import os
import sys
import httpx
import hashlib

# ---------- 全局速率限制器 ----------
class GlobalRateLimiter:
    """线程安全的令牌桶限速器，所有下载线程共享"""
    def __init__(self, rate_bytes_per_sec: float = 0):
        self.rate = rate_bytes_per_sec
        self.allowance = 0.0
        self.last_check = time.monotonic()
        self.lock = threading.Lock()

    def set_rate(self, rate_bytes_per_sec: float):
        with self.lock:
            self.rate = rate_bytes_per_sec
            if self.rate <= 0:
                self.allowance = 0

    def acquire(self, amount: int):
        if self.rate <= 0:
            return
        with self.lock:
            now = time.monotonic()
            elapsed = now - self.last_check
            self.allowance += elapsed * self.rate
            self.last_check = now
            if self.allowance < amount:
                wait = (amount - self.allowance) / self.rate
                time.sleep(wait)
                self.allowance = 0
                self.last_check = time.monotonic()
            else:
                self.allowance -= amount


class Downloader:
    def __init__(
        self,
        max_retries: int = 3,
        chunk_size: int = 512 * 1024,
        user_agent: str = "Euora Craft Launcher",
        parallel_download: bool = True,
        parallel_threads: int = 8,
        parallel_threshold: int = 10 * 1024 * 1024,
        rate_limit: float = 0,
        temp_dir: Optional[str | Path] = None,
    ):
        self.download_status = True
        self.__download_total: List[Tuple[str, str]] = []
        self.__download_done: List[str] = []
        self.output_progress = self.__default_output_progress
        self.output_log: Callable[[str], None] = print
        self.lock = threading.Lock()
        self.max_retries = max_retries
        self.chunk_size = chunk_size
        self.parallel_download = parallel_download
        self.parallel_threads = parallel_threads
        self.parallel_threshold = parallel_threshold

        self.event_callback: Optional[Callable[[dict], None]] = None

        self._file_progress_callback: Optional[Callable[[str, int, int], None]] = None
        self._total_progress_callback: Optional[Callable[[int, int, int, int], None]] = None

        self.stop_event = threading.Event()
        self.rate_limiter = GlobalRateLimiter(rate_limit)

        self.temp_dir = Path(temp_dir) if temp_dir else None
        if self.temp_dir:
            self.temp_dir.mkdir(parents=True, exist_ok=True)

        self.client = httpx.Client(
            http2=True,
            timeout=httpx.Timeout(30.0, connect=10.0),
            follow_redirects=True,
            limits=httpx.Limits(max_keepalive_connections=parallel_threads * 2,
                                max_connections=parallel_threads * 2),
            headers={"User-Agent": user_agent}
        )

    # ---------- 公共 API ----------
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
            if set_status:
                self.stop_event.clear()
            else:
                self.stop_event.set()

    def cancel_all_downloads(self) -> None:
        self.set_download_status(False)

    def close(self) -> None:
        try:
            self.client.close()
        except Exception:
            pass

    def set_file_progress_callback(self, callback: Optional[Callable[[str, int, int], None]]) -> None:
        self._file_progress_callback = callback

    def set_total_progress_callback(self, callback: Optional[Callable[[int, int, int, int], None]]) -> None:
        self._total_progress_callback = callback

    def set_rate_limit(self, rate_bytes_per_sec: float):
        self.rate_limiter.set_rate(rate_bytes_per_sec)

    def cleanup_temp_files(self):
        if not self.temp_dir:
            return
        for tmp_file in self.temp_dir.glob("*.tmp"):
            try:
                tmp_file.unlink()
                self.output_log(f"清理临时文件: {tmp_file}")
            except Exception as e:
                self.output_log(f"清理临时文件失败 {tmp_file}: {e}")

    # ---------- 内部方法 ----------
    def __default_output_progress(self, total_files: list, downloaded_files: list):
        with self.lock:
            total = len(total_files)
            done = len(downloaded_files)
            if total > 0:
                print(f"下载进度: {done}/{total} ({done / total * 100:.1f}%)")

    def __get_file_size(self, url: str) -> Optional[int]:
        for attempt in range(self.max_retries):
            try:
                resp = self.client.head(url)
                resp.raise_for_status()
                content_length = resp.headers.get("content-length")
                if content_length:
                    return int(content_length)
                with self.client.stream("GET", url) as stream:
                    stream.raise_for_status()
                    content_length = stream.headers.get("content-length")
                    return int(content_length) if content_length else 0
            except (httpx.HTTPError, httpx.StreamError, OSError) as e:
                if attempt == self.max_retries - 1:
                    self.output_log(f"获取文件大小失败 {url}: {str(e)}")
                    return None
                time.sleep(2 ** attempt)
        return None

    def __preallocate_file(self, path: Path, size: int):
        try:
            # 使用 "w+b" 确保文件存在并截断至 size
            with open(path, "w+b") as f:
                f.truncate(size)
            if sys.platform != "win32":
                fd = os.open(path, os.O_RDWR)
                try:
                    os.posix_fallocate(fd, 0, size)
                except AttributeError:
                    pass
                finally:
                    os.close(fd)
        except Exception as e:
            self.output_log(f"预分配文件失败 {path}: {str(e)}")
            raise  # 上层捕获并回退

    def __download_range(self, url: str, start: int, end: int, temp_file: Path,
                         part_index: int, total_size: int, file_path: str) -> bool:
        headers = {"Range": f"bytes={start}-{end}"}
        for attempt in range(self.max_retries):
            if self.stop_event.is_set():
                return False
            try:
                with self.client.stream("GET", url, headers=headers) as resp:
                    resp.raise_for_status()
                    if resp.status_code != 206:
                        return False
                    with open(temp_file, "r+b") as f:
                        f.seek(start)
                        for chunk in resp.iter_bytes(chunk_size=self.chunk_size):
                            if self.stop_event.is_set():
                                return False
                            if chunk:
                                f.write(chunk)
                                self.rate_limiter.acquire(len(chunk))
                return True
            except FileNotFoundError:
                # 若预分配未创建文件，尝试创建并重试
                try:
                    with open(temp_file, "w+b") as f:
                        f.truncate(total_size)
                except Exception:
                    return False
                continue  # 重试本次下载
            except (httpx.HTTPError, httpx.StreamError, OSError) as e:
                if attempt == self.max_retries - 1:
                    self.output_log(f"分片 {part_index} 下载失败 {url}: {str(e)}")
                    return False
                time.sleep(2 ** attempt)
        return False

    def __download_parallel(self, url: str, file_path: Path, file_size: int, temp_path: Path) -> bool:
        min_part_size = 4 * 1024 * 1024
        part_count = min(self.parallel_threads, max(1, file_size // min_part_size))
        part_size = file_size // part_count
        parts = []
        for i in range(part_count):
            start = i * part_size
            end = start + part_size - 1
            if i == part_count - 1:
                end = file_size - 1
            parts.append((start, end, i))

        try:
            self.__preallocate_file(temp_path, file_size)
        except Exception:
            # 预分配失败，回退到流式下载
            return self.__download_stream(url, temp_path, 0) and self.__finalize_file(temp_path, file_path, file_size)

        with ThreadPoolExecutor(max_workers=len(parts)) as executor:
            futures = [
                executor.submit(
                    self.__download_range,
                    url, start, end, temp_path, idx, file_size, str(file_path)
                )
                for start, end, idx in parts
            ]
            for fut in as_completed(futures):
                if not fut.result():
                    return False
        if self._file_progress_callback:
            self._file_progress_callback(str(file_path), file_size, file_size)
        return True

    def __download_stream(self, url: str, file_path: Path, start_byte: int = 0) -> bool:
        headers = {}
        if start_byte > 0:
            headers["Range"] = f"bytes={start_byte}-"

        for attempt in range(self.max_retries):
            if self.stop_event.is_set():
                return False
            try:
                file_path.parent.mkdir(parents=True, exist_ok=True)
                mode = "ab" if start_byte > 0 else "wb"
                with self.client.stream("GET", url, headers=headers) as resp:
                    resp.raise_for_status()
                    if start_byte > 0 and resp.status_code != 206:
                        return False

                    total_size = None
                    if not start_byte:
                        cl = resp.headers.get("content-length")
                        if cl:
                            total_size = int(cl)
                    else:
                        total_size = self.__get_file_size(url)
                    if total_size is None:
                        total_size = 0

                    last_percent = -1
                    downloaded = start_byte
                    with open(file_path, mode) as f:
                        for chunk in resp.iter_bytes(chunk_size=self.chunk_size):
                            if self.stop_event.is_set():
                                return False
                            if chunk:
                                f.write(chunk)
                                downloaded += len(chunk)
                                self.rate_limiter.acquire(len(chunk))
                                if self._file_progress_callback and total_size > 0:
                                    percent = int(downloaded * 100 / total_size)
                                    if percent > last_percent:
                                        self._file_progress_callback(str(file_path), downloaded, total_size)
                                        last_percent = percent
                    if self._file_progress_callback and total_size > 0 and last_percent != 100:
                        self._file_progress_callback(str(file_path), total_size, total_size)
                return True
            except (httpx.HTTPError, httpx.StreamError, OSError) as e:
                if attempt == self.max_retries - 1:
                    self.output_log(f"流式下载失败 {url}: {str(e)}")
                    return False
                time.sleep(2 ** attempt)
        return False

    def __download_single_file(self, download_url: str, save_path: str) -> bool:
        save_file_path = Path(save_path)

        if self.temp_dir:
            abs_path = str(save_file_path.resolve())
            temp_name = hashlib.md5(abs_path.encode()).hexdigest() + ".tmp"
            temp_path = self.temp_dir / temp_name
        else:
            temp_path = save_file_path.with_name(save_file_path.name + ".tmp")

        try:
            save_file_path.parent.mkdir(parents=True, exist_ok=True)
        except Exception as e:
            self.output_log(f"创建目录失败: {e}")
            return False

        file_size = self.__get_file_size(download_url)
        if file_size is None:
            return self.__download_stream(download_url, temp_path) and self.__finalize_file(temp_path, save_file_path, 0)

        downloaded_size = 0
        if temp_path.exists():
            try:
                downloaded_size = temp_path.stat().st_size
                if downloaded_size >= file_size > 0:
                    temp_path.unlink(missing_ok=True)
                    downloaded_size = 0
            except Exception:
                temp_path.unlink(missing_ok=True)

        use_parallel = (
            self.parallel_download
            and file_size > self.parallel_threshold
            and downloaded_size == 0
        )

        if use_parallel:
            success = self.__download_parallel(download_url, save_file_path, file_size, temp_path)
        else:
            success = self.__download_stream(download_url, temp_path, downloaded_size)

        if not success:
            return False

        return self.__finalize_file(temp_path, save_file_path, file_size)

    def __finalize_file(self, temp_path: Path, target_path: Path, expected_size: int) -> bool:
        try:
            final_size = temp_path.stat().st_size
            if expected_size != 0 and final_size != expected_size:
                self.output_log(f"大小不匹配: {target_path} 期望 {expected_size} 实际 {final_size}")
                return False
        except Exception as e:
            self.output_log(f"验证失败: {e}")
            return False

        try:
            if target_path.exists():
                target_path.unlink(missing_ok=True)
            temp_path.rename(target_path)
            return True
        except Exception as e:
            self.output_log(f"重命名失败: {e}")
            return False

    def download_manager(self, download_list: List[Tuple[str, str]], max_threads: int) -> bool:
        if not download_list or max_threads <= 0:
            self.output_log("下载列表为空或线程数无效")
            return False

        self.output_log(f"开始下载 {len(download_list)} 个文件，并发线程 {max_threads}")

        with self.lock:
            self.__download_total = download_list
            self.__download_done.clear()
            self.stop_event.clear()
            self.download_status = True

        successful_downloads = 0
        with ThreadPoolExecutor(max_workers=max_threads) as executor:
            future_to_item = {
                executor.submit(self.__download_single_file, url, path): (url, path)
                for url, path in self.__download_total
            }
            for future in as_completed(future_to_item):
                if self.stop_event.is_set():
                    executor.shutdown(wait=False, cancel_futures=True)
                    return False
                url, path = future_to_item[future]
                try:
                    if future.result():
                        with self.lock:
                            self.__download_done.append(path)
                            successful_downloads += 1
                        self.output_progress(self.__download_total, self.__download_done)
                        self.output_log(f"成功: {path}")

                        if self.event_callback:
                            total = len(self.__download_total)
                            done = len(self.__download_done)
                            try:
                                self.event_callback({
                                    "type": "download_progress",
                                    "done": done,
                                    "total": total,
                                    "current_file": path,
                                })
                            except Exception as e:
                                self.output_log(f"事件回调异常: {e}")

                        if self._total_progress_callback:
                            with self.lock:
                                self._total_progress_callback(0, 0, successful_downloads, len(self.__download_total))
                    else:
                        self.output_log(f"失败: {path}")
                except Exception as e:
                    self.output_log(f"异常 {url}: {e}")

        total = len(self.__download_total)
        self.output_log(f"下载统计: {successful_downloads}/{total}")
        return successful_downloads == total

    def __del__(self):
        try:
            self.client.close()
        except:
            pass