from fastapi import APIRouter, HTTPException
from ruamel.yaml import YAML
from pathlib import Path
from pydantic import BaseModel
from models.devicemodels import ApplicationService
import docker
import os

# Define the structure for configuring the edge node
class NodeConfig(BaseModel):
    group_id: str
    node_id: str
    description: str | None = None
    ip: str
    app_services: list[str] = []

class MQTTConfig(BaseModel):
    ip: str

router = APIRouter(prefix="/api/configure_node")

#Directory for running locally
#local_dir = r"C:\Users\jeppe\OneDrive - Aalborg Universitet\Masters\4. Semester\Gateway Configurator"
#mounted_dir = Path(local_dir)
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
        print(f"Warning: Could not determine container ID: {e}")
        return None


# Get container ID
container_id = get_current_container_id()

if not container_id:
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
        raise RuntimeError("Could not find mounted directory in container mounts")

except docker.errors.APIError as e:
    raise RuntimeError(f"Docker API error: {e}")

@router.post("/configure_node")# API for edge node
async def configure_node(config: NodeConfig):
    #Configure the metadata on the node which has been added
    try:
        # Define the core directory path for metadata.yaml
        core_path = mounted_dir.joinpath("core")
        # Check if path exist and create it if not:
        # Create the metadata file if it does not exsist
        core_path.mkdir(parents=True, exist_ok=True)
        # Define the file path for metadata.yaml
        metadata_path = core_path.joinpath("metadata.yaml")

        # Load existing YAML
        yaml = YAML()
        yaml.preserve_quotes = True
        yaml.indent(mapping=2, sequence=4, offset=2)

        if not metadata_path.exists():
            raise HTTPException(status_code=500, detail=f"metadata.yaml does not exist in the following path {metadata_path}")

        with open(metadata_path, 'r') as f:
            metadata = yaml.load(f)

        # Update identity
        metadata["identity"]["group_id"] = config.group_id
        metadata["identity"]["node_id"] = config.node_id
        metadata["identity"]["description"] = config.description
        metadata["identity"]["ip"] = config.ip

        # Enable application services based on connections
        app_services = metadata["services"].get("application_services", [])
        for service in config.app_services:
            matched = False
            for application in app_services:
                if application.get("service") == service:
                    application["enabled"] = True
                    matched = True
                    print(f"Enabled service: {service}")
                    break

            if not matched:
                raise HTTPException(status_code=400, detail=f"Service '{service}' not found in metadata.")

        # Save updated YAML back to file
        with open(metadata_path, 'w') as f:
            yaml.dump(metadata, f)

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

    return

@router.post("/MQTT")
async def configure_and_start_mqtt(mqtt_config: MQTTConfig):
    try:
        # Define the file path for mqtt_publisher.yaml
        config_path = mounted_dir.joinpath("applications/MQTT/mqtt_publisher.yaml")

        # Load existing YAML
        yaml = YAML()
        yaml.preserve_quotes = True
        yaml.indent(mapping=2, sequence=4, offset=2)

        if not config_path.exists():
            # Create file path if it does not exist
            config_path.mkdir(parents=True, exist_ok=True)

        with open(config_path, 'r') as f:
            config = yaml.load(f)

        config["broker"]["ip"] = mqtt_config.ip

        # Save updated YAML back to file
        with open(config_path, 'w') as f:
            yaml.dump(config, f)

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Could not configure MQTT_config file at path {config_path}, with error {e}")

    # If no errors have been detected and the config file has been successfully edited start the mqtt_publisher
    try:
        container = client.containers.run(
            name="MQTT",
            image="mqtt_publisher:0.1.1",
            volumes={
                host_mounted_dir: {"bind": "/mounted_dir", "mode": "rw"},
            },
            extra_hosts={"localhost": "host-gateway"},
            detach=True,
            restart_policy={"Name": "unless-stopped"}
        )
        return "MQTT application has been launched"
    except docker.errors.DockerException as e:
        raise HTTPException(status_code=500, detail=f"Docker error: {str(e)}")

@router.post("/delete_node")
async def delete_node():
    # Gets all the devices and remove their containers and config files so that the node can be reconfigured
    try:
        yaml = YAML()
        # Define the path to the metadata.yaml files to add the service inside of that
        metadata_path = mounted_dir.joinpath("core/metadata.yaml")

        with open(metadata_path, 'r') as f:
            metadata = yaml.load(f)

        device_services = metadata["services"].get("device_services", [])
        app_services = metadata["services"].get("application_services", [])

        for application in app_services:
            if application.get("enabled") == True:
                application["enabled"] = False
                service = application.get("service")
                # Stop and remove container
                try:
                    container = client.containers.get(service)
                    container.remove(force=True)
                    print(f"Stopped and removed container: {service}")
                except docker.errors.NotFound:
                    print(f"Container {service} not found.")
                except docker.errors.APIError as e:
                    print(f"Error removing container {service}: {e.explanation}")

        # Loop over all device services
        if device_services:
            for device in device_services:
                device_id = device.get("device_id")
                config_file_path = mounted_dir.joinpath(f"{device.get("config_path")}.yaml")

                # Stop and remove container
                try:
                    container = client.containers.get(device_id)
                    container.remove(force=True)
                    print(f"Stopped and removed container: {device_id}")
                except docker.errors.NotFound:
                    print(f"Container {device_id} not found.")
                except docker.errors.APIError as e:
                    print(f"Error removing container {device_id}: {e.explanation}")

                # Delete config file
                if config_file_path:
                    if config_file_path.exists():
                        try:
                            config_file_path.unlink()
                            print(f"Deleted config file: {config_file_path}")
                        except Exception as e:
                            print(f"Error deleting config file {config_file_path}: {e}")
                    else:
                        print(f"No config file found at: {config_file_path}")
                else:
                    print(f"No config_path provided for device: {device_id}")

            #Clear device_services
            metadata["services"]["device_services"] = []

        # Write updated metadata
        try:
            with open(metadata_path, 'w') as f:
                yaml.dump(metadata, f)
            print("Metadata YAML updated successfully.")
        except Exception as e:
            print(f"Error writing updated YAML file: {e}")


    except Exception as e:
        raise(e)
