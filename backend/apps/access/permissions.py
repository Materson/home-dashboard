"""Module/level constants and the model→module routing table.

Each module is a top-level concern users can be granted on. Each app declares
which module its models belong to by implementing ``Meta.access_module`` or
registering with ``register_module_for(Model, "...")``. ``module_for_model``
is the single lookup."""

from __future__ import annotations

from typing import Final

from django.db.models import Model

MODULES: Final = (
    "finance",
    "cars",
    "health",
    "household",
    "calendar",
    "notes",
    "assistant",
    "people",
    "admin",
)

LEVELS: Final = ("view", "edit", "manage")
LEVEL_ORDER = {lvl: i for i, lvl in enumerate(LEVELS)}

_MODEL_TO_MODULE: dict[type[Model], str] = {}


def register_module_for(model: type[Model], module: str) -> None:
    if module not in MODULES:
        raise ValueError(f"unknown module {module!r}")
    _MODEL_TO_MODULE[model] = module


def module_for_model(model: type[Model]) -> str:
    try:
        return _MODEL_TO_MODULE[model]
    except KeyError:
        pass
    declared = getattr(model._meta, "access_module", None)  # type: ignore[attr-defined]
    if declared:
        return declared
    raise LookupError(f"no access module registered for {model.__qualname__}")


def level_at_least(have: str, required: str) -> bool:
    return LEVEL_ORDER[have] >= LEVEL_ORDER[required]
