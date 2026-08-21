"""极简 NBT 读写实现，替代 nbtlib 以去除 numpy 依赖。

仅覆盖启动器实际用到的标签类型与读写语义，格式遵循 Minecraft NBT 规范。
"""

from __future__ import annotations

import gzip
import io
import struct
from collections.abc import Iterable
from pathlib import Path
from typing import Any

_TAG_END = 0
_TAG_BYTE = 1
_TAG_SHORT = 2
_TAG_INT = 3
_TAG_LONG = 4
_TAG_FLOAT = 5
_TAG_DOUBLE = 6
_TAG_BYTE_ARRAY = 7
_TAG_STRING = 8
_TAG_LIST = 9
_TAG_COMPOUND = 10
_TAG_INT_ARRAY = 11
_TAG_LONG_ARRAY = 12


class _Tag:
    """
    NBT 标签基类，子类继承对应 Python 内置类型以复用其操作。
    """

    _id: int

    def unpack(self, json: bool = False) -> Any:
        """
        转换为普通 Python 值。
        """
        return self


class Byte(int, _Tag):
    _id = _TAG_BYTE

    def unpack(self, json: bool = False) -> int:
        return int(self)


class Short(int, _Tag):
    _id = _TAG_SHORT

    def unpack(self, json: bool = False) -> int:
        return int(self)


class Int(int, _Tag):
    _id = _TAG_INT

    def unpack(self, json: bool = False) -> int:
        return int(self)


class Long(int, _Tag):
    _id = _TAG_LONG

    def unpack(self, json: bool = False) -> int:
        return int(self)


class Float(float, _Tag):
    _id = _TAG_FLOAT

    def unpack(self, json: bool = False) -> float:
        return float(self)


class Double(float, _Tag):
    _id = _TAG_DOUBLE

    def unpack(self, json: bool = False) -> float:
        return float(self)


class String(str, _Tag):
    _id = _TAG_STRING

    def unpack(self, json: bool = False) -> str:
        return str(self)


class ByteArray(bytes, _Tag):
    _id = _TAG_BYTE_ARRAY

    def unpack(self, json: bool = False) -> list[int] | bytes:
        return list(self) if json else bytes(self)


class IntArray(list, _Tag):
    _id = _TAG_INT_ARRAY

    def unpack(self, json: bool = False) -> list[int]:
        return [int(item) for item in self]


class LongArray(list, _Tag):
    _id = _TAG_LONG_ARRAY

    def unpack(self, json: bool = False) -> list[int]:
        return [int(item) for item in self]


class List(list, _Tag):
    _id = _TAG_LIST
    _element_type: type[_Tag] | None = None

    def __init__(self, values: Iterable[Any] = ()) -> None:
        super().__init__()
        element_type = self._element_type
        for value in values:
            if element_type is not None and not isinstance(value, _Tag):
                value = element_type(value)
            self.append(value)

    def __class_getitem__(cls, item: type[_Tag]) -> type[List]:
        return type(f"List[{item.__name__}]", (cls,), {"_element_type": item})

    def unpack(self, json: bool = False) -> list[Any]:
        return [item.unpack(json) if hasattr(item, "unpack") else item for item in self]


class Compound(dict, _Tag):
    _id = _TAG_COMPOUND

    def unpack(self, json: bool = False) -> dict[str, Any]:
        return {key: value.unpack(json) if hasattr(value, "unpack") else value for key, value in self.items()}

class File(Compound):
    """
    根 NBT 文档，提供 save 与 load 入口。
    """

    def __init__(self, value: dict | None = None, gzipped: bool = False) -> None:
        super().__init__(value or {})

    def save(self, path: Path | str, gzipped: bool = True) -> None:
        data = _serialize(self)
        if gzipped:
            data = gzip.compress(data)
        Path(path).write_bytes(data)

def load(path: Path | str) -> File:
    """
    从文件读取 NBT 文档，自动识别 gzip 压缩。
    """
    data = Path(path).read_bytes()
    if data[:2] == b"\x1f\x8b":
        data = gzip.decompress(data)
    buffer = io.BytesIO(data)
    root_id = struct.unpack(">b", buffer.read(1))[0]
    _read_string(buffer)
    root = _parse_payload(buffer, root_id)
    if not isinstance(root, Compound):
        raise ValueError("NBT 根节点不是 Compound")
    return File(root)


