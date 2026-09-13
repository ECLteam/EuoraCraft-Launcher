# ============================================================
# EuoraCraft Launcher
# ECLTeam © 2026 GPL-3.0 License
# https://github.com/ECLTeam/EuoraCraft-Launcher
#
# 文件作用：极简 NBT 读写实现，替代 nbtlib 以去除 numpy 依赖。
#
# 公开接口：
#   - class Byte
#       - unpack(json=…) -> int
#   - class Short
#       - unpack(json=…) -> int
#   - class Int
#       - unpack(json=…) -> int
#   - class Long
#       - unpack(json=…) -> int
#   - class Float
#       - unpack(json=…) -> float
#   - class Double
#       - unpack(json=…) -> float
#   - class String
#       - unpack(json=…) -> str
#   - class ByteArray
#       - unpack(json=…) -> list[int] | bytes
#   - class IntArray
#       - unpack(json=…) -> list[int]
#   - class LongArray
#       - unpack(json=…) -> list[int]
#   - class List
#       - unpack(json=…) -> list[Any]
#   - class Compound
#       - unpack(json=…) -> dict[str, Any]
#   - class File — 根 NBT 文档，提供 save 与 load 入口。
#       - save(path, gzipped=…) -> None
#   - load(path) -> File — 从文件读取 NBT 文档，自动识别 gzip 压缩。
# ============================================================

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


class NbtTagIds:
    """
    Minecraft NBT 格式定义的标签编号。

    编号与二进制协议固定对应，读写路径共用此表以保持序列化兼容。
    """

    end = 0
    byte = 1
    short = 2
    integer = 3
    long = 4
    float = 5
    double = 6
    byte_array = 7
    string = 8
    list = 9
    compound = 10
    int_array = 11
    long_array = 12


class NbtParserPolicy:
    """
    NBT 二进制解析的资源限制。

    限制嵌套深度，防止恶意构造的存档数据耗尽调用栈或内存。
    """

    max_depth = 512


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
    _id = NbtTagIds.byte

    def unpack(self, json: bool = False) -> int:
        return int(self)


class Short(int, _Tag):
    _id = NbtTagIds.short

    def unpack(self, json: bool = False) -> int:
        return int(self)


class Int(int, _Tag):
    _id = NbtTagIds.integer

    def unpack(self, json: bool = False) -> int:
        return int(self)


class Long(int, _Tag):
    _id = NbtTagIds.long

    def unpack(self, json: bool = False) -> int:
        return int(self)


class Float(float, _Tag):
    _id = NbtTagIds.float

    def unpack(self, json: bool = False) -> float:
        return float(self)


class Double(float, _Tag):
    _id = NbtTagIds.double

    def unpack(self, json: bool = False) -> float:
        return float(self)


class String(str, _Tag):
    _id = NbtTagIds.string

    def unpack(self, json: bool = False) -> str:
        return str(self)


class ByteArray(bytes, _Tag):
    _id = NbtTagIds.byte_array

    def unpack(self, json: bool = False) -> list[int] | bytes:
        return list(self) if json else bytes(self)


class IntArray(list, _Tag):
    _id = NbtTagIds.int_array

    def unpack(self, json: bool = False) -> list[int]:
        return [int(item) for item in self]


class LongArray(list, _Tag):
    _id = NbtTagIds.long_array

    def unpack(self, json: bool = False) -> list[int]:
        return [int(item) for item in self]


class List(list, _Tag):
    _id = NbtTagIds.list
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
    _id = NbtTagIds.compound

    def unpack(self, json: bool = False) -> dict[str, Any]:
        return {key: value.unpack(json) if hasattr(value, "unpack") else value for key, value in self.items()}


class File(Compound):
    """
    根 NBT 文档，提供 save 与 load 入口。
    """

    def __init__(self, value: dict | None = None, gzipped: bool = False) -> None:
        super().__init__(value or {})
        self._gzipped = gzipped

    def save(self, path: Path | str, gzipped: bool | None = None) -> None:
        data = _serialize(self)
        if self._gzipped if gzipped is None else gzipped:
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


