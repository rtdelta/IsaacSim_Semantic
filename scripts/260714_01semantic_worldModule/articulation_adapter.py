"""Direct-position access to selected Isaac Sim articulation DOFs.

The module is intentionally importable outside Isaac Sim.  Isaac-specific
modules are loaded only when :meth:`IsaacArticulationAdapter.bind` creates the
default articulation wrapper.  Tests and other callers may inject an
``articulation_factory`` instead.
"""

from __future__ import annotations

import math
from typing import Any, Callable, Sequence


class ArticulationAdapterError(RuntimeError):
    """Raised when an articulation cannot be bound, validated, read, or written."""


ArticulationFactory = Callable[[str], Any]


def _default_articulation_factory(root_path: str) -> Any:
    """Create Isaac's articulation wrapper without importing Isaac at module load."""

    from isaacsim.core.experimental.prims import Articulation

    return Articulation(root_path)


def _flat_values(value: Any) -> list[Any]:
    """Convert an Isaac tensor-like return value to one flat Python list."""

    if hasattr(value, "numpy"):
        value = value.numpy()
    if hasattr(value, "reshape"):
        value = value.reshape(-1)
    if hasattr(value, "tolist"):
        value = value.tolist()
    if isinstance(value, tuple):
        value = list(value)
    if not isinstance(value, list):
        value = [value]

    flattened: list[Any] = []
    for item in value:
        if isinstance(item, (list, tuple)):
            flattened.extend(_flat_values(item))
        else:
            flattened.append(item)
    return flattened


