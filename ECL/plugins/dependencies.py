"""插件依赖解析与拓扑排序。"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from packaging.specifiers import InvalidSpecifier, SpecifierSet
from packaging.version import InvalidVersion, Version


@dataclass
class DependencyRequirement:
    """
    单个插件依赖需求。
    """

    name: str
    specifier: SpecifierSet = field(default_factory=lambda: SpecifierSet(""))
    optional: bool = False

    @property
    def version_constraint(self) -> str:
        """返回该依赖的版本约束表达式。"""
        return str(self.specifier) or "*"


def parse_dependency(name: str, value: Any) -> DependencyRequirement | None:
    """
    解析 plugin.json 中 dependencies 的单个条目。
    支持字符串约束或 {"version": ..., "optional": true} 对象。
    :param name: 被依赖插件名
    :param value: 依赖声明值
    :return: 解析后的需求，格式错误时返回 None
    """
    constraint = ""
    optional = False
    if isinstance(value, str):
        constraint = value
    elif isinstance(value, dict):
        constraint = value.get("version", "")
        optional = bool(value.get("optional", False))
    else:
        return None
    if constraint in ("", "*"):
        return DependencyRequirement(name, SpecifierSet(""), optional)
    try:
        return DependencyRequirement(name, SpecifierSet(constraint), optional)
    except InvalidSpecifier:
        return None


@dataclass
class PluginDependencyInfo:
    """
    解析后的插件依赖信息。
    """

    name: str
    version: str
    dependencies: list[DependencyRequirement] = field(default_factory=list)
    is_system: bool = False


@dataclass
class DependencyResolution:
    """
    依赖解析结果。
    """

    load_order: list[str] = field(default_factory=list)
    errors: dict[str, str] = field(default_factory=dict)
    skipped: set[str] = field(default_factory=set)


def parse_version(version: str) -> Version | None:
    """
    解析版本字符串，非法版本返回 None。

    :param version: 待解析的版本字符串
    :return: 解析后的版本对象，无法解析时返回 None
    """
    try:
        return Version(version)
    except InvalidVersion:
        return None


def _detect_cycles(graph: dict[str, set[str]]) -> list[str] | None:
    """
    使用 DFS 检测有向图中的环，返回环上任意一个节点或 None。
    """
    white, gray, black = 0, 1, 2
    color = dict.fromkeys(graph, white)
    parent: dict[str, str | None] = dict.fromkeys(graph)

    def dfs(node: str) -> list[str] | None:
        color[node] = gray
        for neighbor in graph.get(node, set()):
            if color.get(neighbor, white) == gray:
                cycle = [neighbor]
                current = node
                while current != neighbor and current is not None:
                    cycle.append(current)
                    current = parent.get(current)
                cycle.reverse()
                return cycle
            if color.get(neighbor, white) == white:
                parent[neighbor] = node
                result = dfs(neighbor)
                if result is not None:
                    return result
        color[node] = black
        return None

    for node in graph:
        if color[node] == white:
            cycle = dfs(node)
            if cycle is not None:
                return cycle
    return None


def _validated_edges(
    plugins: list[PluginDependencyInfo],
    info_map: dict[str, PluginDependencyInfo],
    result: DependencyResolution,
) -> dict[str, set[str]]:
    """
    校验必需依赖和版本约束，并构造插件指向其依赖的边。

    :param plugins: 插件依赖信息列表
    :param info_map: 按插件名索引的依赖信息
    :param result: 用于记录校验错误和跳过项的解析结果
    :return: 通过校验的必需依赖边
    """
    required_edges: dict[str, set[str]] = {name: set() for name in info_map}
    for info in plugins:
        for requirement in info.dependencies:
            if requirement.optional and requirement.name not in info_map:
                continue
            dependency = info_map.get(requirement.name)
            if dependency is None:
                result.errors[info.name] = f"依赖插件 {requirement.name} 未找到"
                result.skipped.add(info.name)
                continue
            dependency_version = parse_version(dependency.version)
            if dependency_version is None:
                result.errors[info.name] = f"依赖插件 {requirement.name} 的版本号无效"
                result.skipped.add(info.name)
                continue
            if not requirement.specifier.contains(dependency_version, prereleases=True):
                result.errors[info.name] = (
                    f"依赖插件 {requirement.name} 版本 {dependency.version} 不满足约束 {requirement.version_constraint}"
                )
                result.skipped.add(info.name)
                continue
            required_edges[info.name].add(requirement.name)
    return required_edges


def _topological_order(active_names: set[str], required_edges: dict[str, set[str]]) -> list[str]:
    """
    使用 Kahn 算法生成稳定的插件加载顺序。

    :param active_names: 未因校验错误而跳过的插件名
    :param required_edges: 插件指向其依赖的边
    :return: 依赖先于使用者的插件名列表
    """
    in_degree = dict.fromkeys(active_names, 0)
    dependents: dict[str, list[str]] = {name: [] for name in active_names}
    for name in active_names:
        for dependency in required_edges[name] & active_names:
            dependents[dependency].append(name)
            in_degree[name] += 1

    queue = sorted(name for name, degree in in_degree.items() if degree == 0)
    load_order: list[str] = []
    while queue:
        name = queue.pop(0)
        load_order.append(name)
        for dependent in sorted(dependents[name]):
            in_degree[dependent] -= 1
            if in_degree[dependent] == 0:
                queue.append(dependent)
    return load_order


def resolve_dependencies(plugins: list[PluginDependencyInfo]) -> DependencyResolution:
    """
    解析插件依赖关系，返回加载顺序与错误信息。
    :param plugins: 插件依赖信息列表
    :return: 包含 load_order、errors、skipped 的解析结果
    """
    info_map = {plugin.name: plugin for plugin in plugins}
    names = set(info_map.keys())
    result = DependencyResolution()

    required_edges = _validated_edges(plugins, info_map, result)

    # 第二步：检测环（仅针对未被跳过的插件）
    active_names = names - result.skipped
    active_graph = {name: required_edges[name] & active_names for name in active_names}
    cycle = _detect_cycles(active_graph)
    if cycle is not None:
        cycle_names = " -> ".join(cycle)
        for name in cycle:
            result.errors[name] = f"存在循环依赖: {cycle_names}"
            result.skipped.add(name)

    active_names = names - result.skipped
    load_order = _topological_order(active_names, required_edges)

    if len(load_order) != len(active_names):
        unresolved = active_names - set(load_order)
        for name in unresolved:
            result.errors[name] = "依赖关系无法解析"
            result.skipped.add(name)
        load_order = [n for n in load_order if n not in result.skipped]

    result.load_order = load_order
    return result
