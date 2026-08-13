from pathlib import Path
from time import sleep
from uuid import uuid4

_WINDOWS_REPLACE_RETRY_DELAYS = (0.02, 0.05, 0.1, 0.2)


def atomic_write_bytes(path: str | Path, data: bytes) -> None:
    """
    Atomically replace a file using a temporary sibling.

    :param path: 需要处理的文件或目录路径
    :param data: 需要处理或持久化的数据
    """
    destination = Path(path)
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary = destination.with_name(f".{destination.name}.{uuid4().hex}.tmp")
    try:
        temporary.write_bytes(data)
        for delay in (*_WINDOWS_REPLACE_RETRY_DELAYS, None):
            try:
                temporary.replace(destination)
                break
            except PermissionError:
                if delay is None:
                    raise
                # Windows 上杀毒软件、索引器或另一条刚结束的替换操作可能短暂占用目标。
                # 临时文件仍在同一目录，重试不会破坏原子替换语义。
                sleep(delay)
    finally:
        temporary.unlink(missing_ok=True)


def atomic_write_text(path: str | Path, data: str, encoding: str = "utf-8") -> None:
    atomic_write_bytes(path, data.encode(encoding))


__all__ = ["atomic_write_bytes", "atomic_write_text"]
