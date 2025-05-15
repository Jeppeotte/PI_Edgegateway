import time
import valkey
import json
from pymodbus.client import ModbusTcpClient
import yaml
from pathlib import Path

# Get configuration from config file
def get_device_config(client_config_path):
    config_path = Path.cwd().parent.joinpath(client_config_path)
    try:
        with open(config_path, 'r') as f:
            device_config = yaml.safe_load(f)
    except FileNotFoundError:
        print(f"Error: The configuration file '{config_path}' does not exist.")
        return None
    except yaml.YAMLError as e:
        print(f"Error reading the YAML file: {e}")
        return None

    # Extract device information with default fallbacks in case of missing keys
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



# Connect to modbus client
def connect_modbus(config):
    MODBUSIP = config["MODBUSIP"]
    MODBUSPORT = config["MODBUSPORT"]
    try:
        # Connect to modbus device
        modbusclient = ModbusTcpClient(MODBUSIP, port=MODBUSPORT)
        modbusclient.connect()
        print("Connection to the Modbus device was successful!")
    except Exception as e:
        print(f"Could not connect to the modbus device, with the following error: {e}")
        exit()

    return modbusclient

# Begin the polling of data from holding registers
def Begin_HR_polling(config,modbusclient):
    polltimer = config["HR_poll_timer"]
    holding_registers = config["holding_registers"]
    addresses = holding_registers["addresses"]
    print(f"Now polling data every {polltimer} seconds")

    # Defining addresses to poll data from
    count = len(addresses) # the number of addresses needed to pull
    address0 = addresses[0]-1 # the address to begin counting from

    while True:
        # Read holding register
        result = modbusclient.read_holding_registers(address=address0, count=count, slave=unitid)  # slave=unit ID
        if not result.isError():
            current_values = result.registers
            changed_values = get_changed_values(current_values)

            if changed_values:
                publish_ddata(changed_values)
                print(f"Published DDATA with changes: {changed_values}")
        else:
            print("Error:", result)
            break
        time.sleep(polltimer)

if __name__ == "__main__":
    # Get configuration from config file
    config_path = "plc-001.yaml"

    config = get_device_config(config_path)

    connect_modbus(config)