import paho.mqtt.client as mqtt
import valkey
import json
import time
import yaml
import argparse
import logging
import sys

# Configure logging to output INFO and above to stdout
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)]
)

logger = logging.getLogger(__name__)

#Setting the path for the config file
parser = argparse.ArgumentParser()
parser.add_argument("--mqtt_configfile_path", required=True)
parser.add_argument("--metadata_path", required=True)
parser.add_argument("--valkey_host", required=True)

args = parser.parse_args()

def get_node_identity(metadata_path):
    # Get the identity of the node
    with open(metadata_path, 'r') as f:
        metadata_config = yaml.safe_load(f)

    return metadata_config["identity"]

def mqtt_connection(identity,mqtt_configfile_path):
    try:
        with open(mqtt_configfile_path, 'r') as f:
            mqtt_config = yaml.safe_load(f)
    except FileNotFoundError:
        logger.error(f"Error: The configuration file '{mqtt_configfile_path}' does not exist.")
        exit()

    except yaml.YAMLError as e:
        logger.error(f"Error reading the YAML file: {e}")
        exit()

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
        payload=json.dumps({"status": "OFFLINE"}),
        qos=0
    )

    try:
        logger.info("Trying to connet to mqtt broker")
        mqtt_client.connect(BROKERIP, BROKERPORT)

        mqtt_client.loop_start()

    except TimeoutError:
        logger.error("Error: Connection timed out. Check network connectivity.")
        exit()
    except Exception as e:
        logger.error(f"Unexpected error: {str(e)}")
        exit()

    logger.info("Connection to the broker was successful!")
    # Publish DBIRTH
    mqtt_client.publish(
        DBIRTHTOPIC,
        payload=json.dumps({"timestamp": int(time.time()),
                            "status": "ONLINE"}),
        qos=0
    )

    return mqtt_client

# Connecting to the internal message bus
def valkey_connection():
    valkey_client = valkey.Valkey(host=args.valkey_host, port=6379)

    # Test connection
    if not valkey_client.ping():
        logger.error("No connection to the internal message bus")
        exit()

    logger.info("Connection to the internal message bus was successful")
    return  valkey_client

# Connecting to the internal message bus
def receive_and_publish_messages(valkey_client, mqtt_client):

    pubsub = valkey_client.pubsub()

    # Subscribes to all device data from the different device_ids which the node might have
    pubsub.subscribe(["spBv1.0/+/DDATA/#",
                      "spBv1.0/+/STATE/#",
                      "spBv1.0/+/DBIRTH/#",
                      "spBv1.0/+/DDEATH/#",
                      "spBv1.0/+/AUDIODATA/#",
                      ])

    for message in pubsub.listen():
        if message['type'] == 'message':
            mqtt_client.publish(message['channel'].decode('utf-8'), message['data'].decode('utf-8'))
    return

if __name__ == "__main__":
    node_identity = get_node_identity(args.metadata_path)
    valkey_client = valkey_connection()
    mqtt_client = mqtt_connection(node_identity,args.mqtt_configfile_path)
    receive_and_publish_messages(valkey_client, mqtt_client)