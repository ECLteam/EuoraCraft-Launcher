from pathlib import Path
from uuid import uuid4


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
        temporary.replace(destination)
    finally:
        temporary.unlink(missing_ok=True)


def atomic_write_text(path: str | Path, data: str, encoding: str = "utf-8") -> None:
    atomic_write_bytes(path, data.encode(encoding))


__all__ = ["atomic_write_bytes", "atomic_write_text"]
