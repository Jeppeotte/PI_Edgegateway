import valkey
import logging
import time
import sys
import json

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)]
)

logger = logging.getLogger(__name__)

# Connecting to the internal message bus
def valkey_connection(retries=3, delay=5):
    logger.info("Connecting the to internal messagebus")
    attempt = 0
    while attempt < retries:
        try:
            valkey_client = valkey.Valkey(host="host.docker.internal", port=6379)

            # Test connection
            if valkey_client.ping():
                logger.info("Connection to the internal message bus was successful")
                return valkey_client
            else:
                logger.error("Ping failed, no connection to the internal message bus")

        except Exception as e:
            logger.error(f"Connection attempt {attempt + 1} failed with error: {e}")

        attempt += 1
        if attempt < retries:
            logger.info(f"Retrying in {delay} seconds... ({attempt}/{retries}) attempts")
            time.sleep(delay)
        else:
            logger.error("All retry attempts failed. Shutting down")
            sys.exit(1)

if __name__ == "__main__":
    valkey_client = valkey_connection()

    state_topic = "spBv1.0/group_1/STATE/lenovo_node/TESTPLC"

    while True:
        logger.info("Publishing data_trigger: True")
        valkey_client.publish(state_topic, json.dumps({"time": time.time(),
                                                            "data_trigger": "True"
                                                            }))
        time.sleep(5)
        logger.info("Publishing data_trigger: False")
        valkey_client.publish(state_topic, json.dumps({"time": time.time(),
                                                       "data_trigger": "False"
                                                       }))
        time.sleep(10)