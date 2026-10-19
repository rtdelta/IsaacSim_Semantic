"""Use the installed writer-immediate-use contract, then copy to owned CPU memory.

Only RGB do_array_copy changes. No GPU reference crosses writer return, thread,
group or rendering submission. Original synchronous host copy remains mandatory.
"""
class ImmediateWriterCopy:
    def __init__(self):self.original=None
    def install(self):
        import omni.replicator.core as rep
        self.registry=rep.AnnotatorRegistry
        self.original=self.registry.__dict__['get_annotator']
        bound=self.registry.get_annotator
        def get_annotator(cls,name,*args,**kwargs):
            if name=='rgb':kwargs['do_array_copy']=False
            return bound(name,*args,**kwargs)
        self.registry.get_annotator=classmethod(get_annotator)
    def uninstall(self):
        if self.original is not None:self.registry.get_annotator=self.original
