"""Lightweight dependency-injection container.

The single seam where ``infra/*`` and ``domain/*`` meet. Use-cases ask the
container for ports; tests can override any binding without monkey-patching.
"""

from __future__ import annotations

from typing import Any, Callable, TypeVar, cast

T = TypeVar("T")


class Container:
    """Tiny service locator with explicit registration.

    Bindings can be:
      - a singleton instance (``register_instance``), returned as-is.
      - a factory (``register_factory``), called once and memoised.
    """

    def __init__(self) -> None:
        self._instances: dict[type, object] = {}
        self._factories: dict[type, Callable[["Container"], object]] = {}

    # --------------------------- registration --------------------------- #
    def register_instance(self, port: type[T], instance: T) -> None:
        self._instances[port] = instance

    def register_factory(self, port: type[T], factory: Callable[["Container"], T]) -> None:
        self._factories[port] = cast(Callable[["Container"], object], factory)

    # ----------------------------- resolve ----------------------------- #
    def resolve(self, port: type[T]) -> T:
        if port in self._instances:
            return cast(T, self._instances[port])
        if port in self._factories:
            instance = self._factories[port](self)
            self._instances[port] = instance
            return cast(T, instance)
        raise LookupError(f"No binding registered for {port!r}")

    def has(self, port: type) -> bool:
        return port in self._instances or port in self._factories

    # ----------------------------- testing ----------------------------- #
    def override(self, port: type[T], instance: T) -> None:
        """Test hook — swap any binding (skips factory memoisation)."""
        self._instances[port] = instance

    def reset(self) -> None:
        self._instances.clear()
        self._factories.clear()


def make_default_container(config: Any) -> Container:
    """Build the production container.

    Imported lazily so the domain has zero hard dependency on infra modules.
    Concrete wiring lives in :mod:`stock_screener.bootstrap`.
    """
    from ..bootstrap import wire  # local import — avoids cycles

    container = Container()
    wire(container, config)
    return container


__all__ = ["Container", "make_default_container"]
