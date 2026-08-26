import importlib
import sys
import unittest


class OptionalImportTests(unittest.TestCase):
    def test_omni_adapter_import_does_not_load_omni(self) -> None:
        before = set(sys.modules)
        module = importlib.import_module("semantic_world_v04.stage.omni_adapter")
        self.assertTrue(hasattr(module, "OmniStageService"))
        loaded = set(sys.modules) - before
        self.assertFalse(any(name == "omni" or name.startswith("omni.") for name in loaded))


if __name__ == "__main__":
    unittest.main()

