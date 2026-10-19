"""Bounded timestamp join; incomplete groups never masquerade as full captures."""
class FrameGroups:
    def __init__(self, camera_ids, max_pending=3):
        self.ids=tuple(camera_ids)
        if not self.ids or len(set(self.ids))!=len(self.ids):
            raise ValueError('Camera IDs must be nonempty and unique')
        self.limit=max_pending
        self.pending={}
        self.last_emitted=-1

    def add(self, camera_id, timestamp_ns, frame):
        if camera_id not in self.ids:
            raise ValueError('Unknown camera '+camera_id)
        if timestamp_ns<=self.last_emitted:
            return [],[]
        self.pending.setdefault(timestamp_ns,{})[camera_id]=frame
        completed=[];dropped=[]
        while self.pending:
            stamp=min(self.pending)
            group=self.pending[stamp]
            if len(group)==len(self.ids):
                completed.append((stamp,self.pending.pop(stamp)))
                self.last_emitted=stamp
            elif len(self.pending)>self.limit:
                dropped.append(self._drop(stamp,'buffer_limit'))
                self.last_emitted=stamp
            else:
                break
        return completed,dropped

    def _drop(self,stamp,reason):
        group=self.pending.pop(stamp)
        return {'simulation_time_ns':stamp,'missing_cameras':[x for x in self.ids if x not in group],
                'reason':reason}

    def finish(self):
        complete=[];dropped=[]
        for t in sorted(self.pending):
            if len(self.pending[t])==len(self.ids):
                complete.append((t,self.pending.pop(t)))
            else:
                dropped.append(self._drop(t,'recording_stopped'))
            self.last_emitted=t
        return complete,dropped
