import tempfile
import unittest
from pathlib import Path

from semantic_world_v04.runtime.preflight import check_host_preflight


class RuntimePreflightTests(unittest.TestCase):
    def test_preflight_checks_writable_output_and_records_gpu(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            snapshot = check_host_preflight(
                Path(temp),
                minimum_free_bytes=1,
                gpu_probe=lambda: {
                    "available": True,
                    "devices": ["Fake GPU, 1024, test-driver"],
                },
                require_isaac_abi=False,
            )
            self.assertTrue(snapshot["gpu"]["available"])
            self.assertGreater(snapshot["disk"]["free_bytes"], 0)
            self.assertFalse(
                any(Path(temp).glob(".v04-write-probe-*")),
                "write probe must be cleaned up",
            )


if __name__ == "__main__":
    unittest.main()