class IsaacArticulationAdapter:
    """Expose an ordered set of articulation DOFs in degrees.

    ``bind`` is designed to run after the USD stage has opened but before the
    Timeline starts.  Position reads and writes require a valid physics tensor,
    so they become available only after Isaac has advanced a physics frame.
    DOFs are resolved by name once and all writes are submitted as one batch.
    """

    def __init__(
        self,
        articulation_root_path: str,
        ordered_dof_names: Sequence[str],
        articulation_factory: ArticulationFactory | None = None,
    ) -> None:
        self.articulation_root_path = str(articulation_root_path).strip()
        self.ordered_dof_names = tuple(str(name).strip() for name in ordered_dof_names)
        if not self.articulation_root_path:
            raise ArticulationAdapterError("articulation_root_path cannot be empty")
        if not self.ordered_dof_names:
            raise ArticulationAdapterError("ordered_dof_names cannot be empty")
        if any(not name for name in self.ordered_dof_names):
            raise ArticulationAdapterError("ordered_dof_names cannot contain empty names")
        if len(set(self.ordered_dof_names)) != len(self.ordered_dof_names):
            raise ArticulationAdapterError("ordered_dof_names must be unique")
        if articulation_factory is not None and not callable(articulation_factory):
            raise ArticulationAdapterError("articulation_factory must be callable")

        self._articulation_factory = articulation_factory
        self._articulation: Any | None = None
        self._dof_indices: tuple[int, ...] = ()
        self._available_dof_names: tuple[str, ...] = ()

    @property
    def bound(self) -> bool:
        """Whether a wrapper and all requested DOF indices have been resolved."""

        return self._articulation is not None and len(self._dof_indices) == len(
            self.ordered_dof_names
        )

    @property
    def ready(self) -> bool:
        """Whether Isaac has created a valid physics tensor for the wrapper."""

        if not self.bound:
            return False
        try:
            return bool(self._articulation.is_physics_tensor_entity_valid())
        except Exception:
            return False

    @property
    def dof_indices(self) -> tuple[int, ...]:
        """Resolved indices in ``ordered_dof_names`` order."""

        return self._dof_indices

    def bind(self) -> None:
        """Create the wrapper and resolve stable name-to-index bindings."""

        if self.bound:
            return

        factory = self._articulation_factory or _default_articulation_factory
        try:
            articulation = factory(self.articulation_root_path)
            available = tuple(str(name) for name in articulation.dof_names)
            missing = [name for name in self.ordered_dof_names if name not in available]
            if missing:
                raise ArticulationAdapterError(
                    f"Missing DOFs {missing}; available DOFs={list(available)}"
                )

            raw_indices = articulation.get_dof_indices(list(self.ordered_dof_names))
            indices = tuple(int(value) for value in _flat_values(raw_indices))
            if len(indices) != len(self.ordered_dof_names):
                raise ArticulationAdapterError(
                    "DOF index lookup returned "
                    f"{len(indices)} values for {len(self.ordered_dof_names)} names"
                )
            if len(set(indices)) != len(indices) or any(index < 0 for index in indices):
                raise ArticulationAdapterError(
                    f"DOF index lookup returned invalid indices: {list(indices)}"
                )

            # Publish binding state only after every validation has succeeded.
            self._articulation = articulation
            self._available_dof_names = available
            self._dof_indices = indices
        except ArticulationAdapterError:
            raise
        except Exception as exc:
            raise ArticulationAdapterError(
                f"Cannot bind articulation root {self.articulation_root_path}: {exc}"
            ) from exc

    def validate_runtime(self) -> None:
        """Require a bound wrapper with the expected, ready physics tensor."""

        if not self.bound:
            raise ArticulationAdapterError("Articulation adapter is not bound")
        if not self.ready:
            raise ArticulationAdapterError(
                "Articulation physics tensor is not ready; start the Timeline "
                "and wait for a physics frame"
            )

        try:
            num_dofs = int(self._articulation.num_dofs)
        except Exception as exc:
            raise ArticulationAdapterError(f"Cannot inspect articulation DOF count: {exc}") from exc
        if num_dofs != len(self.ordered_dof_names):
            raise ArticulationAdapterError(
                f"Expected {len(self.ordered_dof_names)} DOFs, got {num_dofs}: "
                f"{self._available_dof_names}"
            )
        if any(index >= num_dofs for index in self._dof_indices):
            raise ArticulationAdapterError(
                f"Resolved DOF indices {list(self._dof_indices)} are invalid for {num_dofs} DOFs"
            )

    def get_positions_degrees(self) -> tuple[float, ...]:
        """Read selected DOF positions after a physics step, returning degrees."""

        self.validate_runtime()
        try:
            raw_positions = self._articulation.get_dof_positions(
                dof_indices=list(self._dof_indices)
            )
            values = _flat_values(raw_positions)
            if len(values) != len(self._dof_indices):
                raise ArticulationAdapterError(
                    f"Expected {len(self._dof_indices)} DOF values, got {len(values)}"
                )
            positions = tuple(math.degrees(float(value)) for value in values)
            if any(not math.isfinite(value) for value in positions):
                raise ArticulationAdapterError("Readback contains a non-finite DOF position")
            return positions
        except ArticulationAdapterError:
            raise
        except Exception as exc:
            raise ArticulationAdapterError(f"Cannot read DOF positions: {exc}") from exc

    def set_positions_degrees(self, positions_degrees: Sequence[float]) -> None:
        """Set all selected DOF positions in one batch and zero their velocities."""

        self.validate_runtime()
        try:
            positions = tuple(float(value) for value in positions_degrees)
        except (TypeError, ValueError) as exc:
            raise ArticulationAdapterError(f"DOF positions must be numeric: {exc}") from exc
        if len(positions) != len(self._dof_indices):
            raise ArticulationAdapterError(
                f"Expected {len(self._dof_indices)} positions, got {len(positions)}"
            )
        if any(not math.isfinite(value) for value in positions):
            raise ArticulationAdapterError("DOF positions must all be finite")

        try:
            import numpy as np

            radians = np.asarray(
                [[math.radians(value) for value in positions]], dtype=np.float32
            )
            velocities = np.zeros_like(radians)
            indices = list(self._dof_indices)
            self._articulation.set_dof_positions(radians, dof_indices=indices)
            self._articulation.set_dof_velocities(velocities, dof_indices=indices)
        except Exception as exc:
            raise ArticulationAdapterError(f"Cannot set DOF positions: {exc}") from exc

    def binding_info(self) -> dict[str, Any]:
        """Return JSON-serializable binding information for run manifests."""

        return {
            "articulation_root_path": self.articulation_root_path,
            "ordered_dof_names": list(self.ordered_dof_names),
            "dof_indices": list(self._dof_indices),
            "name_to_index": {
                name: index for name, index in zip(self.ordered_dof_names, self._dof_indices)
            },
            "available_dof_names": list(self._available_dof_names),
            "bound": self.bound,
            "ready": self.ready,
        }

    def shutdown(self) -> None:
        """Release local references so a later stage can be bound safely."""

        self._articulation = None
        self._dof_indices = ()
        self._available_dof_names = ()


__all__ = ["ArticulationAdapterError", "IsaacArticulationAdapter"]
