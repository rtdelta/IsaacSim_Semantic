.. _ext_omni_sensors_nv_lidar:

Omniverse Lidar Extension
=========================

Introduction
^^^^^^^^^^^^

The Lidar extension consists of simulation model plugins (currently only one), several utility plugins and different Omnigraph Nodes, where the simulation plugin is a configurable generic lidar model.

The Lidar model is instantiated in the scene as an ``OmniLidar`` prim, with schema attributes and their default values. It uses the following API-Schemas:

- ``OmniSensorGenericLidarCoreAPI``: Defines the core attributes of the Lidar model.
- ``OmniSensorGenericLidarCoreEmitterStateAPI:s#``: Defines the emitter state attributes of the Lidar model (default: s001).

Example usage:

.. code-block:: usda

    def OmniLidar "generic_lidar" (
      doc = """Defines an instance of a lidar that uses generic lidar model Core"""
      prepend apiSchemas = ["OmniSensorGenericLidarCoreAPI", "OmniSensorGenericLidarCoreEmitterStateAPI:s002"] # s002 only needed for Lidars with second emitter state array
    )
    {

        # ... changing attributes ...

        # ... potentially change values of first emitter state array values ...
        float[] omni:sensor:Core:emitterState:s001:azimuthDeg = [...] # has to have numberOfEmitters elements
        ...

        # ... adding second emitter state array values ...
        # Overwriting second emitter state attributes with prefix "s002".
        float[] omni:sensor:Core:emitterState:s002:azimuthDeg = [...] # has to have numberOfEmitters elements
        ...

        def RenderProduct "RenderedOutputs"
        {
            uniform int2 resolution = (1280, 720)
            rel camera = <../../generic_lidar>
            rel orderedVars = [
                <SupportedOutputs/RtxSensorGmo>,
                <SupportedOutputs/RtxSensorMetadata>,
            ]

            def Scope "SupportedOutputs"
            {
                def RenderVar "RtxSensorGmo"
                {
                    uniform string sourceName = "GenericModelOutput"
                    channels = ["EXTRA"]
                }
                def RenderVar "RtxSensorMetadata"
                {
                    string sourceName = "RtxSensorMetadata"
                }
                def RenderVar "PointCloud"
                {
                    string sourceName = "PointCloud"
                    string[] channels = ["Coordinates", "Intensity", "TimeOffsetNs", "Flags"]
                }
            }
        }
    }

Setting Lidar Attributes
^^^^^^^^^^^^^^^^^^^^^^^^

There are multiple steps and attributes to set so that the configured Lidar behaves in a specific way. For ease of understanding, this part will omit the preceding ``omni:sensor:Core:`` for every attribute. Additionally, this guideline will only explain the most basic attributes.

Defining Output
***************

Lidar output is provided either as a ``GenericModelOutput`` struct or as a ``PointCloud`` (ovrtx_rendered_output_t) struct. 
The following Lidar attributes define output values:

+-------------------------------+----------+------------------------------------------------------------+
| Attribute                     | Type     | Description                                                |
+===============================+==========+============================================================+
| elementsCoordsType            | token    | Sets the desired coordinate system for the output basic    |
|                               |          | elements (not auxiliary data). Allowed tokens: "CARTESIAN",|
|                               |          | "SPHERICAL". Runtime changes not supported, yet.           |
+-------------------------------+----------+------------------------------------------------------------+
| outputMotionCompensationState | token    | Sets the desired motion compensation state for all         |
|                               |          | outputs (including auxiliary data). Allowed tokens:        |
|                               |          | "NONCOMPENSATED", "COMPENSATED". Runtime changes not       |
|                               |          | supported, yet.                                            |
+-------------------------------+----------+------------------------------------------------------------+
| outputFrameOfReference        | token    | Sets the desired frame of reference for all outputs        |
|                               |          | (including auxiliary data). Allowed tokens: "SENSOR",      |
|                               |          | "WORLD", "CUSTOM". Runtime changes not supported, yet.     |
+-------------------------------+----------+------------------------------------------------------------+
| customFrameOfReferenceTrafo   | float[]  | Used only if outputFrameOfReference = CUSTOM. Defines      |
|                               |          | the transformation for the custom frame of reference.      |
|                               |          | Structured as [x,y,z,roll,pitch,yaw]. Runtime changes      |
|                               |          | not supported, yet.                                        |
+-------------------------------+----------+------------------------------------------------------------+

Output Formats
~~~~~~~~~~~~~~

**GenericModelOutput**

The ``GenericModelOutput`` format provides a comprehensive output structure containing all point cloud data 
and metadata in a single buffer. This is the traditional output format. The channels of the GenericModelOutput define the auxiliary data channels.
These are: "NONE", "BASIC", "EXTRA", "FULL" according to the AuxType enum.

**PointCloud (RenderOutput)**

The ``PointCloud`` format provides a flexible output structure with user-selectable channels. When using the 
``PointCloud`` RenderVar, you can request specific data channels to be included in the output:

* **Coordinates**: 3D point coordinates (float[3] per point)
* **Intensity**: Reflection intensity values (float per point)
* **TimeOffsetNs**: Time offset in nanoseconds (int32 per point)
* **Flags**: Point flags (uint8 per point)
* **EmitterId**: Emitter/laser ID (uint32 per point)
* **ChannelId**: Channel ID (uint32 per point)
* **MaterialId**: Material ID of hit surface (uint32 per point)
* **TickId**: Tick/scan ID (uint32 per point)
* **HitNormal**: Surface normal at hit point (float[3] per point)
* **Velocity**: Velocity at hit point (float[3] per point)
* **ObjectId**: Object/instance ID (uint8[16] per point)
* **EchoId**: Echo/return ID (uint8 per point)
* **TickState**: State of the tick (uint8 per point)

The output also includes metadata parameters such as frameId, timestampNs, frame start/end information, 
and transformation data. Only requested channels are included in the output, reducing memory footprint 
for applications that don't need all data channels.



Scanning Principle
******************

The first attribute to set corresponds to the scanning principle of the sensor.

``token omni:sensor:Core:scanType``

The two allowed tokens and supported scanning principles are: ``ROTARY`` (a rotating Lidar) and ``SOLID_STATE`` (a solid state Lidar, including flash Lidars).
There exist common and exclusive attributes between the two scanning principles. Every attribute explained is a common attribute if not indicated otherwise.


Configuring a Full Firing Pattern
*********************************

The second step to configure a Lidar sensor is to set up the firing pattern related attributes. The following attributes are corresponding to the application of the individual emitter state(s) (fixed firing pattern).

+----------------------+---------+--------------------------------------------------------------+
| Attribute            | Type    | Description                                                  |
+======================+=========+==============================================================+
| scanRateBaseHz       | uint    | Number of full point clouds per second.                      |
+----------------------+---------+--------------------------------------------------------------+
|| patternFiringRateHz || uint   || Number of times the emitter array (firing pattern) is       |
||                     ||        || applied per second (at different rotation points for        |
||                     ||        || rotary Lidars). For solid state Lidar this should be the    |
||                     ||        || same as the scanRateBaseHz.                                 |
+----------------------+---------+--------------------------------------------------------------+
|| maxReturns          || uint   || Maximum number of returns/detections (correspond to         |
||                     ||        || individual points) per channel.                             |
+----------------------+---------+--------------------------------------------------------------+
|| numberOfEmitters    || uint   || Number of emitters per emitter state (individual firing     |
||                     ||        || patterns). Corresponds to the length of the arrays in the   |
||                     ||        || emitter states.                                             |
+----------------------+---------+--------------------------------------------------------------+
|| numberOfChannels    || uint   || Number of channels/detectors. Corresponds to the            |
||                     ||        || individual number of detectors (can be different to         |
||                     ||        || numberOfEmitters).                                          |
+----------------------+---------+--------------------------------------------------------------+
|| emitterStateCount   || uint   || Number of different emitter states (firing patterns).       |
||                     ||        || Only needs to be changed for multiple emitter states.       |
+----------------------+---------+--------------------------------------------------------------+
|| stateResolutionStep || uint   || Number of times same firing pattern will be applied until   |
||                     ||        || the state is changed. Only needs to be changed for multiple |
||                     ||        || emitter states.                                             |
+----------------------+---------+--------------------------------------------------------------+
|| numLines            || uint   || Number of lines in solid state firing pattern. Only needed  |
||                     ||        || for solid state Lidar.                                      |
+----------------------+---------+--------------------------------------------------------------+
|| numRaysPerLine      || uint[] || Number of points per line. Only needed for solid state      |
||                     ||        || Lidar.                                                      |
+----------------------+---------+--------------------------------------------------------------+

For rotary Lidars the ``patternFiringRateHz`` and ``scanRateBaseHz`` correspond to the individual rotation points where the emitter states are applied (referred to as "ticks" here onwards).
For instance, a ``scanRateBaseHz`` of 10 and ``patternFiringRateHz`` of 36000 will result in a tick at every 0.1° (azimuth) for a rotary Lidar.

The following attributes define the individual emitter state (firing pattern applied at every rotation point). "#" is a placeholder for the number of the emitter state starting with a "001" (``emitterState:s001:…``)