class NbtTypeRegistry:
    """
    NBT 标签编号到 Python 标签类型的映射。

    列表解析通过本注册表恢复元素类型，保持空列表和具名标签的语义。
    """

    tag_classes: dict[int, type[_Tag]] = {
        NbtTagIds.byte: Byte,
        NbtTagIds.short: Short,
        NbtTagIds.integer: Int,
        NbtTagIds.long: Long,
        NbtTagIds.float: Float,
        NbtTagIds.double: Double,
        NbtTagIds.byte_array: ByteArray,
        NbtTagIds.string: String,
        NbtTagIds.list: List,
        NbtTagIds.compound: Compound,
        NbtTagIds.int_array: IntArray,
        NbtTagIds.long_array: LongArray,
    }


def _read_string(buffer: io.BytesIO) -> str:
    length = struct.unpack(">H", _read_exactly(buffer, 2))[0]
    return _read_exactly(buffer, length).decode("utf-8")


def _read_exactly(buffer: io.BytesIO, count: int) -> bytes:
    # 按预期长度读取，数据不足时抛出可识别的错误而非交给 struct 报晦涩异常。
    data = buffer.read(count)
    if len(data) != count:
        raise ValueError("NBT 数据不完整")
    return data


def _parse_byte(buffer: io.BytesIO) -> Byte:
    return Byte(struct.unpack(">b", _read_exactly(buffer, 1))[0])


def _parse_short(buffer: io.BytesIO) -> Short:
    return Short(struct.unpack(">h", _read_exactly(buffer, 2))[0])


def _parse_int(buffer: io.BytesIO) -> Int:
    return Int(struct.unpack(">i", _read_exactly(buffer, 4))[0])


def _parse_long(buffer: io.BytesIO) -> Long:
    return Long(struct.unpack(">q", _read_exactly(buffer, 8))[0])


def _parse_float(buffer: io.BytesIO) -> Float:
    return Float(struct.unpack(">f", _read_exactly(buffer, 4))[0])


def _parse_double(buffer: io.BytesIO) -> Double:
    return Double(struct.unpack(">d", _read_exactly(buffer, 8))[0])


def _parse_byte_array(buffer: io.BytesIO) -> ByteArray:
    length = struct.unpack(">i", _read_exactly(buffer, 4))[0]
    if length < 0:
        raise ValueError("NBT 数组长度非法")
    return ByteArray(_read_exactly(buffer, length))


def _parse_string(buffer: io.BytesIO) -> String:
    return String(_read_string(buffer))


def _parse_list(buffer: io.BytesIO, _depth: int = 0) -> List:
    element_id = struct.unpack(">b", _read_exactly(buffer, 1))[0]
    length = struct.unpack(">i", _read_exactly(buffer, 4))[0]
    if length < 0:
        raise ValueError("NBT 数组长度非法")
    result = List()
    result._element_type = NbtTypeRegistry.tag_classes.get(element_id)
    for _ in range(length):
        result.append(_parse_payload(buffer, element_id, _depth + 1))
    return result


def _parse_int_array(buffer: io.BytesIO) -> IntArray:
    length = struct.unpack(">i", _read_exactly(buffer, 4))[0]
    if length < 0:
        raise ValueError("NBT 数组长度非法")
    return IntArray(struct.unpack(f">{length}i", _read_exactly(buffer, 4 * length)))


def _parse_long_array(buffer: io.BytesIO) -> LongArray:
    length = struct.unpack(">i", _read_exactly(buffer, 4))[0]
    if length < 0:
        raise ValueError("NBT 数组长度非法")
    return LongArray(struct.unpack(f">{length}q", _read_exactly(buffer, 8 * length)))


