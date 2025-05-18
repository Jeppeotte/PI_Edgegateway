from fastapi import APIRouter, HTTPException
from pathlib import Path
from models.devicemodels import S7CommDeviceServiceConfig, DeviceService, USBMicrophoneDevice
from ruamel.yaml import YAML
import docker
from docker.errors import ImageNotFound, APIError, ContainerError
import logging
import sys
import os


logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)]
)

logger = logging.getLogger(__name__)


router = APIRouter(prefix="/api/add_devices")

#Directory for docker container
mounted_dir = Path("/mounted_dir")

client = docker.from_env()

def get_current_container_id():
    """Get current container ID in a cross-platform way"""
    try:
        # Method 1: Linux containers (works on Raspberry Pi)
        if os.path.exists("/proc/self/cgroup"):
            with open("/proc/self/cgroup") as f:
                for line in f:
                    if "docker" in line:
                        return line.strip().split("/")[-1]

        # Method 2: Docker Desktop (Windows/Mac)
        hostname = os.getenv("HOSTNAME")
        if hostname:
            try:
                # Verify this is actually a container ID
                client.containers.get(hostname)
                return hostname
            except docker.errors.NotFound:
                pass

        # Method 3: Fallback for other cases
        return os.getenv("CONTAINER_ID", None)
    except Exception as e:
        logger.error(f"Warning: Could not determine container ID: {e}")
        return None


# Get container ID
container_id = get_current_container_id()

if not container_id:
    logger.error("Could not determine container ID")
    raise RuntimeError("Could not determine container ID")

try:
    container = client.containers.get(container_id)
    mounts = container.attrs["Mounts"]

    # Find the mounted directory
    host_mounted_dir = None
    for mount in mounts:
        if mount["Destination"] == "/mounted_dir":
            host_mounted_dir = Path(mount["Source"])
            break

    if not host_mounted_dir:
        logger.error("Could not find mounted directory in container mounts")
        raise RuntimeError("Could not find mounted directory in container mounts")

except docker.errors.APIError as e:
    logger.error(f"Docker API error: {e}")
    raise RuntimeError(f"Docker API error: {e}")

host_platform = os.getenv("HOST_PLATFORM", "").lower()
host_arch = os.getenv("HOST_ARCH", "").lower()