+----------------------------------------+----------+------------------------------------------------------------+
| Attribute                              | Type     | Description                                                |
+========================================+==========+============================================================+
| emitterState:s#:azimuthDeg             | float[]  | Azimuth of the emitter relative to the tick position of the|
|                                        |          | emitter in degrees.                                        |
+----------------------------------------+----------+------------------------------------------------------------+
| emitterState:s#:elevationDeg           | float[]  | Elevation of the emitter in degrees.                       |
+----------------------------------------+----------+------------------------------------------------------------+
| emitterState:s#:fireTimeNs             | uint[]   | Delta fire time to the current tick time in nanoseconds    |
+----------------------------------------+----------+------------------------------------------------------------+
| emitterState:s#:channelId              | uint[]   | Mapping to the corresponding channel/detector              |
+----------------------------------------+----------+------------------------------------------------------------+
| emitterState:s#:bank                   | uint[]   | Line of the emitter (only needed for solid state Lidar)    |
+----------------------------------------+----------+------------------------------------------------------------+
| emitterState:s#:rangeId                | uint[]   | Corresponding range id of the emitters. Has                |
|                                        |          | numberOfEmitters elements or empty.                        |
+----------------------------------------+----------+------------------------------------------------------------+
| emitterState:s#:vertOffsetM            | float[]  | Vertical offset of the emitters in meters. Has             |
|                                        |          | numberOfEmitters elements or empty.                        |
+----------------------------------------+----------+------------------------------------------------------------+
| emitterState:s#:horOffsetM             | float[]  | Horizontal offset of the emitters in meters. Has           |
|                                        |          | numberOfEmitters elements or empty.                        |
+----------------------------------------+----------+------------------------------------------------------------+
| emitterState:s#:distanceCorrectionM    | float[]  | Distance correction of the emitters in meters. Has         |
|                                        |          | numberOfEmitters elements or empty.                        |
+----------------------------------------+----------+------------------------------------------------------------+
| emitterState:s#:focalDistM             | float[]  | Focal distance of the emitters in meters. Has              |
|                                        |          | numberOfEmitters elements or empty.                        |
+----------------------------------------+----------+------------------------------------------------------------+
| emitterState:s#:focalSlope             | float[]  | Focal slope of the emitters. Has numberOfEmitters          |
|                                        |          | elements or empty.                                         |
+----------------------------------------+----------+------------------------------------------------------------+
| emitterState:s#:emitterPeakPowerW      | float[]  | Peak power of the emitters. Has                            |
|                                        |          | numberOfEmitters elements or empty. DEPRECATED             |
+----------------------------------------+----------+------------------------------------------------------------+
| emitterState:s#:roi                    | bool[]   | Is the emitter part of the ROI. Has numberOfEmitters       |
|                                        |          | elements or empty. (ROI - Region of Interest)              |
+----------------------------------------+----------+------------------------------------------------------------+
| emitterState:s#:isROIState             | bool     | Is the emitter state a ROI state.                          |
+----------------------------------------+----------+------------------------------------------------------------+

Constraining Field of View
**************************

+-------------------------------+----------+------------------------------------------------------------+
| Attribute                     | Type     | Description                                                |
+===============================+==========+============================================================+
| nearRangeM                    | float    | Minimum range to be a valid return in meters.              |
+-------------------------------+----------+------------------------------------------------------------+
| farRangeM                     | float    | Maximum range to be a valid return in meters.              |
+-------------------------------+----------+------------------------------------------------------------+
| validStartAzimuthDeg          | float    | Valid start azimuth in degrees. Only for rotary sensors.   |
|                               |          | Default is 0°.                                             |
+-------------------------------+----------+------------------------------------------------------------+
| validEndAzimuthDeg            | float    | Valid end azimuth in degrees. Only for rotary sensors.     |
|                               |          | Default is 360°.                                           |
+-------------------------------+----------+------------------------------------------------------------+

Intensity-Defining Attributes
*****************************

The following attributes are responsible for generating a sensible intensity measurement. The Lidar model
calculates an intensity value between 0 and 1. Additionally, one can set the ``omni:sensor:Core:intensityScalePercent``
attribute to map this value to a sensor-specific reflectivity value, with default value 255.
Moreover, there also exists the ability to encode a non-linear mapping to emphasize on specific regions of
intensity values (not discussed here).

Attributes which affect the main intensity computation can be grouped into the following three categories:

Point Drops Sensitivity
~~~~~~~~~~~~~~~~~~~~~~~

The Lidar model calculates the point drops sensitivity (what is seen as a valid point/measurement) based on the two attributes:

+-------------------------------+----------+----------------------------------------------------------------+
| Attribute                     | Type     | Description                                                    |
+===============================+==========+================================================================+
| minReflectance                | float    | Minimum reflectance value (in %) to get a return at a          |
|                               |          | specified distance.                                            |
+-------------------------------+----------+----------------------------------------------------------------+
| minReflectionRangeM           | float    | Range in meters corresponding to the ``minReflectance`` value. |
+-------------------------------+----------+----------------------------------------------------------------+

Beam Properties
~~~~~~~~~~~~~~~

+-------------------------------+----------+------------------------------------------------------------+
| Attribute                     | Type     | Description                                                |
+===============================+==========+============================================================+
| peakPowerW                    | float    | Average power per emitter in watts.                        |
+-------------------------------+----------+------------------------------------------------------------+
| waveLengthNm                  | float    | Wavelength in nanometers. Will also affect the material    |
|                               |          | processing.                                                |
+-------------------------------+----------+------------------------------------------------------------+
| pulseTimeNs                   | uint     | Pulse time of the beam in nanoseconds.                     |
+-------------------------------+----------+------------------------------------------------------------+
| focusDistM                    | float    | Focus distance of the beam in meters.                      |
+-------------------------------+----------+------------------------------------------------------------+
| Msquared                      | float    | Msquared value of the beam. Often called the beam quality  |
|                               |          | value.                                                     |
+-------------------------------+----------+------------------------------------------------------------+
| divergenceHorDeg              | float    | Horizontal beam divergence angle in degrees. Alternatively |
|                               |          | one could set the beamWaistHorM value.                     |
+-------------------------------+----------+------------------------------------------------------------+
| divergenceVerDeg              | float    | Vertical beam divergence angle in degrees. Alternatively   |
|                               |          | one could set the beamWaistVerM value.                     |
+-------------------------------+----------+------------------------------------------------------------+