_TAG_CLASSES: dict[int, type[_Tag]] = {
    _TAG_BYTE: Byte,
    _TAG_SHORT: Short,
    _TAG_INT: Int,
    _TAG_LONG: Long,
    _TAG_FLOAT: Float,
    _TAG_DOUBLE: Double,
    _TAG_BYTE_ARRAY: ByteArray,
    _TAG_STRING: String,
    _TAG_LIST: List,
    _TAG_COMPOUND: Compound,
    _TAG_INT_ARRAY: IntArray,
    _TAG_LONG_ARRAY: LongArray,
}


def _read_string(buffer: io.BytesIO) -> str:
    length = struct.unpack(">H", buffer.read(2))[0]
    return buffer.read(length).decode("utf-8")


def _parse_byte(buffer: io.BytesIO) -> Byte:
    return Byte(struct.unpack(">b", buffer.read(1))[0])


def _parse_short(buffer: io.BytesIO) -> Short:
    return Short(struct.unpack(">h", buffer.read(2))[0])


def _parse_int(buffer: io.BytesIO) -> Int:
    return Int(struct.unpack(">i", buffer.read(4))[0])


def _parse_long(buffer: io.BytesIO) -> Long:
    return Long(struct.unpack(">q", buffer.read(8))[0])


def _parse_float(buffer: io.BytesIO) -> Float:
    return Float(struct.unpack(">f", buffer.read(4))[0])


def _parse_double(buffer: io.BytesIO) -> Double:
    return Double(struct.unpack(">d", buffer.read(8))[0])


def _parse_byte_array(buffer: io.BytesIO) -> ByteArray:
    length = struct.unpack(">i", buffer.read(4))[0]
    return ByteArray(buffer.read(length))


def _parse_string(buffer: io.BytesIO) -> String:
    return String(_read_string(buffer))


def _parse_list(buffer: io.BytesIO) -> List:
    element_id = struct.unpack(">b", buffer.read(1))[0]
    length = struct.unpack(">i", buffer.read(4))[0]
    result = List()
    result._element_type = _TAG_CLASSES.get(element_id)
    for _ in range(length):
        result.append(_parse_payload(buffer, element_id))
    return result


def _parse_int_array(buffer: io.BytesIO) -> IntArray:
    length = struct.unpack(">i", buffer.read(4))[0]
    return IntArray(struct.unpack(f">{length}i", buffer.read(4 * length)))


def _parse_long_array(buffer: io.BytesIO) -> LongArray:
    length = struct.unpack(">i", buffer.read(4))[0]
    return LongArray(struct.unpack(f">{length}q", buffer.read(8 * length)))


def _parse_compound(buffer: io.BytesIO) -> Compound:
    result = Compound()
    while True:
        child_id = struct.unpack(">b", buffer.read(1))[0]
        if child_id == _TAG_END:
            break
        name = _read_string(buffer)
        result[name] = _parse_payload(buffer, child_id)
    return result


_PARSERS: dict[int, Any] = {
    _TAG_BYTE: _parse_byte,
    _TAG_SHORT: _parse_short,
    _TAG_INT: _parse_int,
    _TAG_LONG: _parse_long,
    _TAG_FLOAT: _parse_float,
    _TAG_DOUBLE: _parse_double,
    _TAG_BYTE_ARRAY: _parse_byte_array,
    _TAG_STRING: _parse_string,
    _TAG_LIST: _parse_list,
    _TAG_COMPOUND: _parse_compound,
    _TAG_INT_ARRAY: _parse_int_array,
    _TAG_LONG_ARRAY: _parse_long_array,
}


def _parse_payload(buffer: io.BytesIO, tag_id: int) -> Any:
    parser = _PARSERS.get(tag_id)
    if parser is None:
        raise ValueError(f"未知 NBT 标签类型：{tag_id}")
    return parser(buffer)


