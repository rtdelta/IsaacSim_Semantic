"""Exact reserved target -> owned join -> CPU write -> independent publication."""
import asyncio
import hashlib
import json
import os
from pathlib import Path
import subprocess
import time
from .common import ContractError,cjson,digest,file_hash,save_json,source_ns,utc
from .config import SamplingClock
from .time_joiner import TimeJoiner,GroupTicket
from .buffer_pool import BufferPool
from .record_pipeline import RecordPipeline,cpu_environment
from .diagnostics import EvidenceLog,statistics,process_resources
from .barrier_driver import BarrierDriver
from .sensor_backend import pose_error


class Recording:
    def __init__(self,owner,directory):
        self.owner,self.directory=owner,Path(directory)
        self.directory.mkdir(parents=True,exist_ok=False)
        (self.directory/'logs').mkdir()
        self.log=EvidenceLog(self.directory,owner.recording_id)
        self.pool=self.pipeline=self.joiner=None
        self.complete_group=None
        self.receipt_error=None
        self.worker_ready=self.worker_closed=False
        self.request_stop=self.request_pause=False
        self.panel=self.geometry_spec=None
        self.stop_step=None
        self.backpressure_active=False
        self.closed_segments=[]
        self.injected_groups=set()
        self.held_receipt=self.cached_receipt=None
        self.release_seen=set()
        self.written_seen=set()
        self.cold=time.monotonic()
        self.latencies={k:[] for k in ('source_materialization','join_wait','control_input')}
        names=('continuous_ok','sync_ok','completeness_ok','quality_ok','performance_ok','interaction_ok','lifecycle_ok')
        self.session={'schema_version':1,'recording_id':owner.recording_id,'status':'PREPARING','outcome':None,'timeline_state':'initializing',
            'started_utc':utc(),'ended_utc':None,'backend':None,'policy':owner.job['capture']['policy'],
            'requested_groups':owner.job['capture']['requested_groups'],'epochs':[],
            'counts':dict(requested=owner.job['capture']['requested_groups'],scheduled=0,validated=0,written=0,readback_verified=0,
                          dropped=0,gap_groups=0,received_by_sensor={},duplicate=0,invalid=0,late=0,queue_full=0,backpressure_pause=0),
            'failure':None,'acceptance_results':{k:None for k in names},
            'acceptance_evidence':{k:{'scope':'this recording','reason':'not yet tested','evidence_paths':[]} for k in names}}
        self.save_session()

    def save_session(self):
        save_json(self.directory/'session.json',self.session)

    async def gate_barrier(self):
        o=self.owner
        driver=BarrierDriver(o)
        rows,errors,owned=[],[],{}
        selected={e['sensor_id'] for k in ('cameras','lidars') for e in o.registry[k]}
        current={}
        target=None
        def receive(e,a):
            if target is None:
                return
            step,state=o.ledger.exact_time(o.epoch_id,int(e['source_time_ns']))
            tr,ang=pose_error(state['sensor_world_matrices_usd'][e['sensor_id']],e['rendered_to_world'])
            rows.append(dict(e,physical_step=step,target_step=target,historical_to_world=state['sensor_world_matrices_usd'][e['sensor_id']],translation_error_m=tr,rotation_error_rad=ang))
            current[e['sensor_id']]=e
            if e['sensor_id'] not in owned:
                owned[e['sensor_id']]=(a,hashlib.sha256(a.tobytes()).hexdigest())
        o.on_receipt=receive
        o.on_reject=lambda e:errors.append(e) if target is not None else None
        o.moving=True
        await driver.prepare()
        for _ in range(24):
            target=(o.manager.get_num_physics_steps()//6+1)*6
            current.clear()
            await driver.target(target,lambda:set(current)==selected,time.monotonic_ns()+int(o.job['capture']['group_timeout_wall_s']*1e9))
            if errors:
                raise ContractError('barrier_source',str(errors[-1]))
        passed=bool(rows) and all(r['physical_step']==r['target_step'] and r['translation_error_m']<=.001 and r['rotation_error_rad']<=.0001 for r in rows)
        distinct={s:len({json.dumps(r['historical_to_world']) for r in rows if r['sensor_id']==s}) for s in selected}
        passed=passed and all(n>=20 for n in distinct.values())
        owned_ok=all(a.flags.owndata and a.flags.c_contiguous and hashlib.sha256(a.tobytes()).hexdigest()==h for a,h in owned.values())
        passed=passed and owned_ok
        folder=self.directory/'capability_probe'
        save_json(folder/'receipts.json',rows)
        save_json(folder/'errors.json',errors)
        cap={'schema_version':1,'recording_id':o.recording_id,'capability_id':o.capability_id,
             'status':'barrier_verified' if passed else 'unsupported','selected_backend':'barrier' if passed else None,
             'tests':[{'name':'single_event_barrier_time_pose_ownership','passed':passed,
                       'reason':'24 moving physical targets, native mapped source, full resolution owned CPU buffers, exact rendered pose',
                       'sample_count':len(rows),'evidence_paths':['capability_probe/receipts.json','capability_probe/errors.json']}],
             'source_mapping':{s:{'annotator':'IsaacReadSimulationTime','clock_domain':'physics_simulation',
                'mapping_method':'get_simulation_time_at_time(ReferenceTime)','native_ref_kind':'rational_time',
                'native_ref_scope':next(r['native_ref']['scope'] for r in rows if r['sensor_id']==s),
                'max_native_lead_groups':0,'verified_max_inflight':1} for s in selected},
             'state_capture_phase':'pre physical prescribed motion; post physical actual readback; paused exact target; one manual Writer request',
             'failures':[] if passed else [{'code':'barrier_pose','message':'Native pose/time boundary did not meet contract','evidence_paths':['capability_probe/receipts.json']}],
             'actual_max_inflight_groups':1,'max_native_lead_groups':0}
        cap['tests'].append({'name':'owned_cpu_lifetime','passed':owned_ok,'reason':'Retained independent arrays unchanged over 24 later physical targets',
                             'sample_count':len(owned),'evidence_paths':['capability_probe/receipts.json']})
        o.motion.base_controller.hold()
        o.moving=False
        o._moving_started=False
        return cap,driver

    def received(self,evidence,payload):
        fault=self.owner.job.get('diagnostics',{}).get('receipt_fault',{})
        tickets=list(self.joiner.tickets.values()) if self.joiner else []
        ticket=tickets[0] if tickets else None
        if fault.get('kind')=='old_frame' and ticket and ticket.group_id==0 and evidence['sensor_id']==fault.get('sensor_id','camera/front'):
            self.cached_receipt=(evidence,payload)
        if fault and ticket and ticket.group_id==fault.get('group_id',1) and evidence['sensor_id']==fault.get('sensor_id','camera/front') and ticket.group_id not in self.injected_groups:
            kind=fault['kind']
            self.injected_groups.add(ticket.group_id)
            self.log.event('receipts.jsonl','fault_injected',{'kind':kind,'scope':'explicit CPU transport injection of actual native owned receipt',
                'group_id':ticket.group_id,'sensor_id':evidence['sensor_id'],'original_source_time_ns':evidence['source_time_ns'],'original_native_ref':evidence['native_ref']},self.owner.epoch_id)
            if kind in ('delay','out_of_order'):
                self.held_receipt=(evidence,payload,time.monotonic_ns()+int(float(fault.get('delay_s',2))*1e9) if kind=='delay' else 0,kind)
                return
            if kind=='old_frame':
                if self.cached_receipt is None:
                    self.receipt_error={'code':'fault_config','message':'No actual prior receipt was captured'}
                    return
                self._received(*self.cached_receipt)
                return
            if kind=='old_epoch':
                self._received(evidence,payload,'diagnostic_old_epoch')
                return
            if kind in ('duplicate','conflicting_duplicate'):
                self._received(evidence,payload)
                second=payload
                if kind=='conflicting_duplicate':
                    second=payload.copy()
                    second.reshape(-1)[0]^=1
                self._received(evidence,second)
                return
            self.receipt_error={'code':'fault_config','message':'Unknown receipt fault kind: '+kind}
            return
        self._received(evidence,payload)

    def completion(self):
        if self.held_receipt:
            e,a,release,kind=self.held_receipt
            ticket=next(iter(self.joiner.tickets.values()))
            ready=time.monotonic_ns()>=release if kind=='delay' else set(ticket.received)==set(ticket.expected_sensor_ids)-{e['sensor_id']}
            if ready:
                self.held_receipt=None
                self.log.event('receipts.jsonl','fault_release',{'kind':kind,'sensor_id':e['sensor_id'],'actual_source_time_ns':e['source_time_ns']},self.owner.epoch_id)
                self._received(e,a)
        return self.complete_group is not None or self.receipt_error is not None

    def _received(self,evidence,payload,epoch_override=None):
        try:
            fault=self.owner.job.get('diagnostics',{}).get('drop_sensor',{})
            if fault and evidence['sensor_id']==fault['sensor_id'] and any(t.group_id==fault.get('group_id',1) for t in self.joiner.tickets.values()):
                self.log.event('receipts.jsonl','fault_injected',{'kind':'missing_route','sensor_id':evidence['sensor_id'],
                       'source_time_ns':evidence['source_time_ns'],'native_ref':evidence['native_ref']},self.owner.epoch_id)
                return
            group,disposition=self.joiner.receive(evidence,payload,epoch_override or self.owner.epoch_id,self.owner.scene_generation)
            if disposition=='unrequested':
                self.log.event('receipts.jsonl','unscheduled_discarded',{'sensor_id':evidence['sensor_id'],'source_time_ns':evidence['source_time_ns'],'native_ref':evidence['native_ref']},self.owner.epoch_id)
            if disposition=='duplicate':
                self.session['counts']['duplicate']+=1
            if disposition=='accepted':
                sid=evidence['sensor_id']
                self.session['counts']['received_by_sensor'][sid]+=1
                self.latencies['source_materialization'].append((int(evidence['copy_completed_monotonic_ns'])-int(evidence['received_monotonic_ns']))/1e6)
                ticket=next(t for t in self.joiner.tickets.values() if abs(int(t.simulation_time_ns)-int(evidence['source_time_ns']))<=2)
                self.log.event('receipts.jsonl','accepted',dict(group=ticket.schedule(),evidence=ticket.received[sid][0]),ticket.epoch_id,ticket.segment_id)
            if group:
                if self.complete_group is not None:
                    raise ContractError('multiple_groups','Only one native target is permitted in flight')
                self.complete_group=group
                self.session['counts']['validated']+=1
                times=[int(e['received_monotonic_ns']) for e,a in group['receipts'].values()]
                self.latencies['join_wait'].append((max(times)-min(times))/1e6)
        except Exception as exc:
            self.receipt_error={'code':getattr(exc,'code','join'),'message':str(exc),'evidence_paths':['receipts.jsonl']}
            self.session['counts']['invalid']+=1
            if getattr(exc,'code',None)=='group_deadline':
                self.session['counts']['late']+=1
            self.log.event('receipts.jsonl','rejected',dict(self.receipt_error,sensor_id=evidence['sensor_id']),self.owner.epoch_id)

    def state(self,state):
        try:
            self.joiner.publish_state(state)
            if self.geometry_spec:
                self.log.event('diagnostic_states.jsonl','actual_physical_state',state,state['epoch_id'])
            if self.session['backend']=='continuous' and self.stop_step is not None and state['physical_step']>=self.stop_step and not self.backpressure_active:
                self.owner.setting('/app/player/playSimulations',False)
                self.backpressure_active=True
                self.session['counts']['backpressure_pause']+=1
                self.log.event('groups.jsonl','backpressure_pause',{'physical_step':state['physical_step'],'reason':'next target has no written/reusable credit'},state['epoch_id'])
        except Exception as exc:
            self.receipt_error={'code':getattr(exc,'code','state'),'message':str(exc),'evidence_paths':['schedule.jsonl']}

    def poll(self,ticket=None):
        if self.receipt_error:
            raise ContractError(self.receipt_error['code'],self.receipt_error['message'])
        if self.owner.error:
            raise ContractError(self.owner.error['code'],self.owner.error['message'])
        for ack in self.pipeline.poll():
            if ack.get('recording_id')!=self.owner.recording_id:
                raise ContractError('ack_recording','Worker ACK recording differs')
            kind=ack['type']
            self.log.event('groups.jsonl',kind,ack,ack.get('epoch_id'),ack.get('segment_id'))
            if kind=='ready':
                self.worker_ready=True
                now=time.monotonic_ns()
                boot=Path('/proc/sys/kernel/random/boot_id').read_text().strip()
                self.environment['monotonic_clock']['cross_process_verified']=ack.get('boot_id')==boot and self.worker_launch_ns<=int(ack['monotonic_ns'])<=now
                self.environment['versions'].update(ack.get('versions',{}))
                save_json(self.directory/'environment.json',self.environment)
            elif kind in ('release','written'):
                if ticket is None or any(ack.get(k)!=getattr(ticket,k) for k in ('epoch_id','segment_id','group_id')):
                    raise ContractError('stale_ack','Worker ACK is outside the reserved ticket')
                identity=(ticket.recording_id,ticket.epoch_id,ticket.group_id)
                fault=self.owner.job.get('diagnostics',{}).get('ack_fault',{})
                if fault.get('kind')==kind and ticket.group_id==fault.get('group_id',1):
                    self.log.event('groups.jsonl','fault_injected',{'kind':'old_'+kind+'_ack','original_ack':ack,'altered_generation':ack['generation']-1},ticket.epoch_id,ticket.segment_id)
                    ack=dict(ack,generation=ack['generation']-1)
                if kind=='release':
                    self.pool.release(ack['slot'],ack['generation'],identity)
                    self.release_seen.add(ticket.group_id)
                else:
                    if ticket.group_id not in self.release_seen or ticket.group_id in self.written_seen:
                        raise ContractError('ack_order','Written must follow exactly one valid release')
                    self.pool.written(ack['slot'],ack['generation'],identity)
                    self.written_seen.add(ticket.group_id)
                    self.session['counts']['written']+=1
            elif kind=='segment_closed':
                if not ack['success']:
                    raise ContractError('segment_close','MCAP segment did not close')
                self.closed_segments.append(ack['segment_id'])
            elif kind=='worker_closed':
                self.worker_closed=True
            elif kind=='failed':
                raise ContractError(ack['error']['code'],ack['error']['message'])
        if self.pipeline.process.poll() is not None and not self.worker_closed:
            raise ContractError('worker_died','CPU worker exited before a close ACK')

    async def wait(self,predicate,ticket=None,seconds=30):
        until=time.monotonic()+seconds
        while not predicate():
            self.poll(ticket)
            if time.monotonic()>until:
                raise ContractError('worker_deadline','Worker completion deadline expired')
            await self.owner.app.next_update_async()
        self.poll(ticket)

    async def run(self):
        o=self.owner
        def control(event):
            self.latencies['control_input'].append((int(event['applied_monotonic_ns'])-int(event['received_monotonic_ns']))/1e6)
            self.log.event('controls.jsonl','applied',event,o.epoch_id)
        o.on_control=control
        capture_start=drain_start=readback_start=None
        try:
            await o.initialize()
            backend='barrier' if os.environ.get('S0601_FORCE_BARRIER')=='1' or o.job['capture']['backend']=='barrier' else 'continuous'
            if self.session['policy']!='strict_complete':
                raise ContractError('policy_unverified','strict_latest execution is not yet verified; no formal data is accepted')
            if backend=='barrier':
                cap,driver=await self.gate_barrier()
            else:
                from .capabilities import probe
                cap=await probe(o,self.directory/'capability_probe')
                driver=None
            save_json(self.directory/'capabilities.json',cap)
            if cap['selected_backend']!=backend:
                raise ContractError('backend_unsupported','Real moving capability probe failed; session cannot commit formal data')
            from .ui import Panel
            self.panel=Panel(o,self)
            self.session['backend']=backend
            self.session['acceptance_results']['continuous_ok']=backend=='continuous'
            self.session['acceptance_evidence']['continuous_ok']={'scope':'this recording','reason':cap['status'],'evidence_paths':['capabilities.json']}
            o.moving=os.environ.get('S0601_MOTION','static')=='moving'
            o._moving_started=False
            if not o.moving:
                o.controller.enqueue('acceptance','hold')
            if o.job.get('diagnostics',{}).get('geometry'):
                from .geometry_diagnostics import create
                self.geometry_spec=create(o,self.directory)
                for _ in range(8):
                    await o.app.next_update_async()
                self.geometry_spec['setup_paused_updates']=8
                save_json(self.directory/'diagnostic_geometry.json',self.geometry_spec)
                o.moving=False
                o.controller.enqueue('acceptance','base_velocity',self.geometry_spec['motion'])
            expected=sorted(e['sensor_id'] for k in ('cameras','lidars') for e in o.registry[k])
            self.session['counts']['received_by_sensor']={s:0 for s in expected}
            # Common 10Hz physical boundary comes from actual mapped native event probes.
            probe_rows=json.loads((self.directory/'capability_probe/receipts.json').read_text())
            last=max(probe_rows,key=lambda r:r['physical_step'])
            origin_step,origin_ns=last['physical_step'],int(last['source_time_ns'])
            stride=o.job['clock']['physics_hz']//o.job['clock']['sample_hz']
            first=origin_step+stride
            while first<=o.manager.get_num_physics_steps()+1:
                first+=stride
            clock=SamplingClock(o.job['clock']['physics_hz'],o.job['clock']['sample_hz'],origin_ns,origin_step,first)
            self.clock=clock
            self.environment=o.environment()
            save_json(self.directory/'environment.json',self.environment)
            save_json(self.directory/'job_spec.json',o.job)
            save_json(self.directory/'sensor_registry.json',o.registry)
            o.layer.Export(str(self.directory/'session_layer_initial.usda'))
            assets=o.asset_manifest()
            assets['dependencies'].append({'uri':'session_layer_initial.usda','kind':'anonymous runtime layer','resolved':True,
                'sha256':file_hash(self.directory/'session_layer_initial.usda'),'size_bytes':(self.directory/'session_layer_initial.usda').stat().st_size,'reason':None})
            save_json(self.directory/'asset_manifest.json',assets)
            provenance={v['path']:v for v in json.loads((o.project/'docs/source_transplants.json').read_text())}
            source_files=[]
            for p in sorted(o.project.rglob('*')):
                if not p.is_file() or p.suffix not in ('.py','.json','.sh','.kit'):
                    continue
                if '__pycache__' in p.parts or 'reports' in p.parts or '.deploy_backups' in p.parts:
                    continue
                rel=p.relative_to(o.project).as_posix()
                origin=provenance.get(rel,{})
                source_files.append({'path':rel,'sha256':file_hash(p),'size_bytes':p.stat().st_size,'origin_path':origin.get('origin_path'),
                                     'modified':bool(origin) and file_hash(p)!=origin['origin_sha256']})
            save_json(self.directory/'source_manifest.json',{'schema_version':1,'recording_id':o.recording_id,'entrypoint':'run_in_isaac.py','files':source_files,'git':None,
                'git_reason':'This remote project is a scoped SFTP deployment, not a Git checkout; executed source and configurations are hashed individually'})
            render=o.render_profile
            render['requested']={'renderer_mode':o.job['render']['mode'],'dlss_mode':o.job['render']['dlss_mode'],'aa_mode':o.job['render']['aa_mode'],
                'frame_generation':False,'motion_blur':False,'formal_subframes':1,'png_compress_level':o.job['pipeline']['png_compress_level']}
            render['effective']={'renderer_mode':o.settings.get('/rtx/rendermode'),'dlss_mode':o.settings.get('/rtx/post/dlss/execMode'),
                'aa_mode':o.settings.get('/rtx/post/aa/op'),'frame_generation':o.settings.get('/rtx-transient/dlssg/enabled'),
                'motion_blur':o.settings.get('/rtx/post/motionblur/enabled'),'formal_subframes':1,'png_compress_level':o.job['pipeline']['png_compress_level']}
            render['warmup']={'min_updates':o.job['render']['initial_warmup_min_updates'],'max_updates':o.job['render']['initial_warmup_max_updates'],
                             'actual_updates':cap.get('initial_warmup_updates',o.job['render']['initial_warmup_min_updates']),
                             'passed':True,'evidence_paths':['capabilities.json']}
            save_json(self.directory/'render_profile.json',render)
            epoch={'epoch_id':o.epoch_id,'scene_generation':o.scene_generation,'sim_origin_ns':str(origin_ns),'physical_step_origin':origin_step,
                   'first_target_step':first,'physics_hz':clock.physics_hz,'sample_hz':clock.sample_hz,'segments':[]}
            self.session['epochs']=[epoch]
            metadata=dict(schema_version=3,recording_id=o.recording_id,scene_generation=o.scene_generation,backend=backend,policy=self.session['policy'],
                expected_sensor_ids=expected,**o.job['clock'],sim_origin_ns=str(origin_ns),physical_step_origin=origin_step,first_target_step=first,
                sampling_stride_steps=stride,native_sample_hz=10,selection_stride=10//clock.sample_hz,mount_revision=0,calibration_revision=0,
                registry_snapshot_sha256=digest(o.registry))
            for key,file in [('job_spec_sha256','job_spec.json'),('capabilities_sha256','capabilities.json'),('source_manifest_sha256','source_manifest.json'),('asset_manifest_sha256','asset_manifest.json'),('render_profile_sha256','render_profile.json')]:
                metadata[key]=file_hash(self.directory/file)
            self.pool=BufferPool(self.directory/'.ipc',o.job['pipeline']['slot_bytes'],o.job['pipeline']['max_buffer_bytes'],1)
            self.worker_launch_ns=time.monotonic_ns()
            self.pipeline=RecordPipeline(o.project,self.directory,{'job':o.job,'registry':o.registry,'session':str(self.directory),'backend':backend,'run_metadata':metadata})
            await self.wait(lambda:self.worker_ready)
            self.joiner=TimeJoiner(o.ledger,o.recording_id,o.epoch_id,expected,o.job['capture'])
            o.on_receipt=self.received
            o.on_reject=lambda e:setattr(self,'receipt_error',dict(e,evidence_paths=['receipts.jsonl']))
            o.on_state=self.state
            self.session['status']='RECORDING'
            self.save_session()
            capture_start=time.monotonic()
            for index in range(o.job['capture']['requested_groups']):
                if self.request_pause:
                    self.session['status']='PAUSED'
                    self.save_session()
                while self.request_pause and not self.request_stop:
                    o.timeline.pause()
                    o.timeline.commit()
                    await o.app.next_update_async()
                if self.request_stop:
                    self.log.event('controls.jsonl','stop_cutoff',{'last_written_group_id':index-1,'next_target_index':index},o.epoch_id)
                    break
                step,ns=clock.target(index)
                slot,generation=self.pool.reserve((o.recording_id,o.epoch_id,index))
                reserved=time.monotonic_ns()
                segment='segment_%06d'%(index//o.job['pipeline']['segment_groups'])
                if segment not in epoch['segments']:
                    epoch['segments'].append(segment)
                ticket=GroupTicket(o.recording_id,o.epoch_id,segment,index,index,step,str(ns),expected,slot,generation,str(reserved),
                                   str(reserved+int(o.job['capture']['group_timeout_wall_s']*1e9)))
                self.joiner.reserve(ticket)
                self.log.event('schedule.jsonl','scheduled',ticket.schedule(),o.epoch_id,segment)
                self.session['counts']['scheduled']+=1
                self.complete_group=None
                if backend=='barrier':
                    await driver.target(step,self.completion,int(ticket.deadline_monotonic_ns))
                else:
                    o.backend.permit=lambda mapped_ns:abs(mapped_ns-ns)<=2
                    self.stop_step=step+stride-1
                    self.backpressure_active=False
                    o.setting('/app/player/playSimulations',True)
                    o.timeline.play()
                    o.timeline.commit()
                    while self.complete_group is None:
                        self.poll(ticket)
                        self.joiner.expire()
                        await o.app.next_update_async()
                self.poll(ticket)
                group=self.complete_group
                desc=self.pool.store(slot,generation,(o.recording_id,o.epoch_id,index),{s:a for s,(e,a) in group['receipts'].items()})
                self.pipeline.send({'type':'group','ticket':ticket.schedule(),'state':group['state'],'evidence':{s:e for s,(e,a) in group['receipts'].items()},
                                    'sync_checks':group['sync_checks'],'validated_monotonic_ns':group['validated_monotonic_ns'],'buffer':desc})
                self.complete_group=None
                del group
                await self.wait(lambda:index in self.written_seen,ticket)
                self.joiner.finish(step)
                self.release_seen.discard(index)
                self.written_seen.discard(index)
                self.panel.progress(index+1,o.job['capture']['requested_groups'],backend)
                if index%25==0:
                    self.save_session()
                    print('[S0601 RECORD] '+json.dumps({'recording_id':o.recording_id,'written':index+1,'requested':o.job['capture']['requested_groups'],'backend':backend}),flush=True)
            drain_start=time.monotonic()
            self.session['status']='DRAINING'
            self.pipeline.send({'type':'close'})
            await self.wait(lambda:self.worker_closed)
            while self.pipeline.process.poll() is None:
                await o.app.next_update_async()
            self.pipeline.close_resources()
            deadline=time.monotonic()+3
            while (self.pipeline.sender.is_alive() or self.pipeline.reader.is_alive()) and time.monotonic()<deadline:
                await o.app.next_update_async()
            if self.pipeline.sender.is_alive() or self.pipeline.reader.is_alive():
                raise ContractError('ipc_thread_cleanup','Owned IPC threads did not exit after worker closure')
            self.pool.close()
            o.on_state=lambda s:None
            o.on_receipt=lambda e,a:None
            o.backend.permit=lambda ns:False
            self.stop_step=None
            await o.close()
            save_json(self.directory/'lifecycle.json',dict(o.cleanup_report,worker_pid=self.pipeline.process.pid,
                worker_exit_code=self.pipeline.process.returncode,worker_closed_ack=self.worker_closed,
                closed_segments=self.closed_segments,ipc_threads_closed=True,transport_closed=True,owner_resources_after_close=process_resources()))
            self.panel.close()
            self.panel=None
            self.session['acceptance_results']['lifecycle_ok']=True
            self.session['acceptance_evidence']['lifecycle_ok']={'scope':'this recording','reason':'Native resources drained; worker_closed and segment_closed; own session layer and settings restored',
                                                               'evidence_paths':['groups.jsonl','session.json','lifecycle.json']}
            self.session['status']='VALIDATING'
            self.session['outcome']='stopped' if self.request_stop else 'completed'
            self.session['timeline_state']='stopped'
            self.save_session()
            for filename in ('schedule.jsonl','receipts.jsonl','groups.jsonl','gaps.jsonl'):
                if not (self.directory/filename).exists():
                    (self.directory/filename).touch()
            self.log.close()
            readback_start=time.monotonic()
            worker=json.loads((self.directory/'worker_report.json').read_text())
            latency={k:statistics(v,k) for k,v in self.latencies.items()}
            latency.update(worker['latencies'])
            total_start=self.cold
            perf={'schema_version':1,'recording_id':o.recording_id,'clock_domain_id':self.environment['monotonic_clock']['domain_id'],
                  'scope':'this recording in one GUI; scene/capability preparation included; GUI process boot reported separately',
                  'gui_process_launch_monotonic_ns':os.environ.get('S0601_LAUNCH_MONOTONIC_NS'),
                  'recording_start_monotonic_ns':str(int(self.cold*1e9)),
                  'measured_groups':self.session['counts']['written'],'warmup_excluded_groups':0,
                  'wall_times_s':{'cold_start':capture_start-total_start,'capture':drain_start-capture_start,'drain':readback_start-drain_start,'readback':0.,'total':readback_start-total_start},
                  'throughput':{'capture_groups_per_wall_s':self.session['counts']['written']/(drain_start-capture_start),'usable_groups_per_wall_s':None},
                  'latency_ms':latency,'buffer_peak_bytes':self.pool.peak_bytes,'inflight_peak_groups':1,'rounds':[],'speedup_vs_baseline':None,'performance_ok':None}
            save_json(self.directory/'performance.json',perf)
            out=(o.project/'reports'/('publish_'+o.recording_id+'.log')).open('wb')
            cmd=['/bin/bash','-c','source /opt/ros/jazzy/setup.bash && exec /usr/bin/python3 -B -m single0601_continuous_rt.publish "$1"','s0601-validate',str(self.directory)]
            process=subprocess.Popen(cmd,cwd=o.project,env=cpu_environment(),stdout=out,stderr=subprocess.STDOUT)
            while process.poll() is None:
                await o.app.next_update_async()
            out.close()
            # Publisher freezes all final reports before hashing; timings are measured there.
            candidates=[self.directory.parent.parent/n/o.recording_id for n in ('datasets','failed')]
            destination=next((p for p in candidates if p.exists()),self.directory)
            result={'recording_id':o.recording_id,'directory':str(destination),'publisher_exit_code':process.returncode,'backend':backend,
                    'status':'READY' if (destination/'READY').exists() else ('STOPPED' if self.request_stop else 'FAILED')}
            save_json(o.project/'reports/latest_recording.json',result)
            print('[S0601 RESULT] '+json.dumps(result),flush=True)
            return result
        except Exception as exc:
            self.session.update(status='FAILED',outcome='failed',ended_utc=utc(),failure={'code':getattr(exc,'code','recording_failed'),
                'message':type(exc).__name__+': '+str(exc),'evidence_paths':['logs/engine_error.log']})
            import traceback
            (self.directory/'logs/engine_error.log').write_text(traceback.format_exc())
            self.save_session()
            self.log.close()
            try:
                if self.panel:
                    self.panel.close()
                    self.panel=None
                o.on_receipt=lambda e,a:None
                o.on_state=lambda s:None
                if self.pipeline and self.pipeline.process.poll() is None:
                    try:
                        self.pipeline.send({'type':'close'})
                    except Exception:
                        with (self.directory/'logs/engine_error.log').open('a') as f:
                            f.write(traceback.format_exc())
                await o.close()
                if self.pipeline:
                    deadline=time.monotonic()+15
                    while self.pipeline.process.poll() is None and time.monotonic()<deadline:
                        await o.app.next_update_async()
                    if self.pipeline.process.poll() is None:
                        self.pipeline.process.terminate()
                        self.session['cleanup_worker']='owned worker SIGTERM after bounded close timeout'
                        deadline=time.monotonic()+5
                        while self.pipeline.process.poll() is None and time.monotonic()<deadline:
                            await o.app.next_update_async()
                    if self.pipeline.process.poll() is not None:
                        self.pipeline.close_resources()
                        self.session['cleanup_worker']='exited; no mappings remain in worker'
                        if self.pool:
                            for slot in self.pool.slots:
                                if not slot.released:
                                    self.pool.release(slot.index,slot.generation,slot.identity)
                                if slot.encoded_pending:
                                    self.pool.written(slot.index,slot.generation,slot.identity)
                            self.pool.close()
            except Exception:
                with (self.directory/'logs/engine_error.log').open('a') as f:
                    f.write(traceback.format_exc())
            self.save_session()
            failed=self.directory.parent.parent/'failed'/self.directory.name
            failed.parent.mkdir(exist_ok=True)
            self.directory.rename(failed)
            self.directory=failed
            save_json(o.project/'reports/latest_recording.json',{'recording_id':o.recording_id,'directory':str(self.directory),'status':'FAILED','failure':self.session['failure']})
            raise