Detector Properties
~~~~~~~~~~~~~~~~~~~

+-------------------------------+----------+------------------------------------------------------------+
| Attribute                     | Type     | Description                                                |
+===============================+==========+============================================================+
| aspectRatio                   | float    | Aspect ratio of the detector ("squareness of the detector")|
+-------------------------------+----------+------------------------------------------------------------+
| effectiveApertureSizeM        | float    | Effective aperture size of the sensor in meters.           |
+-------------------------------+----------+------------------------------------------------------------+
| quantumEfficiency             | float    | Quantum efficiency of the detector.                        |
+-------------------------------+----------+------------------------------------------------------------+
| pixelPitch                    | float    | Pixel pitch of the detector in microns.                    |
+-------------------------------+----------+------------------------------------------------------------+
| calibrationGain               | float    | Calibration gain of the detector.                          |
+-------------------------------+----------+------------------------------------------------------------+
| bitDepthResolution            | float    | Bit depth resolution of the detector.                      |
+-------------------------------+----------+------------------------------------------------------------+

Mechanical noise
~~~~~~~~~~~~~~~~

+-------------------------------+----------+------------------------------------------------------------+
| Attribute                     | Type     | Description                                                |
+===============================+==========+============================================================+
| azimuthErrorMean              | float    | Mean value of the emitter's azimuth noise in degrees.      |
+-------------------------------+----------+------------------------------------------------------------+
| azimuthErrorStd               | float    | Standard deviation of the emitter's azimuth noise in       |
|                               |          | degrees.                                                   |
+-------------------------------+----------+------------------------------------------------------------+
| elevationErrorMean            | float    | Mean value of the emitter's elevation noise in degrees.    |
+-------------------------------+----------+------------------------------------------------------------+
| elevationErrorStd             | float    | Standard deviation of the emitter's elevation noise in     |
|                               |          | degrees.                                                   |
+-------------------------------+----------+------------------------------------------------------------+
| originErrorMean               | float    | Mean value of the emitter's origin error in meters. Can be |
|                               |          | used to model vibrations.                                  |
+-------------------------------+----------+------------------------------------------------------------+
| originErrorStd                | float    | Standard deviation of the emitter's origin error in meters.|
|                               |          | Can be used to model vibrations.                           |
+-------------------------------+----------+------------------------------------------------------------+

Additional attributes
*********************

As mentioned before there are additional attributes not listed in this section. Some examples are:

+-------------------------------+----------+------------------------------------------------------------+
| Attribute                     | Type     | Description                                                |
+===============================+==========+============================================================+
| beamWaistHorM                 | float    | Beam waist horizontal of the sensor in meters.             |
+-------------------------------+----------+------------------------------------------------------------+
| beamWaistVerM                 | float    | Beam waist vertical of the sensor in meters.               |
+-------------------------------+----------+------------------------------------------------------------+
| emitterStatesFile             | string   | File containing the emitter states of the sensor.          |
|                               |          | Not supported, yet.                                        |
+-------------------------------+----------+------------------------------------------------------------+
| intensityMappingDecoding      | float[]  | Intensity mapping decoding. Changing the number of         |
|                               |          | elements at runtime is not supported.                      |
+-------------------------------+----------+------------------------------------------------------------+
| intensityMappingEncoding      | float[]  | Intensity mapping encoding. Changing the number of         |
|                               |          | elements at runtime is not supported.                      |
+-------------------------------+----------+------------------------------------------------------------+
| intensityMappingType          | token    | Intensity mapping type. Allowed tokens: "LINEAR",          |
|                               |          | "NONLINEAR", "NONLINEAR_ENCODING_ONLY",                    |
|                               |          | "NONLINEAR_DECODING_ONLY".                                 |
+-------------------------------+----------+------------------------------------------------------------+
| maxAzimuthROI                 | float    | End azimuth point of the ROI part of the pattern --        |
|                               |          | in sensor market model frame.                              |
+-------------------------------+----------+------------------------------------------------------------+
| minAzimuthROI                 | float    | Start azimuth point of the ROI part of the pattern --      |
|                               |          | in sensor market model frame.                              |
+-------------------------------+----------+------------------------------------------------------------+
| minDistBetweenEchosM          | float    | Minimum distance between two echos in meters.              |
+-------------------------------+----------+------------------------------------------------------------+
| rangeAccuracyM                | float    | Range accuracy of the sensor in meters.                    |
+-------------------------------+----------+------------------------------------------------------------+
| rangeCount                    | uint     | Number of range regions of the emitters.                   |
+-------------------------------+----------+------------------------------------------------------------+
| rangeOffsetM                  | float    | Range for which objects are invisible -- useful for        |
|                               |          | sensors inside objects.                                    |
+-------------------------------+----------+------------------------------------------------------------+
| rangeResolutionM              | float    | Range resolution of the sensor in meters.                  |
+-------------------------------+----------+------------------------------------------------------------+
| rangesMaxM                    | float[]  | Maximum ranges of the emitters in meters. Has              |
|                               |          | rangeCount elements. For per-emitter ranges                |
+-------------------------------+----------+------------------------------------------------------------+
| rangesMinM                    | float[]  | Minimum ranges of the emitters in meters. Has              |
|                               |          | rangeCount elements. For per-emitter ranges                |
+-------------------------------+----------+------------------------------------------------------------+
| reflectionPowerFraction       | float    | Fraction of the reflection power for multiple returns.     |
+-------------------------------+----------+------------------------------------------------------------+
| skipDroppingInvalidPoints     | bool     | When false the model will drop invalid (dropped) points.   |
|                               |          | Runtime changes not supported, yet.                        |
+-------------------------------+----------+------------------------------------------------------------+
| startAzimuthOffsetDeg         | float    | Start azimuth offset angle of the sensor in degrees --     |
|                               |          | in sensor market model frame.                              |
+-------------------------------+----------+------------------------------------------------------------+
| transmissionPowerFraction     | float    | Fraction of the transmission power for multiple returns.   |
+-------------------------------+----------+------------------------------------------------------------+
| marketName                    | string   | Market name of the sensor.                                 |
+-------------------------------+----------+------------------------------------------------------------+
| modelName                     | string   | Model name of the sensor.                                  |
+-------------------------------+----------+------------------------------------------------------------+
| modelVendor                   | string   | Vendor of the sensor model.                                |
+-------------------------------+----------+------------------------------------------------------------+
| modelVersion                  | string   | Version of the sensor model.                               |
+-------------------------------+----------+------------------------------------------------------------+
| tickRate                      | float    | Tick rate of the sensor.                                   |
+-------------------------------+----------+------------------------------------------------------------+