@router.post("/add_S7_device")
async def add_S7_device(serviceconfig: S7CommDeviceServiceConfig):
    if host_arch not in ["x86_64", "arm64", "amd64"]:
        raise HTTPException(status_code=400, detail=f"Unsupported host architecture: {host_arch}")

    #Create the config file for the device service
    try:
        # Define the directory for the device service
        configfile_path = mounted_dir.joinpath(f"devices/{serviceconfig.device.protocol_type}/{serviceconfig.device.device_id}.yaml")
        # Ensure the parent directories exist
        configfile_path.parent.mkdir(parents=True, exist_ok=True)
        # Create the file if it doesn't exist
        if not configfile_path.exists():
            configfile_path.touch()

        yaml = YAML()
        yaml.preserve_quotes = True
        yaml.indent(mapping=2, sequence=4, offset=2)

        with open(configfile_path, 'w') as f:
            yaml.dump(serviceconfig.model_dump(), f)

        if not configfile_path.exists():
            raise (f"File was not created at: {configfile_path}")

        try:
            # Define the path to the metadata.yaml files to add the service inside of that
            metadata_path = mounted_dir.joinpath("core/metadata.yaml")

            if not metadata_path.exists():
                raise HTTPException(status_code=500,
                                    detail=f"metadata.yaml does not exist in the following path {metadata_path}")

            with open(metadata_path, 'r') as f:
                metadata = yaml.load(f)

            configfile_path = f"devices/{serviceconfig.device.protocol_type}/{serviceconfig.device.device_id}.yaml"

            device_info = DeviceService(device_id= serviceconfig.device.device_id,
                          protocol_type= serviceconfig.device.protocol_type,
                          config= configfile_path,
                          tested= False,
                          activated= True)

            # If there is nothing under device_services, make it a list to that entries can be appended
            if metadata["services"]["device_services"] is None:
                metadata["services"]["device_services"] = []

            # Append the information of the device service
            metadata["services"]["device_services"].append(device_info.model_dump())

            with open(metadata_path, 'w') as f:
                yaml.dump(metadata, f)

            # Pull container if it is not already on the device
            client.images.pull("jeppeotte/s7comm_device_service", tag="latest")

            # Start the container
            try:
                container = client.containers.run(
                    name=f"{serviceconfig.device.device_id}",
                    image="jeppeotte/s7comm_device_service:latest",
                    volumes={
                        host_mounted_dir: {"bind": "/mounted_dir", "mode": "rw"},
                    },
                    command=[
                        "--device_service_config_path", f"{configfile_path}"
                    ],
                    extra_hosts={"localhost": "host-gateway"},
                    detach=True,
                    restart_policy={"Name": "unless-stopped"}
                )

            except Exception as e:
                raise HTTPException(status_code=500, detail=str(e))

        except Exception as e:
            raise HTTPException(status_code=500, detail=str(e))

        return {"configfile_path": configfile_path}

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/add_USB_microphone")
async def add_USB_microphone(serviceconfig: USBMicrophoneDevice):
    if host_platform != "linux":
        raise HTTPException(status_code=400, detail="This service only works on Linux hosts.")

    if host_arch not in ["x86_64", "arm64", "amd64"]:
        raise HTTPException(status_code=400, detail=f"Unsupported host architecture: {host_arch}")

    #Create the config file for the device service
    try:
        # Define the directory for the device service
        configfile_path = mounted_dir.joinpath(f"devices/{serviceconfig.device.protocol_type}/{serviceconfig.device.device_id}.yaml")
        # Ensure the parent directories exist
        configfile_path.parent.mkdir(parents=True, exist_ok=True)
        # Create the file if it doesn't exist
        if not configfile_path.exists():
            configfile_path.touch()

        yaml = YAML()
        yaml.preserve_quotes = True
        yaml.indent(mapping=2, sequence=4, offset=2)

        with open(configfile_path, 'w') as f:
            yaml.dump(serviceconfig.model_dump(), f)

        if not configfile_path.exists():
            raise (f"File was not created at: {configfile_path}")

        try:
            # Define the path to the metadata.yaml files to add the service inside of that
            metadata_path = mounted_dir.joinpath("core/metadata.yaml")

            if not metadata_path.exists():
                raise HTTPException(status_code=500,
                                    detail=f"metadata.yaml does not exist in the following path {metadata_path}")

            with open(metadata_path, 'r') as f:
                metadata = yaml.load(f)

            configfile_path = f"devices/{serviceconfig.device.protocol_type}/{serviceconfig.device.device_id}.yaml"

            device_info = DeviceService(device_id= serviceconfig.device.device_id,
                          protocol_type= serviceconfig.device.protocol_type,
                          config= configfile_path,
                          tested= False,
                          activated= True)

            # If there is nothing under device_services, make it a list to that entries can be appended
            if metadata["services"]["device_services"] is None:
                metadata["services"]["device_services"] = []

            # Append the information of the device service
            metadata["services"]["device_services"].append(device_info.model_dump())

            with open(metadata_path, 'w') as f:
                yaml.dump(metadata, f)

            # Get information about the backend for sending data:
            # Define the path to the mqtT_publisher.yaml files to add the service inside of that
            mqtt_path = mounted_dir.joinpath("applications/MQTT/MQTT_config.yaml")

            if not mqtt_path.exists():
                raise HTTPException(status_code=500,
                                    detail=f"MQTT config file does not exist in the following path {mqtt_path}")

            with open(mqtt_path, 'r') as f:
                mqtt_config = yaml.load(f)

            backend_ip = mqtt_config["broker"].get("ip","")
            # Pull container if it is not already on the device
            try:
                client.images.pull("jeppeotte/usb_microphone_service", tag="latest")
            except ImageNotFound:
                raise HTTPException(status_code=500,
                                    detail="Docker image not found: jeppeotte/usb_microphone_service:0.0.1")
            except APIError as e:
                if "no matching manifest for" in str(e.explanation).lower():
                    raise HTTPException(
                        status_code=500,
                        detail="Incompatible image for this machine's architecture (e.g., x86_64 vs ARM)."
                    )
                raise HTTPException(status_code=500, detail=f"Docker API error: {str(e)}")

            # Start the container
            try:
                container = client.containers.run(
                    name=f"{serviceconfig.device.device_id}",
                    image="jeppeotte/usb_microphone_service:latest",
                    volumes={
                        host_mounted_dir: {"bind": "/mounted_dir", "mode": "rw"},
                    },
                    command=[
                        "--device_service_config_path", f"{configfile_path}",
                        "--backend_ip", f"{backend_ip}"
                    ],
                    extra_hosts={"localhost": "host-gateway"},
                    devices=["/dev/snd"],
                    detach=True,
                    restart_policy={"Name": "unless-stopped"}
                )
            except ContainerError as e:
                raise HTTPException(status_code=500, detail=f"Failed to start container: {str(e)}")
            except APIError as e:
                raise HTTPException(status_code=500, detail=f"Docker API error during container run: {str(e)}")
            except Exception as e:
                raise HTTPException(status_code=500, detail=f"Unexpected error while starting container: {str(e)}")

            return {"configfile_path": configfile_path}

        except Exception as e:
            logger.error(e)
            raise HTTPException(status_code=500, detail=str(e))

    except Exception as e:
        logger.error(e)
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/test_service")
async def test_device_service(device_id: str):
    # Find the information about the device_service so that it can be tested:
    try:
        yaml = YAML()
        yaml.preserve_quotes = True
        yaml.indent(mapping=2, sequence=4, offset=2)

        # Define the path to the metadata.yaml files to add the service inside of that
        metadata_path = mounted_dir.joinpath("core/metadata.yaml")

        if not metadata_path.exists():
            raise HTTPException(status_code=500,
                                detail=f"metadata.yaml does not exist in the following path {metadata_path}")

        with open(metadata_path, 'r') as f:
            metadata = yaml.load(f)

        for device in metadata["services"]["device_services"]:
            # Finding the device service which need to be tested (device_ft, device for test)
            if device.get("device_id") == device_id:
                device_ft = DeviceService(**device)

        # Check if the config file path exist
        device_config_path = Path(device_ft.config)
        if not device_config_path.exists():
            raise HTTPException(status_code=500,
                                detail=f"metadata.yaml does not exist in the following path {metadata_path}")

        return "The test script has not yet been made"

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/start_service")
async def start_device_service(device_id: str):
    # Find the information about the device_service so that it can be deleted:
    try:
        yaml = YAML()
        yaml.preserve_quotes = True
        yaml.indent(mapping=2, sequence=4, offset=2)

        # Define the path to the metadata.yaml files to add the service inside of that
        metadata_path = mounted_dir.joinpath("core/metadata.yaml")

        if not metadata_path.exists():
            raise HTTPException(status_code=500,
                                detail=f"metadata.yaml does not exist in the following path {metadata_path}")

        with open(metadata_path, 'r') as f:
            metadata = yaml.load(f)

        for device in metadata["services"]["device_services"]:
            # Finding the device service which need to be tested (device_ft, device for test)
            if device.get("device_id") == device_id:
                device_ft = DeviceService(**device)

        # Check if the config file path exist
        device_config_path = Path(device_ft.config)
        if not device_config_path.exists():
            raise HTTPException(status_code=500,
                                detail=f"metadata.yaml does not exist in the following path {metadata_path}")

        return "The test script has not yet been made"

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    return

