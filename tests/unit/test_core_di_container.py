"""Unit tests for ``stock_screener.core.di``."""

from __future__ import annotations

import pytest

from stock_screener.core.di import Container


class PortA:
    pass


class PortB:
    pass


class _ImplA(PortA):
    pass


class _ImplB(PortB):
    def __init__(self, dependency: PortA) -> None:
        self.dependency = dependency


def test_register_instance_resolves_to_same_instance() -> None:
    c = Container()
    impl = _ImplA()
    c.register_instance(PortA, impl)
    assert c.resolve(PortA) is impl


def test_register_factory_memoises_first_resolution() -> None:
    c = Container()
    calls = {"count": 0}

    def factory(_c: Container) -> PortA:
        calls["count"] += 1
        return _ImplA()

    c.register_factory(PortA, factory)
    first = c.resolve(PortA)
    second = c.resolve(PortA)
    assert first is second
    assert calls["count"] == 1


def test_resolve_unregistered_port_raises_lookup_error() -> None:
    c = Container()
    with pytest.raises(LookupError):
        c.resolve(PortA)


def test_has_returns_true_for_known_bindings() -> None:
    c = Container()
    assert c.has(PortA) is False

    c.register_instance(PortA, _ImplA())
    assert c.has(PortA) is True

    c.register_factory(PortB, lambda _c: _ImplB(_ImplA()))
    assert c.has(PortB) is True


def test_override_swaps_binding() -> None:
    c = Container()
    original = _ImplA()
    replacement = _ImplA()
    c.register_instance(PortA, original)
    c.override(PortA, replacement)
    assert c.resolve(PortA) is replacement


def test_reset_clears_all_bindings() -> None:
    c = Container()
    c.register_instance(PortA, _ImplA())
    c.register_factory(PortB, lambda _c: _ImplB(_ImplA()))
    c.reset()

    assert c.has(PortA) is False
    assert c.has(PortB) is False
    with pytest.raises(LookupError):
        c.resolve(PortA)


def test_factory_receives_container_for_dependent_lookups() -> None:
    c = Container()
    impl_a = _ImplA()
    c.register_instance(PortA, impl_a)
    c.register_factory(PortB, lambda inner: _ImplB(inner.resolve(PortA)))

    resolved = c.resolve(PortB)
    assert isinstance(resolved, _ImplB)
    assert resolved.dependency is impl_a


def test_two_distinct_ports_can_coexist() -> None:
    c = Container()
    impl_a = _ImplA()
    impl_b = _ImplB(impl_a)
    c.register_instance(PortA, impl_a)
    c.register_instance(PortB, impl_b)

    assert c.resolve(PortA) is impl_a
    assert c.resolve(PortB) is impl_b