Atmospheric Modeling
^^^^^^^^^^^^^^^^^^^^

The Lidar model includes a Mie scattering based atmospheric simulation model, which currently supports rain.
It is planned to add fog, haze and snow at a later time.

Besides the wavelength dependency, the rain model has one basic parameter: the rain rate in mm/h (configurable as a ``carb`` setting, ``/app/sensors/nv/atmospherics/rainRate``).
For instance, a rain rate of 0.25mm/h is light rain, whereas a rain rate of 25mm/h corresponds to a very heavy rain.
Every other parameter for the Mie scattering (e.g., rain drop size distribution) is derived from the rain rate.

Additionally, the rain model provides the possibility to simulate rain drop hits as false positive.
The amount of false positives can be set via a rain drop hit threshold (configurable as a ``carb`` setting: ``/app/sensors/nv/atmospherics/rainDropHitThresh``).
This threshold is related to the Mie back scattering efficiency parameter and a distance dependent rain drop hit probability distribution.

Both parameters can be set via command line and dynamically via the script editor, as both parameter are defined as ``carb`` settings.
For example, you can start the simulation with a rain rate of 25mm/h by adding ``--/app/sensors/nv/atmospherics/rainRate=25`` to the startup command of kit.
It is important to activate the material framework to get accurate readings from wet roads (point drops) and false positives due to back scattering (under the ground).

.. _LidarPCConverter:

LidarPCConverter
^^^^^^^^^^^^^^^^

The LidarPCConverter converts the Lidar data stream to an easily usable point cloud (GenericModelOutput format).
The interface is defined in the header file ILidarPCConverter.h.

Users can create objects that implement this interface by acquiring the
ILidarPCConverterFactory (ILidarPCConverterFactory.h) carbonite interface and using the createInstance() method.

Instantiation
*************

To instantiate the LidarPCConverter the user needs to acquire the carbonite ILidarPCConverterFactory interface, and use the create instance method::

  ILidarPCConverterPtr m_pcConverter = carb::getFramework()->acquireInterface<omni::sensors::lidar::ILidarPCConverterFactory>()->createInstance();

Initialization
**************

The user has to initialize the converter, with the corresponding converter cfg (omni::sensors::lidar::LidarPCConverterCfg) like this::

  m_pcConverter->init(cfg);

Conversion
**********

The conversion of the buffer differs with the conversion buffer type (PACKETS, GENERIC_FILE (HDF5) or live sensor buffer).
In the live sensor buffer the user calls the following function ::

  m_pcConverter->convertBuffer(sensorBuffer, dataSize, numPoints, scanComplete, cudaStream);

Next he can get the point cloud::

  LidarPointCloud pc = m_pcConverter->getPointCloud(cudaStream);


The user has to keep in mind, that in live CPU mode the getPointCloud function has to be called in a cudaLaunchHostFunc with the appropriate cudaStream, as every work is scheduled asynchronously.


Omnigraph Nodes
^^^^^^^^^^^^^^^

TranscoderLidar
***************

**Introduction**

The Transcoder node encodes the Lidar data stream into vendor specific packets and records them via binary file writing.

**Omnigraph Node Name**

``omni.sensors.nv.lidar.TranscoderLidar``

