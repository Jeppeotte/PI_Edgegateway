import paho.mqtt.client as mqtt
import valkey
import json
import time
import yaml
import logging
import sys
from pathlib import Path

# Configure logging to output INFO and above to stdout
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)]
)

logger = logging.getLogger(__name__)

#Directory for docker container
mounted_dir = Path("/mounted_dir")

def get_node_identity():
    metadata_path = mounted_dir.joinpath("core/metadata.yaml")

    if not metadata_path.exists():
        logger.error(f"Cant find the metadata.yaml file under path: {metadata_path}")
        sys.exit(1)

    # Get the identity of the node
    with open(metadata_path, 'r') as f:
        metadata_config = yaml.safe_load(f)

    return metadata_config["identity"]

def mqtt_connection(identity):
    try:
        #Path to mqtt config file
        mqtt_configfile_path = mounted_dir.joinpath("applications/MQTT/MQTT_config.yaml")

        if not mqtt_configfile_path.exists():
            logger.error(f"Cant find the config file for the mqtt publisher under path: {mqtt_configfile_path}")
            sys.exit(1)


        with open(mqtt_configfile_path, 'r') as f:
            mqtt_config = yaml.safe_load(f)
    except FileNotFoundError:
        logger.error(f"Error: The configuration file '{mqtt_configfile_path}' does not exist.")
        sys.exit(1)

    except yaml.YAMLError as e:
        logger.error(f"Error reading the YAML file: {e}")
        sys.exit(1)

    broker_configuration = mqtt_config.get("broker")
    BROKERIP = broker_configuration['ip']
    BROKERPORT = broker_configuration['port']

    GROUP_ID = identity["group_id"]
    EDGE_NODE_ID = identity["node_id"]
    DBIRTHTOPIC = f"spBv1.0/{GROUP_ID}/NBIRTH/{EDGE_NODE_ID}"
    DDEATHTOPIC = f"spBv1.0/{GROUP_ID}/NDEATH/{EDGE_NODE_ID}"
    # MQTT Client Setup
    mqtt_client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, EDGE_NODE_ID)

    # Setting the last will, if connection drops
    mqtt_client.will_set(
        topic=DDEATHTOPIC,
        payload=json.dumps({"status": {"connected": "False"}}),
        qos=0
    )

    try:
        logger.info("Trying to connet to mqtt broker")
        mqtt_client.connect(BROKERIP, BROKERPORT)

        mqtt_client.loop_start()

    except TimeoutError:
        logger.error("Error: Connection timed out. Check network connectivity.")
        sys.exit(1)
    except Exception as e:
        logger.error(f"Unexpected error: {str(e)}")
        sys.exit(1)

    logger.info("Connection to the broker was successful!")
    # Publish DBIRTH
    mqtt_client.publish(
        DBIRTHTOPIC,
        payload=json.dumps({"timestamp": time.time(),
                            "status": {"connected": "True"}}),
        qos=0
    )

    return mqtt_client

# Connecting to the internal message bus
def valkey_connection():
    valkey_client = valkey.Valkey(host="localhost", port=6379)

    # Test connection
    if not valkey_client.ping():
        logger.error("No connection to the internal message bus")
        sys.exit(1)

    logger.info("Connection to the internal message bus was successful")
    return  valkey_client

# Connecting to the internal message bus
def receive_and_publish_messages(valkey_client, mqtt_client):

    pubsub = valkey_client.pubsub()

    # Subscribes to all topics
    # Change when it might be noisy
    pubsub.psubscribe("*")

    for message in pubsub.listen():
        if message['type'] == 'pmessage':
            mqtt_client.publish(message['channel'].decode('utf-8'), message['data'].decode('utf-8'))
    return

if __name__ == "__main__":
    node_identity = get_node_identity()
    valkey_client = valkey_connection()
    mqtt_client = mqtt_connection(node_identity)
    receive_and_publish_messages(valkey_client, mqtt_client)