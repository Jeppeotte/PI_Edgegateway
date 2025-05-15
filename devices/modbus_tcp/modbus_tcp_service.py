import time
import valkey
import json
from pymodbus.client import AsyncModbusTcpClient
import yaml
from pathlib import Path
import asyncio
from pymodbus import ModbusException
from typing import List
from models.devicemodels import ModbusDeviceServiceConfig


# Get configuration from config file
def get_device_config(device_config_path):
    config_path = Path.cwd().parent.joinpath(device_config_path)

    try:
        with open(config_path, 'r') as f:
            device_config = yaml.safe_load(f)

    except FileNotFoundError:
        print(f"Error: The configuration file '{config_path}' does not exist.")
        exit()

    except yaml.YAMLError as e:
        print(f"Error reading the YAML file: {e}")
        exit()

    config = ModbusDeviceServiceConfig.model_validate(device_config)
    device = config.device[0]
    polling = config.polling
    holding_registers = config.holding_registers
    coils = config.coils

    # Extract device information
    device_information = device_config.get("device", {})
    GROUP_ID = device_information.get('group_id', None)
    NODE_ID = device_information.get('node_id', None)
    DEVICE_ID = device_information.get('device_id', None)
    MODBUSIP = device_information.get("ip", None)
    MODBUSPORT = device_information.get("port", None)
    UNITID = device_information.get("unit_id", None)

    # Poll timers
    poll_timers = device_config.get("polling", {})
    HR_poll_timer = poll_timers.get("default_register_interval", None)

    # Holding registers
    holding_registers = device_config.get("holding_registers", [])
    names = [item.get('name') for item in holding_registers]
    addresses = [item.get('address') for item in holding_registers]
    types = [item.get('type') for item in holding_registers]
    units = [item.get('units') for item in holding_registers]

    # Return all relevant information, can expand based on usage
    return {
        "GROUP_ID": GROUP_ID,
        "NODE_ID": NODE_ID,
        "DEVICE_ID": DEVICE_ID,
        "MODBUSIP": MODBUSIP,
        "MODBUSPORT": MODBUSPORT,
        "UNITID": UNITID,
        "HR_poll_timer": HR_poll_timer,
        "holding_registers": {
            "names": names,
            "addresses": addresses,
            "types": types,
            "units": units
        }
    }

# Connecting to the internal message bus
def valkey_connection():
    valkey_client = valkey.Valkey(host="localhost", port=6379)

    # Test connection
    if not valkey_client.ping():
        print("No connection to the internal message bus")
        exit()

    print("Connection to the internal message bus was successful")
    return  valkey_client

def create_datadict(
        indexes: List[int],
        names: List[str],
        data_types: List[str],
        values: List[dict],
        units: List[str]):

    current_time = time.time()
    #Creating metrics list
    metrics =[
            {
                "name": names[i],
                "timestamp": current_time,
                "dataType": data_types[i],
                "value": values[i],
                "unit": units[i]
            }
            for i in indexes]

    return {
        "timestamp": current_time,
        "metrics": metrics
    }

previous_data = None
# Reads the desired holding registers from the device.
async def reading_task(modbusclient,addresses,count,unitid,data_types,units,names,valkey_client,topic):
    global previous_data

    try:
        # Read holding register
        results = await modbusclient.read_holding_registers(
            address=addresses,
            count=count,
            slave=unitid)

        if results.isError():
            print(f"Received exception from device ({results})")
            modbusclient.close()
            return

        data = results.registers

        if previous_data is None:
            previous_data = data.copy()
            print("This is the printed because no previouse data")
            indexes = range(len(names))
            data_struct = create_datadict(indexes,names,data_types,data,units)
            #Publishing data to the messagebus
            valkey_client.publish(topic,json.dumps(data_struct))
            print(data_struct)
            return

        if data != previous_data:
            print("These are the the values changed in the register")
            #Find changed indexes
            changed_indexes = [i for i, (previous, current) in enumerate(zip(previous_data, data))
                               if previous != current]

            data_struct = create_datadict(changed_indexes,names,data_types,data,units)
            print(data_struct)
            #Publishing data to the messagebus
            valkey_client.publish(topic,json.dumps(data_struct))
            #Changing the previous data set
            previous_data = data.copy()

            return

        print("No new data in the registers")


    except ModbusException as exc:
        print(f"Received ModbusException({exc}) from library")
        modbusclient.close()
        return

# Begin the polling of data from holding registers
async def begin_HR_polling(config):
    # Connect to modbus client
    MODBUSIP = config["MODBUSIP"]
    MODBUSPORT = config["MODBUSPORT"]
    # Connect to modbus device
    modbusclient = AsyncModbusTcpClient(MODBUSIP, port=MODBUSPORT)
    await modbusclient.connect()

    # Connecting to the internal message bus
    valkey_client = valkey_connection()

    # Check if the client is connected
    if modbusclient.connected:
        print("Connection to the Modbus device was successful!")

    else:
        print("Could not connect to the modbus device")
        print("Check if it is turned on and that it is configured correctly")
        exit()

    group_id = config["GROUP_ID"]
    node_id = config["NODE_ID"]
    device_id = config["DEVICE_ID"]
    unitid = config["UNITID"]
    polltimer = config["HR_poll_timer"]
    holding_registers = config["holding_registers"]
    addresses = holding_registers["addresses"]
    data_types = holding_registers["types"]
    units = holding_registers["units"]
    names = holding_registers["names"]
    # Defining addresses to poll data from
    count = len(addresses) # the number of addresses needed to pull
    address0 = addresses[0]-1 # the address to begin counting from
    print(f"Now polling data every {polltimer} seconds")
    #Topic for publishing data
    topic = f"spBv1.0/{group_id}/DDATA/{node_id}/{device_id}"

    while True:
        asyncio.create_task(reading_task(modbusclient,address0,count,unitid,data_types,units,names,valkey_client,topic))
        await asyncio.sleep(polltimer)


if __name__ == "__main__":
    # Get configuration from config file
    device_config_path = "configs/modbus_tcp/plc-001.yaml"

    config = get_device_config(device_config_path)
    asyncio.run(begin_HR_polling(config))