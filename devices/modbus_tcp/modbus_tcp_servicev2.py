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
import sys

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
    device = config.device
    polling = config.polling
    holding_registers = config.holding_registers
    coils = config.coils

    # Return all data from configfile
    return device, polling, holding_registers, coils

# Connecting to the internal message bus
def valkey_connection():
    valkey_client = valkey.Valkey(host="localhost", port=6379)

    # Test connection
    if not valkey_client.ping():
        print("No connection to the internal message bus")
        exit()

    print("Connection to the internal message bus was successful")
    return  valkey_client

async def connect_modbus_client(ip, port):
    try:
        # Connect to modbus device
        modbus_client = AsyncModbusTcpClient(ip, port=port)

        await modbus_client.connect()

        if not modbus_client.connect():
            raise ConnectionError(f"Failed to connect to the Modbus device at {ip}:{port}.")

        print(f"Connection to the Modbus device at {ip}:{port} was successful!")
        return modbus_client

    except ConnectionError as e:
        print(f"Connection error: {e} \n"
              "Make sure that modbus devices is running")
        exit()

    except Exception as e:
        print(f"Could not connect to the modbus device, with the following error: {e}")
        exit()

def create_datadict(
        indexes: List[int],
        names: List[str],
        data_types: List[str],
        values: List[dict],
        units: List[str],
        sampletime):

    current_time = time.time()
    #Creating metrics list
    metrics =[
            {
                "name": names[i],
                "timestamp": sampletime,
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
async def reading_task(modbus_client,valkey_client,address0,count,unitid,data_types,units,names,topic):
    global previous_data

    try:
        # Read holding register
        results = await modbus_client.read_holding_registers(
            address=address0,
            count=count,
            slave=unitid)
        sampletime = time.time()
        if results.isError():
            print(f"Received exception from device ({results})")
            modbus_client.close()
            raise ModbusException

        data = results.registers

        if previous_data is None:
            previous_data = data.copy()
            print("This is the printed because no previouse data")
            indexes = range(len(names))
            data_struct = create_datadict(indexes,names,data_types,data,units,sampletime)
            #Publishing data to the messagebus
            valkey_client.publish(topic,json.dumps(data_struct))
            print(data_struct)
            return

        if data != previous_data:
            print("These are the the values changed in the register")
            #Find changed indexes
            changed_indexes = [i for i, (previous, current) in enumerate(zip(previous_data, data))
                               if previous != current]

            data_struct = create_datadict(changed_indexes,names,data_types,data,units,sampletime)
            print(data_struct)
            #Publishing data to the messagebus
            valkey_client.publish(topic,json.dumps(data_struct))
            #Changing the previous data set
            previous_data = data.copy()

            return

        print("No new data in the registers")

    except ModbusException as exc:
        print(f"Received ModbusException({exc}) from library")
        modbus_client.close()
        raise exc

    except Exception as e:
        print(f"There was and error:{e}")
        raise e


# Begin the polling of data from holding registers
async def begin_HR_polling(valkey_client, device, polling, holding_registers):

    try:
        # Connect to modbus device
        modbus_client = AsyncModbusTcpClient(device.ip, port=device.port)

        if not await modbus_client.connect():
            raise ConnectionError(f"Failed to connect to the Modbus device at {device.ip}:{device.port}.")

    except ConnectionError as e:
        print(f"Connection error: {e} \n"
              "Make sure that modbus devices is running")
        sys.exit()

    except Exception as e:
        print(f"Could not connect to the modbus device, with the following error: {e}")
        sys.exit()

    print(f"Connection to the Modbus device at {device.ip}:{device.port} was successful!")
    # Create topic for publishing data
    topic = f"spBv1.0/{device.group_id}/DDATA/{device.node_id}/{device.device_id}"

    # Get the poll timer for the holding registers
    poll_timer = polling.default_register_interval

    # Separate the holding registers information
    names = [reg.name for reg in holding_registers]
    addresses = [reg.address for reg in holding_registers]
    data_types = [reg.data_type for reg in holding_registers]
    units = [reg.units for reg in holding_registers]

    # Defining addresses to poll data from
    count = len(addresses) # the number of addresses needed to pull
    address0 = addresses[0]-1 # the address to begin counting from

    print(f"Now polling data every {poll_timer} seconds")



    while True:
        task = asyncio.create_task(reading_task(modbus_client,valkey_client,
                                                address0=address0,count=count,
                                                unitid=device.unit_id,data_types=data_types,
                                                units=units,names=names,topic=topic))

        await asyncio.sleep(poll_timer)
        # If the task return an exception
        if task.exception() is not None:
            print("There was an error inside the data polling")
            break

    print("The system is turning off")
if __name__ == "__main__":
    # Get configuration from config file
    device_config_path = "configs/modbus_tcp/plc-001.yaml"
    # Get the configuration for the device
    device, polling, holding_registers, coils = get_device_config(device_config_path)
    # Connect to valkey_client the internal message bus
    valkey_client = valkey_connection()


    asyncio.run(begin_HR_polling(valkey_client, device, polling, holding_registers))