@router.post("/restart_service")
async def restart_service(device_id: str):
    try:
        container = client.containers.get(device_id)

        container.restart(timeout=5)

        # Refresh state and check if running
        container.reload()
        if container.status == "running":
            return {"message": f"Container '{device_id}' successfully restarted."}
        else:
            raise HTTPException(status_code=500, detail=f"Container '{device_id}' not running after restart.")

    except docker.errors.NotFound:
        raise HTTPException(status_code=404, detail=f"Container '{device_id}' not found.")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to restart container: {str(e)}")

@router.post("/delete_device_service")
async def delete_device_service(device_id: str):
    # Find the information about the device_service so that it can be tested:
    try:
        yaml = YAML()
        yaml.preserve_quotes = True
        yaml.indent(mapping=2, sequence=4, offset=2)

        # Define the path to the metadata.yaml files to add the service inside of that
        metadata_path = mounted_dir.joinpath("core/metadata.yaml")

        with open(metadata_path, 'r') as f:
            metadata = yaml.load(f)

        device_services = metadata["services"].get("device_services", [])

        device_fd = None

        # Find the device which need to be deleted
        for device in metadata["services"]["device_services"]:
            if device.get("device_id") == device_id:
                device_fd = DeviceService(**device)

        # If the device is within the metadata file begin the process of deletion
        if device_fd:
            config_file_path = mounted_dir.joinpath(f"{device_fd.config}")

            if config_file_path.exists():
                try:
                    config_file_path.unlink()
                    print(f"Deleted config file: {config_file_path}")
                except Exception as e:
                    print(f"Error deleting config file: {e}")
            else:
                print(f"No config file found at: {config_file_path}")

            # Remove the device from the list
            metadata["services"]["device_services"] = [
                device for device in device_services if device.get("device_id") != device_id
            ]

            try:
                with open(metadata_path, 'w') as f:
                    yaml.dump(metadata, f)
                print(f"Device service '{device_id}' removed successfully.")
            except Exception as e:
                print(f"Error writing YAML file: {e}")
        else:
            print(f"No device found with device_id: {device_id}")

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


    try:
        container = client.containers.get(device_id)
        container.remove(force=True)  # force=True will stop it if it's running
        print("Container removed.")
        return {"message": f"Device service '{device_id}' was successfully removed ."}

    except docker.errors.NotFound:
        return {"message": f"Device service '{device_id}' was successfully removed. Container was not running"}
    except docker.errors.APIError as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/get_container_logs")
async def get_container_logs(device_id:str):
    try:
        # Replace this logic with however you're mapping device_id to container
        container = client.containers.get(device_id)  # assuming device_id is the container name or ID
        logs = container.logs(tail=10).decode('utf-8')
        return {"logs": logs}

    except docker.errors.NotFound:
        logger.warning(f"Container '{device_id}' not found.")
        raise HTTPException(status_code=404, detail=f"Container '{device_id}' not found.")

    except docker.errors.APIError as e:
        logger.error(f"Docker API error: {e}")
        raise HTTPException(status_code=500, detail="Docker API error while retrieving logs.")

    except Exception as e:
        logger.exception(f"Unexpected error while retrieving logs: {e}")
        raise HTTPException(status_code=500, detail="Unexpected error while retrieving logs.")
