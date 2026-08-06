"""插件依赖解析与拓扑排序测试。"""
from packaging.specifiers import SpecifierSet

from ECL.Plugin.dependencies import (
    DependencyRequirement,
    PluginDependencyInfo,
    parse_dependency,
    parse_version,
    resolve_dependencies,
)


def test_parse_dependency_string() -> None:
    req = parse_dependency("other", ">=1.0.0")
    assert req is not None
    assert req.name == "other"
    assert str(req.specifier) == ">=1.0.0"
    assert req.optional is False


def test_parse_dependency_object() -> None:
    req = parse_dependency("other", {"version": ">=2.0.0", "optional": True})
    assert req is not None
    assert req.name == "other"
    assert str(req.specifier) == ">=2.0.0"
    assert req.optional is True


def test_parse_dependency_wildcard() -> None:
    req = parse_dependency("other", "*")
    assert req is not None
    assert str(req.specifier) == ""


def test_parse_dependency_invalid() -> None:
    assert parse_dependency("other", 123) is None
    assert parse_dependency("other", "not-a-spec") is None


def test_parse_version() -> None:
    assert parse_version("1.0.0") is not None
    assert parse_version("bad") is None


def test_resolve_simple_chain() -> None:
    plugins = [
        PluginDependencyInfo("a", "1.0.0", [DependencyRequirement("b", SpecifierSet(""))]),
        PluginDependencyInfo("b", "1.0.0", [DependencyRequirement("c", SpecifierSet(""))]),
        PluginDependencyInfo("c", "1.0.0"),
    ]
    result = resolve_dependencies(plugins)
    assert result.errors == {}
    assert result.skipped == set()
    assert result.load_order == ["c", "b", "a"]


def test_resolve_version_mismatch() -> None:
    plugins = [
        PluginDependencyInfo("a", "1.0.0", [DependencyRequirement("b", SpecifierSet(">=2.0.0"))]),
        PluginDependencyInfo("b", "1.0.0"),
    ]
    result = resolve_dependencies(plugins)
    assert "a" in result.skipped
    assert "版本 1.0.0 不满足约束 >=2.0.0" in result.errors["a"]


def test_resolve_missing_dependency() -> None:
    plugins = [
        PluginDependencyInfo("a", "1.0.0", [DependencyRequirement("missing", SpecifierSet(""))]),
    ]
    result = resolve_dependencies(plugins)
    assert result.skipped == {"a"}
    assert "依赖插件 missing 未找到" in result.errors["a"]


def test_resolve_optional_missing_dependency() -> None:
    plugins = [
        PluginDependencyInfo("a", "1.0.0", [DependencyRequirement("missing", SpecifierSet(""), optional=True)]),
    ]
    result = resolve_dependencies(plugins)
    assert result.skipped == set()
    assert result.load_order == ["a"]


def test_resolve_circular_dependency() -> None:
    plugins = [
        PluginDependencyInfo("a", "1.0.0", [DependencyRequirement("b", SpecifierSet(""))]),
        PluginDependencyInfo("b", "1.0.0", [DependencyRequirement("a", SpecifierSet(""))]),
    ]
    result = resolve_dependencies(plugins)
    assert result.skipped == {"a", "b"}
    assert "循环依赖" in result.errors["a"]
    assert "循环依赖" in result.errors["b"]


def test_resolve_stable_order() -> None:
    plugins = [
        PluginDependencyInfo("a", "1.0.0"),
        PluginDependencyInfo("b", "1.0.0"),
        PluginDependencyInfo("c", "1.0.0"),
    ]
    result = resolve_dependencies(plugins)
    assert result.load_order == ["a", "b", "c"]
