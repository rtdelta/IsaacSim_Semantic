from __future__ import annotations
import isaacsim.sensors.experimental.rtx.generic_model_output._rtx_sensors_gmo
import typing

__all__ = [
    "AccessType",
    "AuxType",
    "CoordsType",
    "ElementFlags",
    "FrameAtTime",
    "FrameOfReference",
    "GMOIOConfig",
    "GenericModelOutput",
    "GenericModelOutputIOFactory",
    "IDSAuxHas",
    "IGenericModelOutputIO",
    "LidarAuxHas",
    "Modality",
    "MotionCompensationState",
    "OutputType",
    "getMagicNumberGMO",
    "getModelOutputFromBuffer"
]


class AccessType():
    """
    Members:

      READ

      RECORD_BASIC

      RECORD_FULL
    """
    def __eq__(self, other: object) -> bool: ...
    def __getstate__(self) -> int: ...
    def __hash__(self) -> int: ...
    def __index__(self) -> int: ...
    def __init__(self, value: int) -> None: ...
    def __int__(self) -> int: ...
    def __ne__(self, other: object) -> bool: ...
    def __repr__(self) -> str: ...
    def __setstate__(self, state: int) -> None: ...
    @property
    def name(self) -> str:
        """
        :type: str
        """
    @property
    def value(self) -> int:
        """
        :type: int
        """
    READ: isaacsim.sensors.experimental.rtx.generic_model_output._rtx_sensors_gmo.AccessType # value = <AccessType.READ: 0>
    RECORD_BASIC: isaacsim.sensors.experimental.rtx.generic_model_output._rtx_sensors_gmo.AccessType # value = <AccessType.RECORD_BASIC: 1>
    RECORD_FULL: isaacsim.sensors.experimental.rtx.generic_model_output._rtx_sensors_gmo.AccessType # value = <AccessType.RECORD_FULL: 2>
    __members__: dict # value = {'READ': <AccessType.READ: 0>, 'RECORD_BASIC': <AccessType.RECORD_BASIC: 1>, 'RECORD_FULL': <AccessType.RECORD_FULL: 2>}
    pass
class AuxType():
    """
    Members:

      NONE

      BASIC

      EXTRA

      FULL
    """
    def __eq__(self, other: object) -> bool: ...
    def __getstate__(self) -> int: ...
    def __hash__(self) -> int: ...
    def __index__(self) -> int: ...
    def __init__(self, value: int) -> None: ...
    def __int__(self) -> int: ...
    def __ne__(self, other: object) -> bool: ...
    def __repr__(self) -> str: ...
    def __setstate__(self, state: int) -> None: ...
    @property
    def name(self) -> str:
        """
        :type: str
        """
    @property
    def value(self) -> int:
        """
        :type: int
        """
    BASIC: isaacsim.sensors.experimental.rtx.generic_model_output._rtx_sensors_gmo.AuxType # value = <AuxType.BASIC: 1>
    EXTRA: isaacsim.sensors.experimental.rtx.generic_model_output._rtx_sensors_gmo.AuxType # value = <AuxType.EXTRA: 2>
    FULL: isaacsim.sensors.experimental.rtx.generic_model_output._rtx_sensors_gmo.AuxType # value = <AuxType.FULL: 3>
    NONE: isaacsim.sensors.experimental.rtx.generic_model_output._rtx_sensors_gmo.AuxType # value = <AuxType.NONE: 0>
    __members__: dict # value = {'NONE': <AuxType.NONE: 0>, 'BASIC': <AuxType.BASIC: 1>, 'EXTRA': <AuxType.EXTRA: 2>, 'FULL': <AuxType.FULL: 3>}
    pass
