from fastapi import APIRouter, HTTPException
from ruamel.yaml import YAML
from pathlib import Path
from pydantic import BaseModel
import docker
import os
import logging
import sys

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)]
)

logger = logging.getLogger(__name__)

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

#Directory for docker container
mounted_dir = Path("/mounted_dir")

client = docker.from_env()

host_platform = os.getenv("HOST_PLATFORM", "").lower()
host_arch = os.getenv("HOST_ARCH", "").lower()

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
    # Configure the metadata on the node which has been added
    try:
        # Define the core directory path for metadata.yaml
        metadata_path = mounted_dir.joinpath("core/metadata.yaml")
        # Ensure the parent directories exist
        metadata_path.parent.mkdir(parents=True, exist_ok=True)

        # Initialize YAML handler
        yaml = YAML()
        yaml.preserve_quotes = True
        yaml.indent(mapping=2, sequence=4, offset=2)

        # Default metadata structure
        default_metadata = {
            "identity": {
                "group_id": config.group_id,
                "node_id": config.node_id,
                "description": config.description or "",
                "ip": config.ip
            },
            "services": {
                "device_services": [],
                "application_services": []
            }
        }

        # Create or load existing metadata
        if not metadata_path.exists():
            metadata = default_metadata
        else:
            with open(metadata_path, 'r') as f:
                metadata = yaml.load(f) or default_metadata

            # Update identity
            metadata["identity"] = {
                "group_id": config.group_id,
                "node_id": config.node_id,
                "description": config.description or metadata["identity"].get("description", ""),
                "ip": config.ip
            }

        # Handle application services
        if config.app_services:
            # Ensure application_services exists
            if "application_services" not in metadata["services"]:
                metadata["services"]["application_services"] = []

            app_services = metadata["services"]["application_services"]

            # Enable requested services
            for service_name in config.app_services:
                service_found = False
                for service in app_services:
                    if service.get("service") == service_name:
                        service["enabled"] = True
                        service_found = True
                        break

                if not service_found:
                    # Create new service with default values if not found
                    app_services.append({
                        "service": service_name,
                        "description": f"Auto-created service {service_name}",
                        "config": f"applications/{service_name}/{service_name}_config.yaml",  # Default empty config
                        "enabled": True
                    })

        # Save metadata
        with open(metadata_path, 'w') as f:
            yaml.dump(metadata, f)

        return {"status": "success", "message": "Node configured successfully"}

    except Exception as e:
        logger.error(f"Error configuring node: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Configuration failed: {str(e)}")

@router.post("/MQTT")
async def configure_and_start_mqtt(mqtt_config: MQTTConfig):
    if host_arch not in ["x86_64", "arm64", "amd64"]:
        raise HTTPException(status_code=400, detail=f"Unsupported host architecture: {host_arch}")

    try:
        # Define the file path for MQTT_config.yaml
        config_path = mounted_dir.joinpath("applications/MQTT/MQTT_config.yaml")
        # Ensure the parent directories exist
        config_path.parent.mkdir(parents=True, exist_ok=True)
        # Create the file if it doesn't exist
        if not config_path.exists():
            config_path.touch()

        # Load config file
        yaml = YAML()
        yaml.preserve_quotes = True
        yaml.indent(mapping=2, sequence=4, offset=2)

        # Default configuration structure
        default_config = {
            "broker": {
                "ip": mqtt_config.ip,
                "port": 1883}}

        # Load existing config or create new one
        if not config_path.exists():
            config = default_config
        else:
            with open(config_path, 'r') as f:
                config = yaml.load(f) or default_config

            # Ensure basic structure exists
            if "broker" not in config:
                config["broker"] = default_config["broker"]

            # Update broker IP (and set default port if not specified)
            config["broker"]["ip"] = mqtt_config.ip
            config["broker"].setdefault("port", 1883)

        # Save updated YAML back to file
        with open(config_path, 'w') as f:
            yaml.dump(config, f)

    except Exception as e:
        logger.error(f"Error updating MQTT config: {str(e)}")
        raise HTTPException(
            status_code=500,
            detail=f"MQTT configuration failed: {str(e)}")

    # First ensure that there is no MQTT container running
    try:
        container = client.containers.get("MQTT")
        container.remove(force=True)
        logger.info(f"Stopped and removed an already running MQTT container")
    except docker.errors.NotFound:
        logger.info(f"No MQTT container found will proceed as planned")

        #Start the mqtt_publisher application
    try:
        container = client.containers.run(
            name="MQTT",
            image="jeppeotte/mqtt_publisher:latest",
            volumes={
                host_mounted_dir: {"bind": "/mounted_dir", "mode": "rw"},
            },
            extra_hosts={"localhost": "host-gateway"},
            detach=True,
            restart_policy={"Name": "unless-stopped"}
        )
        return "MQTT application has been launched"
    except docker.errors.DockerException as e:
        logger.error(f"There was an error with launching the MQTT docker container {e}")
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