def _parse_compound(buffer: io.BytesIO, _depth: int = 0) -> Compound:
    result = Compound()
    while True:
        child_id = struct.unpack(">b", _read_exactly(buffer, 1))[0]
        if child_id == NbtTagIds.end:
            break
        name = _read_string(buffer)
        result[name] = _parse_payload(buffer, child_id, _depth + 1)
    return result


class NbtParserRegistry:
    """
    NBT 标签编号到二进制载荷解析函数的映射。

    递归容器标签会在调用时额外接收当前嵌套深度。
    """

    parsers: dict[int, Any] = {
        NbtTagIds.byte: _parse_byte,
        NbtTagIds.short: _parse_short,
        NbtTagIds.integer: _parse_int,
        NbtTagIds.long: _parse_long,
        NbtTagIds.float: _parse_float,
        NbtTagIds.double: _parse_double,
        NbtTagIds.byte_array: _parse_byte_array,
        NbtTagIds.string: _parse_string,
        NbtTagIds.list: _parse_list,
        NbtTagIds.compound: _parse_compound,
        NbtTagIds.int_array: _parse_int_array,
        NbtTagIds.long_array: _parse_long_array,
    }


def _parse_payload(buffer: io.BytesIO, tag_id: int, depth: int = 0) -> Any:
    if depth > NbtParserPolicy.max_depth:
        raise ValueError("NBT 嵌套层级过深")
    parser = NbtParserRegistry.parsers.get(tag_id)
    if parser is None:
        raise ValueError(f"未知 NBT 标签类型：{tag_id}")
    # 只有会递归的容器标签需要接收深度参数。
    if tag_id in (NbtTagIds.list, NbtTagIds.compound):
        return parser(buffer, depth)
    return parser(buffer)


def _tag_id(value: Any) -> int:
    if isinstance(value, _Tag):
        return value._id
    if isinstance(value, bool):
        return NbtTagIds.byte
    if isinstance(value, int):
        return NbtTagIds.integer
    if isinstance(value, float):
        return NbtTagIds.double
    if isinstance(value, str):
        return NbtTagIds.string
    if isinstance(value, (list, tuple)):
        return NbtTagIds.list
    if isinstance(value, dict):
        return NbtTagIds.compound
    if isinstance(value, bytes):
        return NbtTagIds.byte_array
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
    buffer.write(struct.pack(">b", NbtTagIds.end))


class NbtWriterRegistry:
    """
    NBT 标签编号到二进制载荷写入函数的映射。

    写入函数与解析注册表共用标签编号，保证序列化格式可逆。
    """

    writers: dict[int, Any] = {
        NbtTagIds.byte: _write_byte,
        NbtTagIds.short: _write_short,
        NbtTagIds.integer: _write_int,
        NbtTagIds.long: _write_long,
        NbtTagIds.float: _write_float,
        NbtTagIds.double: _write_double,
        NbtTagIds.byte_array: _write_byte_array,
        NbtTagIds.string: _write_string_tag,
        NbtTagIds.list: _write_list,
        NbtTagIds.compound: _write_compound,
        NbtTagIds.int_array: _write_int_array,
        NbtTagIds.long_array: _write_long_array,
    }


def _write_payload(buffer: io.BytesIO, value: Any) -> None:
    NbtWriterRegistry.writers[_tag_id(value)](buffer, value)


def _element_type_id(value: List) -> int:
    element_type = getattr(value, "_element_type", None)
    return element_type._id if element_type is not None else NbtTagIds.end


def _serialize(root: Compound) -> bytes:
    buffer = io.BytesIO()
    buffer.write(struct.pack(">b", NbtTagIds.compound))
    _write_string(buffer, "")
    _write_payload(buffer, root)
    return buffer.getvalue()


__all__ = [
    "Byte",
    "ByteArray",
    "Compound",
    "Double",
    "File",
    "Float",
    "Int",
    "IntArray",
    "List",
    "Long",
    "LongArray",
    "Short",
    "String",
    "load",
]