class CoordsType():
    """
    Members:

      CARTESIAN

      SPHERICAL

      NOT_APPLICABLE
    """
    def __eq__(self, other: object) -> bool: ...
    def __getstate__(self) -> int: ...
    def __hash__(self) -> int: ...
    def __index__(self) -> int: ...
    def __init__(self, value: int) -> None: ...
    def __int__(self) -> int: ...
    def __ne__(self, other: object) -> bool: ...
    def __repr__(self) -> str: ...
    def __setstate__(self, state: int) -> None: ...
    @property
    def name(self) -> str:
        """
        :type: str
        """
    @property
    def value(self) -> int:
        """
        :type: int
        """
    CARTESIAN: isaacsim.sensors.experimental.rtx.generic_model_output._rtx_sensors_gmo.CoordsType # value = <CoordsType.CARTESIAN: 0>
    NOT_APPLICABLE: isaacsim.sensors.experimental.rtx.generic_model_output._rtx_sensors_gmo.CoordsType # value = <CoordsType.NOT_APPLICABLE: 2>
    SPHERICAL: isaacsim.sensors.experimental.rtx.generic_model_output._rtx_sensors_gmo.CoordsType # value = <CoordsType.SPHERICAL: 1>
    __members__: dict # value = {'CARTESIAN': <CoordsType.CARTESIAN: 0>, 'SPHERICAL': <CoordsType.SPHERICAL: 1>, 'NOT_APPLICABLE': <CoordsType.NOT_APPLICABLE: 2>}
    pass
class ElementFlags():
    """
    Members:

      FLAG_1

      FLAG_2

      FLAG_3

      FLAG_4

      FLAG_5

      FLAG_6

      FLAG_7

      VALID
    """
    def __eq__(self, other: object) -> bool: ...
    def __getstate__(self) -> int: ...
    def __hash__(self) -> int: ...
    def __index__(self) -> int: ...
    def __init__(self, value: int) -> None: ...
    def __int__(self) -> int: ...
    def __ne__(self, other: object) -> bool: ...
    def __repr__(self) -> str: ...
    def __setstate__(self, state: int) -> None: ...
    @property
    def name(self) -> str:
        """
        :type: str
        """
    @property
    def value(self) -> int:
        """
        :type: int
        """
    FLAG_1: isaacsim.sensors.experimental.rtx.generic_model_output._rtx_sensors_gmo.ElementFlags # value = <ElementFlags.FLAG_1: 0>
    FLAG_2: isaacsim.sensors.experimental.rtx.generic_model_output._rtx_sensors_gmo.ElementFlags # value = <ElementFlags.FLAG_2: 1>
    FLAG_3: isaacsim.sensors.experimental.rtx.generic_model_output._rtx_sensors_gmo.ElementFlags # value = <ElementFlags.FLAG_3: 2>
    FLAG_4: isaacsim.sensors.experimental.rtx.generic_model_output._rtx_sensors_gmo.ElementFlags # value = <ElementFlags.FLAG_4: 4>
    FLAG_5: isaacsim.sensors.experimental.rtx.generic_model_output._rtx_sensors_gmo.ElementFlags # value = <ElementFlags.FLAG_5: 8>
    FLAG_6: isaacsim.sensors.experimental.rtx.generic_model_output._rtx_sensors_gmo.ElementFlags # value = <ElementFlags.FLAG_6: 16>
    FLAG_7: isaacsim.sensors.experimental.rtx.generic_model_output._rtx_sensors_gmo.ElementFlags # value = <ElementFlags.FLAG_7: 32>
    VALID: isaacsim.sensors.experimental.rtx.generic_model_output._rtx_sensors_gmo.ElementFlags # value = <ElementFlags.VALID: 64>
    __members__: dict # value = {'FLAG_1': <ElementFlags.FLAG_1: 0>, 'FLAG_2': <ElementFlags.FLAG_2: 1>, 'FLAG_3': <ElementFlags.FLAG_3: 2>, 'FLAG_4': <ElementFlags.FLAG_4: 4>, 'FLAG_5': <ElementFlags.FLAG_5: 8>, 'FLAG_6': <ElementFlags.FLAG_6: 16>, 'FLAG_7': <ElementFlags.FLAG_7: 32>, 'VALID': <ElementFlags.VALID: 64>}
    pass
