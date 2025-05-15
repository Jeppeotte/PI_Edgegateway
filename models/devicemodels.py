from pydantic import BaseModel
# General data classes
# Data class for the configfile
class Device(BaseModel):
    group_id: str
    node_id: str
    device_id: str
    alias: str | None = None
    manufacturer: str | None = None
    model: str | None = None
    protocol_type: str
    ip: str | None = None
    port: int | None = None
    unit_id: int | None=None
    rack: int | None=None
    slot: int | None=None

# For the device_services
class DeviceService(BaseModel):
    device_id: str
    protocol_type: str
    config: str
    tested: bool
    activated: bool

# For the application_services
class ApplicationService(BaseModel):
    application_id: str
    config: str
    activated: bool

# Modbus classes
class ModbusPollingInterval(BaseModel):
    default_coil_interval: float
    default_register_interval: float

class HoldingRegisters(BaseModel):
    name: str
    address: int
    data_type: str
    units: str

class Coils(BaseModel):
    name: str
    address: int

class ModbusDeviceServiceConfig(BaseModel):
    device: Device
    polling: ModbusPollingInterval
    holding_registers: list[HoldingRegisters] | None=None
    coils: list[Coils] | None=None

class Metrics(BaseModel):
    name: str
    timestamp: float
    datatype: str
    value: int
    unit: str

class PollingInterval(BaseModel):
    default_interval: float
    data_interval: float | None = None
    data_trigger: float | None = None
    process_trigger: float | None = None

class Triggers(BaseModel):
    trigger_type: str
    node_id: str
    device_id: str
    topic: str
    source: dict
    condition: str
#S7comm specific models
class S7commTriggers(BaseModel):
    trigger_type: str
    name: str
    description: str | None = None
    db_number: int
    read_size: int
    data_type: str
    byte_offset: int
    bit_offset: int
    units: str | None = None
    condition: bool

class S7commVariables(BaseModel):
    name: str
    data_type:str
    byte_offset: int
    bit_offset: int
    units: str

class DataBlock(BaseModel):
    name: str
    db_number: int
    read_size: int
    byte_offset: int
    variables: list[S7commVariables]

class S7CommDeviceServiceConfig(BaseModel):
    device: Device
    polling: PollingInterval
    triggers: list[Triggers]
    data_block: DataBlock | None = None

#USB microphone models
class USBtrigger(BaseModel):
    trigger_type: str
    name: str
    description: str | None = None
    topic: str
    data_type: str
    units: str | None = None
    condition: bool

class USBDevice(BaseModel):
    name: str
    data_type: str
    units: str | None = None
    samplerate: int
    channel: int

class USBMicrophoneDevice(BaseModel):
    device: Device
    triggers: list[Triggers]
    USB_device: USBDevice