**Parameters & Attributes**

+------------------+------------------------------------------------------------+----------+-----------+--------------------+-------+
|Parameter Name    |Description                                                 |Value Type|Value Range|Default Value       |Example|
+==================+============================================================+==========+===========+====================+=======+
|sensorProfileName |Filename of sensor profile (excluding directory and .json)  |string    |           | "GENERIC"          |       |
+------------------+------------------------------------------------------------+----------+-----------+--------------------+-------+
|returnType        |Desired return type (0 - First, 1 - last, 2 - Strongest,    |int       |           | 3                  |       |
|                  |3 - MultipleReturns)                                        |          |           |                    |       |
+------------------+------------------------------------------------------------+----------+-----------+--------------------+-------+
|dumpPackets       |Dump packets as file                                        |bool      |           | false              |       |
+------------------+------------------------------------------------------------+----------+-----------+--------------------+-------+
|decoderPath       |Optional path to ndas decoder                               |string    |           | ""                 |       |
+------------------+------------------------------------------------------------+----------+-----------+--------------------+-------+
|fileName          |Filename of the dumped bin file                             |string    |           | "lidar.h5"         |       |
+------------------+------------------------------------------------------------+----------+-----------+--------------------+-------+
|groupName         |Sensor name to be put inside hdf5 file                      |string    |           | "Lidar"            |       |
+------------------+------------------------------------------------------------+----------+-----------+--------------------+-------+
|encoderType       |Encoder Type -- needed if there are different versions of   |int       |           | 7                  |       |
|                  |the sensor (e.g., NCD)                                      |          |           |                    |       |
+------------------+------------------------------------------------------------+----------+-----------+--------------------+-------+
|simTime           |Simulation time given from PostProcessEntryNode             |double    |           | 0                  |       |
+------------------+------------------------------------------------------------+----------+-----------+--------------------+-------+
|src               |Sensor buffer id                                            |uint64    |           | 0                  |       |
+------------------+------------------------------------------------------------+----------+-----------+--------------------+-------+
|srcMeta           |Lidar Meta Data                                             |uint64    |           | 0                  |       |
+------------------+------------------------------------------------------------+----------+-----------+--------------------+-------+
|cudaStream        |Cuda Stream Input                                           |uint64    |           | 0                  |       |
+------------------+------------------------------------------------------------+----------+-----------+--------------------+-------+


The next node is the LidarPointAccumulator, which accumulates the Lidar data stream and converts it to a point cloud.

LidarPointAccumulator
*********************

**Introduction**

The LidarPointAccumulator node accumulates the Lidar data stream and converts it to a point cloud.

**Omnigraph Node Name**

``omni.sensors.nv.lidar.LidarPointAccumulator``

**Parameters & Attributes**

+------------------+------------------------------------------------------------+----------+-----------+--------------------+-------+
|Parameter Name    |Description                                                 |Value Type|Value Range|Default Value       |Example|
+==================+============================================================+==========+===========+====================+=======+
|src               |Input buffer                                                |uint64    |           | 0                  |       |
+------------------+------------------------------------------------------------+----------+-----------+--------------------+-------+
|cudaStream        |Cuda Stream Input                                           |uint64    |           | 0                  |       |
+------------------+------------------------------------------------------------+----------+-----------+--------------------+-------+
|srcMeta           |Input meta data buffer                                      |uint64    |           | 0                  |       |
+------------------+------------------------------------------------------------+----------+-----------+--------------------+-------+
|targetPID         |Target process ID to send data stream to                    |uint64    |           | 0                  |       |
+------------------+------------------------------------------------------------+----------+-----------+--------------------+-------+
|exportBytePoints  |Export lidar points                                         |bool      |           | false              |       |
+------------------+------------------------------------------------------------+----------+-----------+--------------------+-------+
|publishVizPoints  |Export viz points                                           |bool      |           | true               |       |
+------------------+------------------------------------------------------------+----------+-----------+--------------------+-------+
|maxPoints         |Max points in one scan                                      |int       |           | 1000000            |       |
+------------------+------------------------------------------------------------+----------+-----------+--------------------+-------+
|desiredCoordsType |Desired output coords type                                  |token     |CARTESIAN, | "CARTESIAN"        |       |
|                  |                                                            |          |SPHERICAL  |                    |       |
+------------------+------------------------------------------------------------+----------+-----------+--------------------+-------+
|outputOnGPU       |Output on GPU                                               |bool      |           | false              |       |
+------------------+------------------------------------------------------------+----------+-----------+--------------------+-------+
|sensorMount6DPose |[x,y,z,r,p,y]                                               |float[]   |           |                    |       |
+------------------+------------------------------------------------------------+----------+-----------+--------------------+-------+
|scanRateBaseHz    |Scan rate of the sensor                                     |int       |           | 10                 |       |
+------------------+------------------------------------------------------------+----------+-----------+--------------------+-------+
|scanDeltaEpsilonNs|Epsilon for considering scan complete in ns                 |int       |           |  28000             |       |
+------------------+------------------------------------------------------------+----------+-----------+--------------------+-------+
|colorCode         |0 - constant, 1 - intensity, 2 - height, 3 - range,         |int       |           | 1                  |       |
|                  |4 - objectId, 5 - echoId, 6 - materialId                    |          |           |                    |       |
+------------------+------------------------------------------------------------+----------+-----------+--------------------+-------+
|sendDataId        |Send data id to distinguish point clouds on the receiver    |int       |           | 0                  |       |
|                  |side                                                        |          |           |                    |       |
+------------------+------------------------------------------------------------+----------+-----------+--------------------+-------+

