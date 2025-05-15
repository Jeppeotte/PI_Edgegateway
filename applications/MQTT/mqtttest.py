import subprocess
import os

image_name = 'mqtt_publisher:0.1.1'
mqtt_config = r'C:\Users\jeppe\OneDrive - Aalborg Universitet\Masters\4. Semester\Gateway Configurator\applications\MQTT\mqtt_publisher.yaml'
metadata = r'C:\Users\jeppe\OneDrive - Aalborg Universitet\Masters\4. Semester\Gateway Configurator\core\metadata.yaml'

cmd = [
    'docker', 'run', '-d',
    '-v', f'{mqtt_config}:/config.yaml',
    '-v', f'{metadata}:/metadata.yaml',
    '--add-host', 'host.docker.internal:host-gateway',
    image_name,
    '--mqtt_configfile_path', '/config.yaml',
    '--metadata_path', '/metadata.yaml',
    '--valkey_host', 'host.docker.internal',  # Instead of localhost
]

result = subprocess.run(cmd, capture_output=True, text=True)

if result.returncode == 0:
    print("✅ Container launched successfully!")
    container_id = result.stdout.strip()