class FrameAtTime():
    def __init__(self) -> None: ...
    @property
    def orientation(self) -> typing.List[float]:
        """
        :type: typing.List[float]
        """
    @orientation.setter
    def orientation(self, arg1: typing.List[float]) -> None:
        pass
    @property
    def posM(self) -> typing.List[float]:
        """
        :type: typing.List[float]
        """
    @posM.setter
    def posM(self, arg1: typing.List[float]) -> None:
        pass
    @property
    def timestampNs(self) -> int:
        """
        :type: int
        """
    @timestampNs.setter
    def timestampNs(self, arg0: int) -> None:
        pass
    pass
class FrameOfReference():
    """
    Members:

      SENSOR

      WORLD

      CUSTOM

      PARENT
    """
    def __eq__(self, other: object) -> bool: ...
    def __getstate__(self) -> int: ...
    def __hash__(self) -> int: ...
    def __index__(self) -> int: ...
    def __init__(self, value: int) -> None: ...
    def __int__(self) -> int: ...
    def __ne__(self, other: object) -> bool: ...
    def __repr__(self) -> str: ...
    def __setstate__(self, state: int) -> None: ...
    @property
    def name(self) -> str:
        """
        :type: str
        """
    @property
    def value(self) -> int:
        """
        :type: int
        """
    CUSTOM: isaacsim.sensors.experimental.rtx.generic_model_output._rtx_sensors_gmo.FrameOfReference # value = <FrameOfReference.CUSTOM: 2>
    PARENT: isaacsim.sensors.experimental.rtx.generic_model_output._rtx_sensors_gmo.FrameOfReference # value = <FrameOfReference.PARENT: 3>
    SENSOR: isaacsim.sensors.experimental.rtx.generic_model_output._rtx_sensors_gmo.FrameOfReference # value = <FrameOfReference.SENSOR: 0>
    WORLD: isaacsim.sensors.experimental.rtx.generic_model_output._rtx_sensors_gmo.FrameOfReference # value = <FrameOfReference.WORLD: 1>
    __members__: dict # value = {'SENSOR': <FrameOfReference.SENSOR: 0>, 'WORLD': <FrameOfReference.WORLD: 1>, 'CUSTOM': <FrameOfReference.CUSTOM: 2>, 'PARENT': <FrameOfReference.PARENT: 3>}
    pass
class GMOIOConfig():
    def __del__(self) -> None: ...
    def __init__(self) -> None: ...
    @property
    def accessType(self) -> AccessType:
        """
        :type: AccessType
        """
    @accessType.setter
    def accessType(self, arg0: AccessType) -> None:
        pass
    @property
    def clientName(self) -> str:
        """
        :type: str
        """
    @clientName.setter
    def clientName(self, arg1: str) -> None:
        pass
    @property
    def fileName(self) -> str:
        """
        :type: str
        """
    @fileName.setter
    def fileName(self, arg1: str) -> None:
        pass
    @property
    def groupName(self) -> str:
        """
        :type: str
        """
    @groupName.setter
    def groupName(self, arg1: str) -> None:
        pass
    @property
    def loop(self) -> bool:
        """
        :type: bool
        """
    @loop.setter
    def loop(self, arg0: bool) -> None:
        pass
    @property
    def maxPoints(self) -> int:
        """
        :type: int
        """
    @maxPoints.setter
    def maxPoints(self, arg0: int) -> None:
        pass
    @property
    def onlyValid(self) -> bool:
        """
        :type: bool
        """
    @onlyValid.setter
    def onlyValid(self, arg0: bool) -> None:
        pass
    pass