**Outputs**

+------------------+------------------------------------------------------------+----------+-----------+--------------------+-------+
|Output Name       |Description                                                 |Value Type|Value Range|Default Value       |Example|
+==================+============================================================+==========+===========+====================+=======+
|dest              |Output buffer of accumulated GenericModelOutput             |uint64    |           | 0                  |       |
+------------------+------------------------------------------------------------+----------+-----------+--------------------+-------+
|newData           |True if new data is published                               |bool      |           | false              |       |
+------------------+------------------------------------------------------------+----------+-----------+--------------------+-------+
|cudaStream        |Cuda Stream Input                                           |uint64    |           | 0                  |       |
+------------------+------------------------------------------------------------+----------+-----------+--------------------+-------+

Python Bindings and Scripts
^^^^^^^^^^^^^^^^^^^^^^^^^^^

The Lidar extension offers a variety of python bindings and scripts for the Lidar. These can be used for easy post-processing of the simulated Lidar point cloud.

Python Bindings
***************

The python bindings make it possible to use the Lidar utilities and specific classes in python code.
For instance, the user can import the Lidar python bindings in the following way

.. code-block:: python

    import omni.sensors.nv.lidar._lidar as lidar

Furthermore, there exist the LidarUtilities script, containing some helper functions for ease of use of the Lidar bindings.
The script can be imported, e.g., the following way:

.. code-block:: python

    import omni.sensors.nv.lidar.scripts.LidarUtilities as lutil

There are binding definitions for all basic classes and structs of the Lidar and Lidar Tools extension.
Furthermore, there are bindings for the utilities like the LidarPCConverter. There is a mode to accumulate and convert udp packets to a Lidar point cloud, but not every sensor is supported.
To get a LidarPCConverter object the user can call the following helper function of the LidarUtilities script

..  code-block:: python

    cfg = lutil.PCGeneratorConfig(bin_file) # or (bin_file,"",sensor_name) for reading a HDF5 file (only supported in linux for now)
    converter = lutil.get_pc_converter(cfg)

For more options of the PCGeneratorConfig see the LidarUtilities script. An example conversion is as follows

..  code-block:: python

    # convert buffer
    # File is specified in the cfg
    converter.convertBuffer()
    # or this for a GenericModelOutput binary buffer
    # converter.convertBuffer(buffer,data_size, scan_complete)
    pc = converter.getPointCloud()



Tiled Lidar Functionality
^^^^^^^^^^^^^^^^^^^^^^^^^

Similar to tiled Camera rendering multiple Lidar models can be attached to a single RenderProduct to allow for more efficient rendering.

Example usage:

.. code-block:: usda

    def OmniLidar "DasLidarTile_0" (
        prepend apiSchemas = ["OmniSensorGenericLidarCoreAPI"]
        doc = "Defines an instance of a lidar that uses generic lidar model Core"
    )
    {
        float3 xformOp:rotateYXZ = (0, 0, 0)
        float3 xformOp:scale = (1, 1, 1)
        double3 xformOp:translate = (0, 0, 0)
        uniform token[] xformOpOrder = ["xformOp:translate", "xformOp:rotateYXZ", "xformOp:scale"]
    }

    def OmniLidar "DasLidarTile_1" (
        prepend apiSchemas = ["OmniSensorGenericLidarCoreAPI"]
        doc = "Defines an instance of a lidar that uses generic lidar model Core"
    )
    {
        float3 xformOp:rotateYXZ = (0, 0, 0)
        float3 xformOp:scale = (1, 1, 1)
        double3 xformOp:translate = (0, 1, 0)
        uniform token[] xformOpOrder = ["xformOp:translate", "xformOp:rotateYXZ", "xformOp:scale"]
    }

    def Scope "Render"
    {
        def RenderProduct "TiledLidar"
        {
            rel camera = [
                </DasLidarTile_0>,
                </DasLidarTile_1>
            ]
            rel orderedVars = [
                </Render/TiledLidar/gmo_tile_0>,
                </Render/TiledLidar/gmo_tile_1>
            ]

            def RenderVar "gmo_tile_0"
            {
                uniform string sourceName = "GenericModelOutput_0"
            }

            def RenderVar "gmo_tile_1"
            {
                uniform string sourceName = "GenericModelOutput_1"
            }
        }
    }


