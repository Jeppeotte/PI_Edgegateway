import docker
import os
from pathlib import Path
import platform

client = docker.from_env()

# Define the path to the metadata.yaml files to add the service inside of that
mounted_dir = Path(r"C:\Users\jeppe\OneDrive - Aalborg Universitet\Masters\4. Semester\Gateway Configurator\gateway_folder")

try:
    client.images.pull(repository="jeppeotte/gateway_configurator", tag="latest")
except docker.errors.APIError as e:
    print(f"Error: {e.explanation}")
    exit()

print("Pulled image")

# Get host env vars
host_platform = os.getenv("HOST_PLATFORM", platform.system()).lower()
print(host_platform)
host_arch = os.getenv("HOST_ARCH", platform.machine()).lower()
print(host_arch)

container = client.containers.run(
            name="configurator",
            image="jeppeotte/gateway_configurator:latest",
            volumes={
                mounted_dir: {"bind": "/mounted_dir", "mode": "rw"},
                "/var/run/docker.sock": {"bind": "/var/run/docker.sock", "mode": "rw"},
            },
            environment={
                "HOST_PLATFORM": host_platform,
                "HOST_ARCH": host_arch,
            },
            ports={'8000/tcp': 8000},
            privileged=True,
            detach=True
        )