class GenericModelOutput():
    def __init__(self) -> None: ...
    @property
    def auxType(self) -> AuxType:
        """
        :type: AuxType
        """
    @auxType.setter
    def auxType(self, arg0: AuxType) -> None:
        pass
    @property
    def azimuthOffset(self) -> float:
        """
        :type: float
        """
    @property
    def channelId(self) -> numpy.ndarray:
        """
        :type: numpy.ndarray
        """
    @property
    def cycleCnt(self) -> int:
        """
        :type: int
        """
    @property
    def echoId(self) -> numpy.ndarray:
        """
        :type: numpy.ndarray
        """
    @property
    def elementsCoordsType(self) -> CoordsType:
        """
        :type: CoordsType
        """
    @elementsCoordsType.setter
    def elementsCoordsType(self, arg0: CoordsType) -> None:
        pass
    @property
    def emitterId(self) -> numpy.ndarray:
        """
        :type: numpy.ndarray
        """
    @property
    def filledAuxMembers(self) -> LidarAuxHas:
        """
        :type: LidarAuxHas
        """
    @property
    def flags(self) -> numpy.ndarray:
        """
        :type: numpy.ndarray
        """
    @property
    def frameEnd(self) -> FrameAtTime:
        """
        :type: FrameAtTime
        """
    @frameEnd.setter
    def frameEnd(self, arg0: FrameAtTime) -> None:
        pass
    @property
    def frameId(self) -> int:
        """
        :type: int
        """
    @frameId.setter
    def frameId(self, arg0: int) -> None:
        pass
    @property
    def frameOfReference(self) -> FrameOfReference:
        """
        :type: FrameOfReference
        """
    @frameOfReference.setter
    def frameOfReference(self, arg0: FrameOfReference) -> None:
        pass
    @property
    def frameStart(self) -> FrameAtTime:
        """
        :type: FrameAtTime
        """
    @frameStart.setter
    def frameStart(self, arg0: FrameAtTime) -> None:
        pass
    @property
    def hitNormals(self) -> numpy.ndarray:
        """
        :type: numpy.ndarray
        """
    @property
    def idsFilledAuxMembers(self) -> IDSAuxHas:
        """
        :type: IDSAuxHas
        """
    @property
    def idsVelocities(self) -> numpy.ndarray:
        """
        :type: numpy.ndarray
        """
    @property
    def magicNumber(self) -> int:
        """
        :type: int
        """
    @magicNumber.setter
    def magicNumber(self, arg0: int) -> None:
        pass
    @property
    def majorVersion(self) -> int:
        """
        :type: int
        """
    @majorVersion.setter
    def majorVersion(self, arg0: int) -> None:
        pass
    @property
    def matId(self) -> numpy.ndarray:
        """
        :type: numpy.ndarray
        """
    @property
    def materialId(self) -> numpy.ndarray:
        """
        :type: numpy.ndarray
        """
    @property
    def maxAzRad(self) -> float:
        """
        :type: float
        """
    @property
    def maxElRad(self) -> float:
        """
        :type: float
        """
    @property
    def maxRangeM(self) -> float:
        """
        :type: float
        """
    @property
    def maxVelMps(self) -> float:
        """
        :type: float
        """
    @property
    def minAzRad(self) -> float:
        """
        :type: float
        """
    @property
    def minElRad(self) -> float:
        """
        :type: float
        """
    @property
    def minVelMps(self) -> float:
        """
        :type: float
        """
    @property
    def minorVersion(self) -> int:
        """
        :type: int
        """
    @minorVersion.setter
    def minorVersion(self, arg0: int) -> None:
        pass
    @property
    def modality(self) -> Modality:
        """
        :type: Modality
        """
    @modality.setter
    def modality(self, arg0: Modality) -> None:
        pass
    @property
    def modelToAppTransform(self) -> numpy.ndarray:
        """
        :type: numpy.ndarray
        """
    @property
    def motionCompensationState(self) -> MotionCompensationState:
        """
        :type: MotionCompensationState
        """
    @motionCompensationState.setter
    def motionCompensationState(self, arg0: MotionCompensationState) -> None:
        pass
    @property
    def numCols(self) -> int:
        """
        :type: int
        """
    @property
    def numElements(self) -> int:
        """
        :type: int
        """
    @numElements.setter
    def numElements(self, arg0: int) -> None:
        pass
    @property
    def numRows(self) -> int:
        """
        :type: int
        """
    @property
    def numSamplesPerSgw(self) -> int:
        """
        :type: int
        """
    @property
    def numSgws(self) -> int:
        """
        :type: int
        """
    @property
    def objId(self) -> numpy.ndarray:
        """
        :type: numpy.ndarray
        """
    @property
    def objectId(self) -> numpy.ndarray:
        """
        :type: numpy.ndarray
        """
    @property
    def originX(self) -> numpy.ndarray:
        """
        :type: numpy.ndarray
        """
    @property
    def originY(self) -> numpy.ndarray:
        """
        :type: numpy.ndarray
        """
    @property
    def originZ(self) -> numpy.ndarray:
        """
        :type: numpy.ndarray
        """
    @property
    def outputType(self) -> OutputType:
        """
        :type: OutputType
        """
    @outputType.setter
    def outputType(self, arg0: OutputType) -> None:
        pass
    @property
    def patchVersion(self) -> int:
        """
        :type: int
        """
    @patchVersion.setter
    def patchVersion(self, arg0: int) -> None:
        pass
    @property
    def rv_ms(self) -> numpy.ndarray:
        """
        :type: numpy.ndarray
        """
    @property
    def scalar(self) -> numpy.ndarray:
        """
        :type: numpy.ndarray
        """
    @property
    def scanComplete(self) -> int:
        """
        :type: int
        """
    @property
    def scanIdx(self) -> int:
        """
        :type: int
        """
    @property
    def sensorID(self) -> int:
        """
        :type: int
        """
    @property
    def sizeInBytes(self) -> int:
        """
        :type: int
        """
    @sizeInBytes.setter
    def sizeInBytes(self, arg0: int) -> None:
        pass
    @property
    def tickId(self) -> numpy.ndarray:
        """
        :type: numpy.ndarray
        """
    @property
    def tickStates(self) -> numpy.ndarray:
        """
        :type: numpy.ndarray
        """
    @property
    def timeOffSetNs(self) -> numpy.ndarray:
        """
        :type: numpy.ndarray
        """
    @property
    def timeOffsetNs(self) -> numpy.ndarray:
        """
        :type: numpy.ndarray
        """
    @property
    def timestampNs(self) -> int:
        """
        :type: int
        """
    @timestampNs.setter
    def timestampNs(self, arg0: int) -> None:
        pass
    @property
    def velocities(self) -> numpy.ndarray:
        """
        :type: numpy.ndarray
        """
    @property
    def x(self) -> numpy.ndarray:
        """
        :type: numpy.ndarray
        """
    @property
    def y(self) -> numpy.ndarray:
        """
        :type: numpy.ndarray
        """
    @property
    def z(self) -> numpy.ndarray:
        """
        :type: numpy.ndarray
        """
    pass