Each Lidar instance will produce its own separate RenderVars/AOVs differentiated by the "_X" suffix where X is the index of the Lidar instance in the RenderProduct's camera relationship.
By default each Lidar instance that is part of a tiled Lidar setup will downsample its fidelity by the number of Lidar instances in the tiled setup to preserve runtime and memory requirements. E.g. if there are 4 Lidar instances in a tiled setup each lidar will only produce a point cloud of roughly 1/4 of the original.
This can be overridden by setting the ``omni:sensor:Core:tiledSubsampling`` attribute on each Lidar instance. The value of this attribute indicates the factor by which the original fidelity will be divided by. E.g. setting this attribute to 1 will produce the original fidelity for that Lidar instance. The default value is 0 which means that the fidelity will be divided by the number of Lidar instances in the tiled setup.


AOVs
^^^^

The Lidar model also supports granular AOVs (Arbitrary Output Variables) that provide individual data channels for each return.
These can be requested as separate RenderVars in addition to or instead of the combined ``GenericModelOutput``.

.. list-table::
    :widths: 15 15 15 40 15
    :header-rows: 1

    * - AOV Name
      - Data Type
      - Buffer Semantics
      - Description
      - Unit
    * - Coordinates
      - float
      - 2D Array
      - 3D position of detection (per point). Coordinate system determined by ``omni:sensor:Core:elementsCoordsType`` (Cartesian or Spherical). Array is a 3xN packing (xxx..., yyy..., zzz...).
      - m, rad
    * - Intensity
      - float
      - 1D Array
      - The return strength of a processed ray hit normalized by ``omni:sensor:Core:intensityProcessing`` Mode.
      - unitless
    * - TimeOffsetNs
      - int32
      - 1D Array
      - Time offset in nanoseconds relative to timestampNs in SensorFrameData.
      - ns
    * - Flags
      - uint8
      - 1D Array
      - Status flag bit field for the detection point that can represent multiple options. Current supported flags are: VALID and FLAG_7 detailing a valid point and whether the individual point corresponds to a new scan respectively.
      - unitless
    * - EmitterId
      - uint32
      - 1D Array
      - Internal index of emitter in emitter state array. Requires auxiliary data to be filled specified by: ``string[] channels`` = "BASIC".
      - unitless
    * - ChannelId
      - uint32
      - 1D Array
      - Index identifying a detector. Index sequence can be different from emitter index per emitter state. Allows support for complex channel configurations per tick. Requires auxiliary data to be filled specified by ``string[] channels`` = "BASIC".
      - unitless
    * - TickId
      - uint32
      - 1D Array
      - Index deliniating which tick the hit belongs to. The id ranges from 0 to the azimuth scan extents and azimuth scan step. Requires auxiliary data to be specified as ``string[] channels`` = "BASIC".
      - unitless
    * - EchoId
      - uint8
      - 1D Array
      - Index identifying the return index. Lidar beams can result in multiple returns (i.e. echos) that are index and captured in the echoId array. Requires auxiliary data to be filled specified by ``string[] channels`` = "BASIC".
      - unitless
    * - TickState
      - uint8
      - 1D Array
      - Index deliniating a tick state. Each lidar azimuth step (i.e. tick) can have a unique scan pattern. The tick state index represents the active scan pattern for a given tick for each point in the array. Requires auxiliary data to be filled specified by ``string[] channels`` = "BASIC".
      - unitless
    * - MaterialId
      - uint32
      - 1D Array
      - Non visual material index from the encoded hit geometry. Requires auxiliary data to be filled which is specified by ``string[] channels`` = "EXTRA".
      - unitless
    * - ObjectId
      - uint32
      - 2D Array
      - 128bit stable object id for the hit point. The AOV requires 4 uint32 values to represent the 128bit id hence a Nx4 array. Requires auxiliary data to be filled specified by ``string[] channels`` = "EXTRA". Array is Nx4 packing (Id11, Id12, Id13, Id14, Id21, Id22, Id23, Id24, ...).
      - unitless
    * - HitNormal
      - float
      - 2D Array
      - The normal vector of the hit point. Can be in either world or sensor space by ``omni:sensor:Core:elementsCoordsType``. Requires auxiliary data to be filled by ``string[] channels`` = "FULL". Array is a Nx3 packing (NxNyNz, NxNyNz, NxNyNz, ...).
      - unitless
    * - Velocity
      - float
      - 2D Array
      - The velocity vector of the hit point. Requires auxiliary data to be filled specified by ``string[] channels`` = "FULL". Array is a Nx3 packing (VxVyVz, VyVzVx, VzVxVy, ...).
      - m/s
    * - SensorFrameData
      - SensorFrameData structure
      - Structure
      - Frame data structure contains additional metadata information to give more context to the granular AOVs from the sensor model. The frame data includes information such as coordinate frame, system, begin and end frame, modality, and motion compensation state. This metadata provides per frame characteristics to the give reference to the timestamp offset, coordinates, normals, and other features such as motion compensation. See rtx_plugins/include/rtx/rtsensor/SensorFrameData.h for more details.
      -
    * - GenericModelOutput
      - GMO structure
      - Structure
      - Point cloud data structure. The GMO is a composite of all the data fields mentioned above that can optionally include aux data from the schema variable ``string[] channels``. Buffer can reside on the CPU or GPU. Refer to the generic model output documentation for more details.
      -


Arrays are of size N, where N is the number of detections in the scan that is reported in the metadata.