import sys,unittest
from types import ModuleType
from unittest.mock import patch
from lab.sdk_copy import ImmediateWriterCopy

class CopyContractTests(unittest.TestCase):
    def test_rgb_only_and_restore_classmethod(self):
        class Registry:
            @classmethod
            def get_annotator(cls,name,**kwargs):return name,kwargs
        modules={name:ModuleType(name) for name in ('omni','omni.replicator','omni.replicator.core')}
        modules['omni'].replicator=modules['omni.replicator'];modules['omni.replicator'].core=modules['omni.replicator.core']
        modules['omni.replicator.core'].AnnotatorRegistry=Registry
        original=Registry.__dict__['get_annotator']
        with patch.dict(sys.modules,modules):
            option=ImmediateWriterCopy();option.install()
            self.assertFalse(Registry.get_annotator('rgb',do_array_copy=True)[1]['do_array_copy'])
            self.assertTrue(Registry.get_annotator('lidar',do_array_copy=True)[1]['do_array_copy'])
            option.uninstall();self.assertIs(Registry.__dict__['get_annotator'],original)
if __name__=='__main__':unittest.main()