class GenericModelOutputIOFactory():
    def __init__(self) -> None: ...
    @staticmethod
    def createInstance() -> IGenericModelOutputIO: ...
    pass
class IDSAuxHas():
    """
    Members:

      NONE

      VELOCITIES
    """
    def __eq__(self, other: object) -> bool: ...
    def __getstate__(self) -> int: ...
    def __hash__(self) -> int: ...
    def __index__(self) -> int: ...
    def __init__(self, value: int) -> None: ...
    def __int__(self) -> int: ...
    def __ne__(self, other: object) -> bool: ...
    def __repr__(self) -> str: ...
    def __setstate__(self, state: int) -> None: ...
    @property
    def name(self) -> str:
        """
        :type: str
        """
    @property
    def value(self) -> int:
        """
        :type: int
        """
    NONE: isaacsim.sensors.experimental.rtx.generic_model_output._rtx_sensors_gmo.IDSAuxHas # value = <IDSAuxHas.NONE: 0>
    VELOCITIES: isaacsim.sensors.experimental.rtx.generic_model_output._rtx_sensors_gmo.IDSAuxHas # value = <IDSAuxHas.VELOCITIES: 1>
    __members__: dict # value = {'NONE': <IDSAuxHas.NONE: 0>, 'VELOCITIES': <IDSAuxHas.VELOCITIES: 1>}
    pass
class IGenericModelOutputIO():
    def __init__(self) -> None: ...
    def addPacket(self, arg0: capsule, arg1: int) -> None: ...
    def init(self, arg0: GMOIOConfig) -> None: ...
    def readModelOutput(self, clientName: str = '', frameId: int = -1) -> GenericModelOutput: ...
    def writeModelOutput(self, arg0: GenericModelOutput) -> None: ...
    pass
