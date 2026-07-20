"""Isaac Sim 6 articulation adapter for direct DOF state access."""

from __future__ import annotations

import math
from typing import Sequence


class ArticulationAdapterError(RuntimeError):
    """Raised when the Isaac articulation cannot be resolved or manipulated."""


class IsaacArticulationAdapter:
    """Expose selected articulation DOFs in degrees while Isaac uses radians."""

    def __init__(self, articulation_root_path: str, ordered_dof_names: Sequence[str]) -> None:
        self.articulation_root_path = str(articulation_root_path)
        self.ordered_dof_names = tuple(str(name) for name in ordered_dof_names)
        if not self.articulation_root_path:
            raise ArticulationAdapterError("articulation_root_path cannot be empty")
        if not self.ordered_dof_names or len(set(self.ordered_dof_names)) != len(
            self.ordered_dof_names
        ):
            raise ArticulationAdapterError("ordered_dof_names must be non-empty and unique")
        self._articulation = None
        self._dof_indices: tuple[int, ...] = ()

    def bind(self) -> None:
        """Create the wrapper and resolve stable name-based DOF indices."""

        try:
            from isaacsim.core.experimental.prims import Articulation

            articulation = Articulation(self.articulation_root_path)
            missing = [name for name in self.ordered_dof_names if name not in articulation.dof_names]
            if missing:
                raise ArticulationAdapterError(
                    f"Missing DOFs {missing}; available DOFs={list(articulation.dof_names)}"
                )
            indices = articulation.get_dof_indices(list(self.ordered_dof_names)).numpy()
            self._dof_indices = tuple(int(value) for value in indices.reshape(-1).tolist())
            self._articulation = articulation
        except ArticulationAdapterError:
            raise
        except Exception as exc:
            raise ArticulationAdapterError(
                f"Cannot bind articulation root {self.articulation_root_path}: {exc}"
            ) from exc

    @property
    def bound(self) -> bool:
        return self._articulation is not None and bool(self._dof_indices)

    @property
    def ready(self) -> bool:
        if not self.bound:
            return False
        try:
            return bool(self._articulation.is_physics_tensor_entity_valid())
        except Exception:
            return False

    def validate_runtime(self) -> None:
        if not self.bound:
            raise ArticulationAdapterError("Articulation adapter is not bound")
        if not self.ready:
            raise ArticulationAdapterError(
                "Articulation physics tensor is not ready; start the Timeline and wait for a physics frame"
            )
        available = tuple(self._articulation.dof_names)
        if self._articulation.num_dofs != len(self.ordered_dof_names):
            raise ArticulationAdapterError(
                f"Expected {len(self.ordered_dof_names)} DOFs, got "
                f"{self._articulation.num_dofs}: {available}"
            )

    def get_positions_degrees(self) -> tuple[float, ...]:
        self.validate_runtime()
        try:
            values = self._articulation.get_dof_positions(
                dof_indices=list(self._dof_indices)
            ).numpy()
            flattened = values.reshape(-1)
            if flattened.size != len(self._dof_indices):
                raise ArticulationAdapterError(
                    f"Expected {len(self._dof_indices)} DOF values, got shape {values.shape}"
                )
            return tuple(math.degrees(float(value)) for value in flattened.tolist())
        except ArticulationAdapterError:
            raise
        except Exception as exc:
            raise ArticulationAdapterError(f"Cannot read DOF positions: {exc}") from exc

    def set_positions_degrees(self, positions_degrees: Sequence[float]) -> None:
        self.validate_runtime()
        positions = tuple(float(value) for value in positions_degrees)
        if len(positions) != len(self._dof_indices):
            raise ArticulationAdapterError(
                f"Expected {len(self._dof_indices)} positions, got {len(positions)}"
            )
        if any(not math.isfinite(value) for value in positions):
            raise ArticulationAdapterError("DOF positions must all be finite")
        try:
            import numpy as np

            radians = np.asarray([[math.radians(value) for value in positions]], dtype=np.float32)
            zeros = np.zeros_like(radians)
            indices = list(self._dof_indices)
            self._articulation.set_dof_positions(radians, dof_indices=indices)
            self._articulation.set_dof_velocities(zeros, dof_indices=indices)
        except Exception as exc:
            raise ArticulationAdapterError(f"Cannot set DOF positions: {exc}") from exc

    def hold_current_position(self) -> tuple[float, ...]:
        current = self.get_positions_degrees()
        self.set_positions_degrees(current)
        return current

    def shutdown(self) -> None:
        self._articulation = None
        self._dof_indices = ()
