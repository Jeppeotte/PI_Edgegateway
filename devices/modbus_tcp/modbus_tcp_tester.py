import argparse
from pathlib import Path
from ruamel.yaml import YAML
from pymodbus.client import ModbusTcpClient
from models.devicemodels import ModbusDeviceServiceConfig
#Purpose is to validate the connections between the edge device and the modbus device
#This change the status of the modbus client within the metadata, to allow the Modbus service to run

#Setting the path for the config file
parser = argparse.ArgumentParser()
parser.add_argument("--configfile_path", required=False, default="devices/configs/modbus_tcp/plc-001.yaml")

args = parser.parse_args()

def get_device_config(client_config_path):
    # Getting the information about the device
    configfile_path = Path.cwd().parent.joinpath(client_config_path)
    yaml = YAML()

    with open(configfile_path, 'r') as f:
        device_config = yaml.load(f)

    config = ModbusDeviceServiceConfig.model_validate(device_config)
    device = config.device
    polling = config.polling
    holding_registers = config.holding_registers
    coils = config.coils

    return device, polling, holding_registers, coils

def check_connection(ip, port):
    try:
        # Connect to modbus device
        modbusclient = ModbusTcpClient(ip, port=port)
        if not modbusclient.connect():
            raise ConnectionError(f"Failed to connect to the Modbus device at {ip}:{port}.")

        print(f"Connection to the Modbus device at {ip}:{port} was successful!")
        return modbusclient

    except ConnectionError as e:
        print(f"Connection error: {e} \n"
              "Make sure that modbus devices is running")
        exit()

    except Exception as e:
        print(f"Could not connect to the modbus device, with the following error: {e}")
        exit()

def check_holding_registers(device,holding_registers,modbusclient):
    # Check if the provided addresses for the holding registers exist by having data inside of them
    existing_registers = []
    nonexistent_registers = []

    for holding_register in holding_registers:
        address = holding_register.address
        count_start = address - 1

        try:
            # Read the holding register at the predefined address
            result = modbusclient.read_holding_registers(address=count_start, count=1, slave=device.unit_id)

            # If there is no error in the result
            if not result.isError():
                # Check if the register has data
                if result.registers:
                    existing_registers.append(address)
                else:
                    nonexistent_registers.append(address)
            else:
                nonexistent_registers.append(address)

        except Exception as e:
            print(f"Error while reading register at address {address}: {e}")
            nonexistent_registers.append(address)

    # If there are nonexistent registers, print them and exit
    if nonexistent_registers:
        print(f"The following provided holding register addresses are not existing or could not be read: {nonexistent_registers}")
        print(f"The following holding register addresses exist: {existing_registers}")
        print(f"Please change the configuration of the addresses and try again.")
        return False

    else:
        print("The provided holding register addresses exists")
        return True

def check_coils(device,coils,modbusclient):
    # Check if the provided addresses for the holding registers exist by having data inside of them
    existing_coils = []
    nonexistent_coils = []

    for coil in coils:
        address = coil.address
        count_start = address - 1

        try:
            # Read the coil at the predefined address
            result = modbusclient.read_coils(count_start, count=1, slave=device.unit_id)
            # If there is no error in the result i.e. the coil exists
            if not result.isError():
                # Check if the coil actually has data
                if result.bits[0] is not None:
                    existing_coils.append(address)
                else:
                    nonexistent_coils.append(address)
            else:
                nonexistent_coils.append(address)

        except Exception as e:
            print(f"Error while reading register at address {address}: {e}")
            nonexistent_coils.append(address)

    # If there are nonexistent registers, print them and exit
    if nonexistent_coils:
        print(f"The following provided coil addresses are not existing or could not be read: {nonexistent_coils}")
        print(f"The following coil addresses exist: {existing_coils}")
        print(f"Please change the configuration of the addresses and try again.")
        return False

    else:
        print("The provided coil addresses exists")
        return True

def include_service(device,client_config_path):
    # Include the service information in the metadata
    yaml = YAML()
    yaml.preserve_quotes = True
    yaml.indent(mapping=2, sequence=4, offset=2)

    metadata_path = Path.cwd().joinpath("core/metadata.yaml")
    if Path.exists(metadata_path):
        with open(metadata_path, 'r') as f:
            metadata = yaml.load(f)

        # Modbus services
        modbus_services = metadata["services"]["device_services"]["modbus_tcp"]

        # Check if the device already exist in the metadata file to prevent duplicates.
        device_exists = any(d["device_id"] == str(device.device_id) for d in modbus_services["devices"])

        if device_exists:
            print("A device with the same device_id already exist in the metadata.")
            return False
        else:
            # Update metadata
            modbus_services["enabled"] = True
            modbus_services["devices"].append({"device_id": device.device_id,
                                              "config": client_config_path,
                                              "tested": True})
            #Write to the metadata file
            with open(metadata_path, 'w') as f:
                yaml.dump(metadata, f)
            return True

    else:
        print("The metadata.yaml file is not in the expected location")
        exit()

if __name__ == "__main__":
    try:
        #Get device configuration from the config file
        device, polling, holding_registers, coils = get_device_config(args.configfile_path)
        #Establish a connection to the Modbus device
        modbusclient = check_connection(ip=device.ip, port=device.port)
        #Check if all holding registers exist
        check_1 = check_holding_registers(device, holding_registers, modbusclient)
        #Check if all coils exist
        check_2 = check_coils(device, coils, modbusclient)

        if check_1 and check_2:
            if include_service(device,args.configfile_path):
                # If the service in successfully included in metadata, the service is ready to be used
                print("The devices service has success fully been tested and is ready to be used")

            else:
                print("Reconfigure the device service and try again")
        else:
            print("Reconfigure the device service and try again")

    except Exception as e:
        # Handle unexpected errors in the execution
        print(f"Error occurred: {e}")