class LidarAuxHas():
    """
    Members:

      NONE

      EMITTER_ID

      CHANNEL_ID

      ECHO_ID

      MAT_ID

      OBJ_ID

      TICK_ID

      TICK_STATES

      HIT_NORMALS

      VELOCITIES
    """
    def __eq__(self, other: object) -> bool: ...
    def __getstate__(self) -> int: ...
    def __hash__(self) -> int: ...
    def __index__(self) -> int: ...
    def __init__(self, value: int) -> None: ...
    def __int__(self) -> int: ...
    def __ne__(self, other: object) -> bool: ...
    def __repr__(self) -> str: ...
    def __setstate__(self, state: int) -> None: ...
    @property
    def name(self) -> str:
        """
        :type: str
        """
    @property
    def value(self) -> int:
        """
        :type: int
        """
    CHANNEL_ID: isaacsim.sensors.experimental.rtx.generic_model_output._rtx_sensors_gmo.LidarAuxHas # value = <LidarAuxHas.CHANNEL_ID: 2>
    ECHO_ID: isaacsim.sensors.experimental.rtx.generic_model_output._rtx_sensors_gmo.LidarAuxHas # value = <LidarAuxHas.ECHO_ID: 4>
    EMITTER_ID: isaacsim.sensors.experimental.rtx.generic_model_output._rtx_sensors_gmo.LidarAuxHas # value = <LidarAuxHas.EMITTER_ID: 1>
    HIT_NORMALS: isaacsim.sensors.experimental.rtx.generic_model_output._rtx_sensors_gmo.LidarAuxHas # value = <LidarAuxHas.HIT_NORMALS: 128>
    MAT_ID: isaacsim.sensors.experimental.rtx.generic_model_output._rtx_sensors_gmo.LidarAuxHas # value = <LidarAuxHas.MAT_ID: 8>
    NONE: isaacsim.sensors.experimental.rtx.generic_model_output._rtx_sensors_gmo.LidarAuxHas # value = <LidarAuxHas.NONE: 0>
    OBJ_ID: isaacsim.sensors.experimental.rtx.generic_model_output._rtx_sensors_gmo.LidarAuxHas # value = <LidarAuxHas.OBJ_ID: 16>
    TICK_ID: isaacsim.sensors.experimental.rtx.generic_model_output._rtx_sensors_gmo.LidarAuxHas # value = <LidarAuxHas.TICK_ID: 32>
    TICK_STATES: isaacsim.sensors.experimental.rtx.generic_model_output._rtx_sensors_gmo.LidarAuxHas # value = <LidarAuxHas.TICK_STATES: 64>
    VELOCITIES: isaacsim.sensors.experimental.rtx.generic_model_output._rtx_sensors_gmo.LidarAuxHas # value = <LidarAuxHas.VELOCITIES: 256>
    __members__: dict # value = {'NONE': <LidarAuxHas.NONE: 0>, 'EMITTER_ID': <LidarAuxHas.EMITTER_ID: 1>, 'CHANNEL_ID': <LidarAuxHas.CHANNEL_ID: 2>, 'ECHO_ID': <LidarAuxHas.ECHO_ID: 4>, 'MAT_ID': <LidarAuxHas.MAT_ID: 8>, 'OBJ_ID': <LidarAuxHas.OBJ_ID: 16>, 'TICK_ID': <LidarAuxHas.TICK_ID: 32>, 'TICK_STATES': <LidarAuxHas.TICK_STATES: 64>, 'HIT_NORMALS': <LidarAuxHas.HIT_NORMALS: 128>, 'VELOCITIES': <LidarAuxHas.VELOCITIES: 256>}
    pass
