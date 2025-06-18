from fastapi import FastAPI
import uvicorn
import docker
from docker.errors import ImageNotFound, APIError, ContainerError
import logging
import sys

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)]
)

logger = logging.getLogger(__name__)

# Download necessary
client = docker.from_env()

# List of images to pre-pull
images_to_pull = [
    ("jeppeotte/usb_microphone_service", "latest"),
    ("jeppeotte/s7comm_device_service", "latest"),
    ("jeppeotte/mqtt_publisher", "latest")
]

for image, tag in images_to_pull:
    try:
        logger.info(f"Pulling {image}:{tag}...")
        client.images.pull(image, tag=tag)
        logger.info(f"Pulled {image}:{tag}")
    except ImageNotFound:
        logger.error(f"Image not found: {image}:{tag}")
    except APIError as e:
        logger.error(f"Docker API error for {image}:{tag}")
        if "no matching manifest for" in str(e.explanation).lower():
            logger.error("Incompatible image for this machine's architecture (e.g., x86_64 vs ARM).")
        else:
            logger.error(f"Error: {str(e)}")

logger.info("Initializing configurator")

# Initialize FastAPI
app = FastAPI()

# Import API routers
from api.configure_node import router as configure_node_router
from api.add_devices import router as add_devices_router
from api.add_applications import router as add_applications_router

app.include_router(configure_node_router)
app.include_router(add_devices_router)
app.include_router(add_applications_router)

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000)