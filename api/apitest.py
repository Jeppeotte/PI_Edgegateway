from pathlib import Path
from models.devicemodels import DeviceService
from ruamel.yaml import YAML

# Define the path to the metadata.yaml files to add the service inside of that
mounted_dir = Path(r"C:\Users\jeppe\OneDrive - Aalborg Universitet\Masters\4. Semester\Gateway Configurator")

device_id  = "test1"


yaml = YAML()
yaml.preserve_quotes = True
yaml.indent(mapping=2, sequence=4, offset=2)

# Define the path to the metadata.yaml files to add the service inside of that
metadata_path = mounted_dir.joinpath("core/metadata.yaml")

if not metadata_path.exists():
    print(f"Cant find the metadata_path: {metadata_path}")

with open(metadata_path, 'r') as f:
    metadata = yaml.load(f)

device_ts = None

for device in metadata["services"]["device_services"]:
    # Finding the device service which need to be started (device_ts, device to start)
    if device.get("device_id") == device_id:
        device_ts = DeviceService(**device)
if device_ts:
    # Check if the config file path exist
    device_config_path = Path(device_ts.config)
    if not device_config_path.exists():
        print(f"No such configfile at position: {device_config_path}")

else:
    print(f"Could not find device: {device_id}")