class Modality():
    """
    Members:

      UNDEFINED

      LIDAR

      RADAR

      ACOUSTIC

      IDS
    """
    def __eq__(self, other: object) -> bool: ...
    def __getstate__(self) -> int: ...
    def __hash__(self) -> int: ...
    def __index__(self) -> int: ...
    def __init__(self, value: int) -> None: ...
    def __int__(self) -> int: ...
    def __ne__(self, other: object) -> bool: ...
    def __repr__(self) -> str: ...
    def __setstate__(self, state: int) -> None: ...
    @property
    def name(self) -> str:
        """
        :type: str
        """
    @property
    def value(self) -> int:
        """
        :type: int
        """
    ACOUSTIC: isaacsim.sensors.experimental.rtx.generic_model_output._rtx_sensors_gmo.Modality # value = <Modality.ACOUSTIC: 3>
    IDS: isaacsim.sensors.experimental.rtx.generic_model_output._rtx_sensors_gmo.Modality # value = <Modality.IDS: 4>
    LIDAR: isaacsim.sensors.experimental.rtx.generic_model_output._rtx_sensors_gmo.Modality # value = <Modality.LIDAR: 1>
    RADAR: isaacsim.sensors.experimental.rtx.generic_model_output._rtx_sensors_gmo.Modality # value = <Modality.RADAR: 2>
    UNDEFINED: isaacsim.sensors.experimental.rtx.generic_model_output._rtx_sensors_gmo.Modality # value = <Modality.UNDEFINED: 0>
    __members__: dict # value = {'UNDEFINED': <Modality.UNDEFINED: 0>, 'LIDAR': <Modality.LIDAR: 1>, 'RADAR': <Modality.RADAR: 2>, 'ACOUSTIC': <Modality.ACOUSTIC: 3>, 'IDS': <Modality.IDS: 4>}
    pass
class MotionCompensationState():
    """
    Members:

      NONCOMPENSATED

      COMPENSATED

      NOT_APPLICABLE
    """
    def __eq__(self, other: object) -> bool: ...
    def __getstate__(self) -> int: ...
    def __hash__(self) -> int: ...
    def __index__(self) -> int: ...
    def __init__(self, value: int) -> None: ...
    def __int__(self) -> int: ...
    def __ne__(self, other: object) -> bool: ...
    def __repr__(self) -> str: ...
    def __setstate__(self, state: int) -> None: ...
    @property
    def name(self) -> str:
        """
        :type: str
        """
    @property
    def value(self) -> int:
        """
        :type: int
        """
    COMPENSATED: isaacsim.sensors.experimental.rtx.generic_model_output._rtx_sensors_gmo.MotionCompensationState # value = <MotionCompensationState.COMPENSATED: 1>
    NONCOMPENSATED: isaacsim.sensors.experimental.rtx.generic_model_output._rtx_sensors_gmo.MotionCompensationState # value = <MotionCompensationState.NONCOMPENSATED: 0>
    NOT_APPLICABLE: isaacsim.sensors.experimental.rtx.generic_model_output._rtx_sensors_gmo.MotionCompensationState # value = <MotionCompensationState.NOT_APPLICABLE: 2>
    __members__: dict # value = {'NONCOMPENSATED': <MotionCompensationState.NONCOMPENSATED: 0>, 'COMPENSATED': <MotionCompensationState.COMPENSATED: 1>, 'NOT_APPLICABLE': <MotionCompensationState.NOT_APPLICABLE: 2>}
    pass
class OutputType():
    """
    Members:

      POINTCLOUD
    """
    def __eq__(self, other: object) -> bool: ...
    def __getstate__(self) -> int: ...
    def __hash__(self) -> int: ...
    def __index__(self) -> int: ...
    def __init__(self, value: int) -> None: ...
    def __int__(self) -> int: ...
    def __ne__(self, other: object) -> bool: ...
    def __repr__(self) -> str: ...
    def __setstate__(self, state: int) -> None: ...
    @property
    def name(self) -> str:
        """
        :type: str
        """
    @property
    def value(self) -> int:
        """
        :type: int
        """
    POINTCLOUD: isaacsim.sensors.experimental.rtx.generic_model_output._rtx_sensors_gmo.OutputType # value = <OutputType.POINTCLOUD: 0>
    __members__: dict # value = {'POINTCLOUD': <OutputType.POINTCLOUD: 0>}
    pass
def getMagicNumberGMO() -> int:
    """
    Get magic number for GenericModelOutput.
    """
def getModelOutputFromBuffer(*args, **kwargs) -> typing.Any:
    """
    Get model output from binary buffer.
    """
