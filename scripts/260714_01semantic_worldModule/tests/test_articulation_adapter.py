"""Pure-Python tests for the Isaac articulation adapter."""

from __future__ import annotations

import math
import unittest

import numpy as np

from articulation_adapter import ArticulationAdapterError, IsaacArticulationAdapter


JOINT_NAMES = ("cab", "boom", "small_arm", "bucket")


class FakeTensor:
    def __init__(self, values) -> None:
        self._values = np.asarray(values)

    def numpy(self):
        return self._values


class FakeArticulation:
    def __init__(
        self,
        dof_names=("bucket", "cab", "small_arm", "boom"),
        *,
        ready=True,
        positions=None,
    ) -> None:
        self.dof_names = list(dof_names)
        self.num_dofs = len(self.dof_names)
        self.tensor_ready = ready
        self.positions = np.asarray(
            positions if positions is not None else [[0.0] * self.num_dofs],
            dtype=np.float32,
        )
        self.position_writes = []
        self.velocity_writes = []

    def get_dof_indices(self, names):
        return FakeTensor([self.dof_names.index(name) for name in names])

    def is_physics_tensor_entity_valid(self):
        return self.tensor_ready

    def get_dof_positions(self, *, dof_indices):
        return FakeTensor(self.positions[:, dof_indices])

    def set_dof_positions(self, values, *, dof_indices):
        copied = np.array(values, copy=True)
        self.position_writes.append((copied, list(dof_indices)))
        self.positions[:, dof_indices] = copied

    def set_dof_velocities(self, values, *, dof_indices):
        self.velocity_writes.append((np.array(values, copy=True), list(dof_indices)))


class ArticulationAdapterTests(unittest.TestCase):
    def make_adapter(self, articulation):
        calls = []

        def factory(root_path):
            calls.append(root_path)
            return articulation

        adapter = IsaacArticulationAdapter(
            "/World/Joints/world_track_fixed_joint",
            JOINT_NAMES,
            articulation_factory=factory,
        )
        return adapter, calls

    def test_rejects_invalid_constructor_values(self) -> None:
        with self.assertRaisesRegex(ArticulationAdapterError, "root_path"):
            IsaacArticulationAdapter("", JOINT_NAMES)
        with self.assertRaisesRegex(ArticulationAdapterError, "cannot be empty"):
            IsaacArticulationAdapter("/World/Root", ())
        with self.assertRaisesRegex(ArticulationAdapterError, "unique"):
            IsaacArticulationAdapter("/World/Root", ("cab", "cab"))
        with self.assertRaisesRegex(ArticulationAdapterError, "callable"):
            IsaacArticulationAdapter("/World/Root", JOINT_NAMES, articulation_factory=object())

    def test_bind_resolves_indices_by_name_before_tensor_is_ready(self) -> None:
        articulation = FakeArticulation(ready=False)
        adapter, calls = self.make_adapter(articulation)

        adapter.bind()

        self.assertEqual(calls, ["/World/Joints/world_track_fixed_joint"])
        self.assertTrue(adapter.bound)
        self.assertFalse(adapter.ready)
        self.assertEqual(adapter.dof_indices, (1, 3, 2, 0))
        adapter.bind()  # A repeated lifecycle call is intentionally idempotent.
        self.assertEqual(len(calls), 1)

    def test_bind_rejects_missing_or_invalid_indices_without_partial_state(self) -> None:
        articulation = FakeArticulation(dof_names=("cab", "boom", "bucket"))
        adapter, _ = self.make_adapter(articulation)
        with self.assertRaisesRegex(ArticulationAdapterError, "Missing DOFs"):
            adapter.bind()
        self.assertFalse(adapter.bound)

        articulation = FakeArticulation()
        articulation.get_dof_indices = lambda names: FakeTensor([0, 0, 2, 3])
        adapter, _ = self.make_adapter(articulation)
        with self.assertRaisesRegex(ArticulationAdapterError, "invalid indices"):
            adapter.bind()
        self.assertFalse(adapter.bound)

    def test_validate_runtime_requires_binding_readiness_and_exact_dof_count(self) -> None:
        articulation = FakeArticulation(ready=False)
        adapter, _ = self.make_adapter(articulation)
        with self.assertRaisesRegex(ArticulationAdapterError, "not bound"):
            adapter.validate_runtime()
        adapter.bind()
        with self.assertRaisesRegex(ArticulationAdapterError, "not ready"):
            adapter.validate_runtime()
        articulation.tensor_ready = True
        articulation.num_dofs = 5
        with self.assertRaisesRegex(ArticulationAdapterError, "Expected 4 DOFs, got 5"):
            adapter.validate_runtime()

    def test_set_positions_converts_degrees_and_zeroes_velocities_as_batches(self) -> None:
        articulation = FakeArticulation()
        adapter, _ = self.make_adapter(articulation)
        adapter.bind()

        adapter.set_positions_degrees((0.0, 90.0, -180.0, 45.0))

        self.assertEqual(len(articulation.position_writes), 1)
        self.assertEqual(len(articulation.velocity_writes), 1)
        positions, indices = articulation.position_writes[0]
        velocities, velocity_indices = articulation.velocity_writes[0]
        self.assertEqual(positions.shape, (1, 4))
        np.testing.assert_allclose(
            positions,
            [[0.0, math.pi / 2.0, -math.pi, math.pi / 4.0]],
            rtol=1e-6,
        )
        np.testing.assert_array_equal(velocities, np.zeros((1, 4), dtype=np.float32))
        self.assertEqual(indices, [1, 3, 2, 0])
        self.assertEqual(velocity_indices, indices)

    def test_set_positions_rejects_wrong_length_and_nonfinite_values(self) -> None:
        articulation = FakeArticulation()
        adapter, _ = self.make_adapter(articulation)
        adapter.bind()
        with self.assertRaisesRegex(ArticulationAdapterError, "Expected 4 positions"):
            adapter.set_positions_degrees((1.0, 2.0))
        with self.assertRaisesRegex(ArticulationAdapterError, "finite"):
            adapter.set_positions_degrees((0.0, 0.0, float("nan"), 0.0))
        self.assertFalse(articulation.position_writes)
        self.assertFalse(articulation.velocity_writes)

    def test_get_positions_returns_ordered_degrees(self) -> None:
        articulation = FakeArticulation(
            positions=[[math.pi, math.pi / 6.0, -math.pi / 2.0, math.pi / 3.0]]
        )
        adapter, _ = self.make_adapter(articulation)
        adapter.bind()

        positions = adapter.get_positions_degrees()

        expected = (30.0, 60.0, -90.0, 180.0)
        for actual, target in zip(positions, expected):
            self.assertAlmostEqual(actual, target, places=4)

    def test_binding_info_is_serializable_and_shutdown_clears_state(self) -> None:
        articulation = FakeArticulation()
        adapter, _ = self.make_adapter(articulation)
        adapter.bind()

        info = adapter.binding_info()

        self.assertEqual(info["ordered_dof_names"], list(JOINT_NAMES))
        self.assertEqual(info["dof_indices"], [1, 3, 2, 0])
        self.assertEqual(info["name_to_index"]["boom"], 3)
        self.assertTrue(info["bound"])
        self.assertTrue(info["ready"])

        adapter.shutdown()
        self.assertFalse(adapter.bound)
        self.assertFalse(adapter.ready)
        self.assertEqual(adapter.dof_indices, ())
        self.assertEqual(adapter.binding_info()["available_dof_names"], [])


if __name__ == "__main__":
    unittest.main()