def _tag_id(value: Any) -> int:
    if isinstance(value, _Tag):
        return value._id
    if isinstance(value, bool):
        return _TAG_BYTE
    if isinstance(value, int):
        return _TAG_INT
    if isinstance(value, float):
        return _TAG_DOUBLE
    if isinstance(value, str):
        return _TAG_STRING
    if isinstance(value, (list, tuple)):
        return _TAG_LIST
    if isinstance(value, dict):
        return _TAG_COMPOUND
    if isinstance(value, bytes):
        return _TAG_BYTE_ARRAY
    raise TypeError(f"无法序列化 NBT 值：{type(value).__name__}")


def _write_string(buffer: io.BytesIO, value: str) -> None:
    encoded = value.encode("utf-8")
    buffer.write(struct.pack(">H", len(encoded)))
    buffer.write(encoded)


def _write_byte(buffer: io.BytesIO, value: Any) -> None:
    buffer.write(struct.pack(">b", int(value)))


def _write_short(buffer: io.BytesIO, value: Any) -> None:
    buffer.write(struct.pack(">h", int(value)))


def _write_int(buffer: io.BytesIO, value: Any) -> None:
    buffer.write(struct.pack(">i", int(value)))


def _write_long(buffer: io.BytesIO, value: Any) -> None:
    buffer.write(struct.pack(">q", int(value)))


def _write_float(buffer: io.BytesIO, value: Any) -> None:
    buffer.write(struct.pack(">f", float(value)))


def _write_double(buffer: io.BytesIO, value: Any) -> None:
    buffer.write(struct.pack(">d", float(value)))


def _write_byte_array(buffer: io.BytesIO, value: Any) -> None:
    buffer.write(struct.pack(">i", len(value)))
    buffer.write(bytes(value))


def _write_string_tag(buffer: io.BytesIO, value: Any) -> None:
    _write_string(buffer, str(value))


def _write_list(buffer: io.BytesIO, value: Any) -> None:
    items = list(value)
    element_id = _tag_id(items[0]) if items else _element_type_id(value)
    buffer.write(struct.pack(">b", element_id))
    buffer.write(struct.pack(">i", len(items)))
    for item in items:
        _write_payload(buffer, item)


def _write_int_array(buffer: io.BytesIO, value: Any) -> None:
    buffer.write(struct.pack(">i", len(value)))
    for item in value:
        buffer.write(struct.pack(">i", int(item)))


def _write_long_array(buffer: io.BytesIO, value: Any) -> None:
    buffer.write(struct.pack(">i", len(value)))
    for item in value:
        buffer.write(struct.pack(">q", int(item)))


def _write_compound(buffer: io.BytesIO, value: Any) -> None:
    for key, item in value.items():
        buffer.write(struct.pack(">b", _tag_id(item)))
        _write_string(buffer, key)
        _write_payload(buffer, item)
    buffer.write(struct.pack(">b", _TAG_END))


_WRITERS: dict[int, Any] = {
    _TAG_BYTE: _write_byte,
    _TAG_SHORT: _write_short,
    _TAG_INT: _write_int,
    _TAG_LONG: _write_long,
    _TAG_FLOAT: _write_float,
    _TAG_DOUBLE: _write_double,
    _TAG_BYTE_ARRAY: _write_byte_array,
    _TAG_STRING: _write_string_tag,
    _TAG_LIST: _write_list,
    _TAG_COMPOUND: _write_compound,
    _TAG_INT_ARRAY: _write_int_array,
    _TAG_LONG_ARRAY: _write_long_array,
}


def _write_payload(buffer: io.BytesIO, value: Any) -> None:
    _WRITERS[_tag_id(value)](buffer, value)


def _element_type_id(value: List) -> int:
    element_type = getattr(value, "_element_type", None)
    return element_type._id if element_type is not None else _TAG_END


def _serialize(root: Compound) -> bytes:
    buffer = io.BytesIO()
    buffer.write(struct.pack(">b", _TAG_COMPOUND))
    _write_string(buffer, "")
    _write_payload(buffer, root)
    return buffer.getvalue()


__all__ = ["Byte", "ByteArray", "Compound", "Double", "File", "Float", "Int", "IntArray", "List", "Long", "LongArray", "Short", "String", "load"]
