"""Preregistered nominal model; stochastic angular error is not fitted away."""
import numpy as np
def rays(params,arrays,header,valid):
 def value(k,default=None):return params.get('omni:sensor:Core:'+k,{}).get('value',default)
 prefix='emitterState:s001:';ids=arrays['emitter_id'][valid]
 az=np.asarray(value(prefix+'azimuthDeg'),float)[ids]
 el=np.asarray(value(prefix+'elevationDeg'),float)[ids]
 errors=[]
 for name in ('horOffsetM','vertOffsetM','distanceCorrectionM'):
  if np.any(np.asarray(value(prefix+name,[]))):errors.append('unsupported nonzero '+name)
 state_names={k.split(':')[4] for k in params if k.startswith('omni:sensor:Core:emitterState:')}
 if state_names!={'s001'}:errors.append('multiple emitter states require model extension')
 scan=value('scanType');fire=np.asarray(value(prefix+'fireTimeNs'),float)[ids]
 if scan=='ROTARY':
  rate=value('patternFiringRateHz');scanrate=value('scanRateBaseHz');direction=value('rotationDirection')
  if not rate or not scanrate or direction not in ('CW','CCW'):raise ValueError('Rotary cadence/direction contract missing')
  tick=arrays['tick_id'][valid].astype(float)
  rotational=360.*scanrate*(tick/rate+fire*1e-9)
  az=az+value('startAzimuthOffsetDeg',0.)+(rotational if direction=='CW' else -rotational)
 else:
  if np.any(fire):errors.append('solid-state nonzero emitter time unsupported')
 az=np.deg2rad(az);el=np.deg2rad(el)
 nominal=np.column_stack((np.cos(el)*np.cos(az),-np.cos(el)*np.sin(az),np.sin(el)))
 return nominal,{'structural_qualified':not errors,'errors':errors,'scan_type':scan,'rotary_fire_time_included':scan=='ROTARY',
  'angular_noise_std_deg':[value('azimuthErrorStd'),value('elevationErrorStd')],'noise_policy':'preserved; static numeric threshold unchanged; no per-point noise fitting'}
