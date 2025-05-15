import time
import threading
import snap7
import math
from models.devicemodels import S7CommDeviceServiceConfig
import yaml
from pathlib import Path
import valkey
import json
import argparse
import sys
import logging
import signal

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)]
)

logger = logging.getLogger(__name__)

#Setting the path for the config file
parser = argparse.ArgumentParser()
parser.add_argument(
    "--device_service_config_path",
    help="Parse the path for the device service config file from metadata"
)
args = parser.parse_args()

if not args.device_service_config_path:
    logging.error("Error: You must provide --device_service_config_path (path to the device service config file from metadata.yaml).")
    sys.exit(1)

#Directory for docker container
mounted_dir = Path("/mounted_dir")

# Get configuration from config file
def get_device_config(device_config_path):
    config_path = mounted_dir.joinpath(device_config_path)

    try:
        with open(config_path, 'r') as f:
            device_config = yaml.safe_load(f)

    except FileNotFoundError:
        logging.error(f"Error: The configuration file '{config_path}' does not exist.")
        sys.exit(1)

    except yaml.YAMLError as e:
        logging.error(f"Error reading the YAML file: {e}")
        sys.exit(1)

    config = S7CommDeviceServiceConfig.model_validate(device_config)

    # Return all data from configfile
    return config

# Connecting to the internal message bus
def valkey_connection(retries=3, delay=5):
    logging.info("Connecting the to internal messagebus")
    attempt = 0
    while attempt < retries:
        try:
            valkey_client = valkey.Valkey(host="localhost", port=6379)

            # Test connection
            if valkey_client.ping():
                logging.info("Connection to the internal message bus was successful")
                return valkey_client
            else:
                logging.error("Ping failed, no connection to the internal message bus")

        except Exception as e:
            logging.error(f"Connection attempt {attempt + 1} failed with error: {e}")

        attempt += 1
        if attempt < retries:
            logging.info(f"Retrying in {delay} seconds... ({attempt}/{retries}) attempts")
            time.sleep(delay)
        else:
            logging.error("All retry attempts failed. Shutting down")
            sys.exit(1)

def connect_to_plc(device_config, retries=3, delay=5):
    logging.info("Connecting to the PLC")
    attempt = 0
    while attempt < retries:
        try:
            client = snap7.client.Client()
            client.connect(
                device_config.device.ip,
                device_config.device.rack,
                device_config.device.slot
            )

            if client.get_connected():
                logging.info(f"Connected to PLC at {device_config.device.ip}")
                return client
            else:
                logging.error(f"Attempt {attempt + 1}: Connected but PLC is not responding")

        except Exception as e:
            logging.error(f"Attempt {attempt + 1}: Failed to connect to PLC at {device_config.device.ip} with error: {e}")

        attempt += 1
        if attempt < retries:
            logging.info(f"Retrying in {delay} seconds... ({attempt}/{retries}) attempts")
            time.sleep(delay)
        else:
            logging.error("All retry attempts failed. Exiting.")
            sys.exit(1)

class PLCReader:
    def __init__(self, device_config, client, valkey_client):
        self.device_config = device_config
        # Get the configuration of the data trigger
        self.data_trigger_config = next((trigger for trigger in device_config.triggers if trigger.trigger_type == "data_trigger"),
                                        None)
        # Get the configuration of the process trigger
        self.process_trigger_config = next((trigger for trigger in device_config.triggers if trigger.trigger_type == "process_trigger"),
                                        None)
        self.data_block = self.device_config.data_block
        self.polling_intervals = self.device_config.polling
        self.client = client
        self.valkey_client = valkey_client
        self.client_lock = threading.Lock() #Lock the client so that only 1 thread can access it at the time
        self.process_event = threading.Event()
        self.trigger_event = threading.Event()
        self.stop_event = threading.Event()
        self.state_topic = f"spBv1.0/{device_config.device.group_id}/STATE/{device_config.device.node_id}/{device_config.device.device_id}"
        self.data_topic = f"spBv1.0/{device_config.device.group_id}/DDATA/{device_config.device.node_id}/{device_config.device.device_id}"
        signal.signal(signal.SIGTERM, self.handle_sigterm)
        logger.info(f"Starting up the S7Comm service for device: {device_config.device.device_id}")

    def monitor_process(self):
        # Determine if the "main" process has begun, so that the script do not spam the PLC with requests when it is idle
        trigger_source = self.process_trigger_config.source
        db_number = trigger_source.get("db_number")
        logger.info(f"Process trigger db_number: {db_number}")
        byte_offset = trigger_source.get("byte_offset")
        logger.info(f"Process trigger byte_offset: {byte_offset}")
        bit_offset = trigger_source.get("bit_offset")
        logger.info(f"Process trigger byte_offset: {bit_offset}")
        trigger_condition = self.process_trigger_config.condition
        logger.info(f"Process trigger condition: {trigger_condition}")
        poll_timer = self.polling_intervals.get("process_trigger")
        previous_value = None

        while not self.stop_event.is_set():
            # Read state of PLC
            with self.client_lock:
                reading = self.client.db_read(db_number, byte_offset, 1)

            trigger_value = snap7.util.get_bool(reading, 0, 0)
            logging.info(f"The state of the process is the following: {trigger_value}")

            # Publish initial value or changed value
            if previous_value is None or trigger_value != previous_value:
                logging.info(f"Sending message to the following topic: {self.state_topic}")
                self.valkey_client.publish(self.state_topic, json.dumps({"time": time.time(),
                                                                    "process_trigger": str(trigger_value)
                                                                   }))
                previous_value = trigger_value
            # print(f"This is the trigger state:{self.trigger_state}")
            if trigger_value != trigger_condition:
                trigger_state = trigger_value
                if not trigger_state:
                    self.process_event.clear()  # Clear event when trigger is False
                else:
                    self.process_event.set()  # Set event when trigger is True
            time.sleep(poll_timer)

    def monitor_trigger(self):
        db_number = self.data_trigger_config.db_number
        byte_offset = self.data_trigger_config.byte_offset
        trigger_data_type = "Bool"
        trigger_condition = self.data_trigger_config.condition
        trigger_state = trigger_condition
        poll_timer = self.polling_intervals.get("data_trigger")
        previous_value = None

        while not self.stop_event.is_set():
            self.process_event.wait()
            # Read trigger data from PLC
            with self.client_lock:
                reading = self.client.db_read(db_number, byte_offset, 1)

            sample_time = time.time()
            trigger_value = snap7.util.get_bool(reading, 0, 0)
            logging.info(f"Sampling trigger, with the following reading: {trigger_value}")

            # Publish initial value or changed value
            if previous_value is None or trigger_value != previous_value:
                self.valkey_client.publish(self.state_topic, json.dumps({"time": time.time(),
                                                                         "data_trigger": trigger_value
                                                                         }))
                previous_value = trigger_value
            #print(f"This is the trigger state:{self.trigger_state}")
            if trigger_value != trigger_condition:
                trigger_state = trigger_value
                if not trigger_state:
                    self.trigger_event.clear()  # Clear event when trigger is False
                else:
                    self.trigger_event.set()  # Set event when trigger is True
            time.sleep(poll_timer)

    def sample_main_data(self):
        data_db_number = self.data_block.db_number
        data_byte_offset = self.data_block.byte_offset
        data_read_size = self.data_block.read_size
        previous_values = None
        variable_byte_offsets = [variable.byte_offset for variable in self.data_block.variables]
        min_offset = min(variable_byte_offsets)
        adjusted_variable_byte_offsets = [x - min_offset for x in variable_byte_offsets]
        variable_units = [variable.units for variable in self.data_block.variables]
        variable_names = [variable.name for variable in self.data_block.variables]
        variable_bit_offsets = [variable.bit_offset for variable in self.data_block.variables]
        indexes = range(len(variable_names))
        variable_data_types = [variable.data_type for variable in self.data_block.variables]
        poll_timer = self.polling_intervals.get("data_interval")

        while not self.stop_event.is_set():
            self.trigger_event.wait()  # Block until trigger is True

            # Read main data from PLC
            with self.client_lock:
                reading = self.client.db_read(data_db_number, data_byte_offset, data_read_size)
            sample_time = time.time()

            # Value extraction
            current_values = [snap7.util.get_real(reading, offset)
                              for offset in adjusted_variable_byte_offsets]

            # Value comparison
            if previous_values is None:
                changed_indexes = indexes
            else:
                # Find changed indexes via numpy (fastest for large datasets)
                changed_indexes = [i for i, (prev, curr) in enumerate(zip(previous_values, current_values))
                                   if not math.isclose(prev, curr, rel_tol=1e-6)]

            # Build metric structure for changed values
            changed_metrics = [{
                "name": variable_names[i],
                "value": current_values[i],
                "timestamp": sample_time,
                "datatype": variable_data_types[i],
                "units": variable_units[i]
            } for i in changed_indexes]
            # Publish if changes exist
            if changed_metrics:
                self.valkey_client.publish(self.data_topic, json.dumps({"time": time.time(),
                                                                   "metrics": changed_metrics}))

            # Update previous values
            previous_values = current_values
            time.sleep(poll_timer)

    # Handling the shutdown of the container
    def handle_sigterm(self, signum, frame):
        logger.info("Received SIGTERM, shutting down gracefully...")
        # Stop the while loops
        self.stop_event.set()
        # Stop the process
        self.process_event.clear()
        # Stop the data sampling
        self.trigger_event.clear()
        # give threads a moment to stop
        time.sleep(4)
        sys.exit(0)


    def start_sampling(self):

        if self.process_trigger_config:
            # Start thread for process monitoring
            process_thread = threading.Thread(target=self.monitor_process)
            process_thread.daemon = True
            process_thread.start()
        else:
            logger.info("Process trigger is not configured and will not be performed")

        if self.data_trigger_config:
            # Start thread for trigger monitoring
            trigger_thread = threading.Thread(target=self.monitor_trigger)
            trigger_thread.daemon = True
            trigger_thread.start()

        else:
            logger.info("Data trigger is not configured and will not be performed")

        if self.data_block:
            # Start thread for main data sampling
            data_thread = threading.Thread(target=self.sample_main_data)
            data_thread.daemon = True
            data_thread.start()

        else:
            logger.info("Data blocks are not configured")

        # Keep the main program running
        while not self.stop_event.is_set():
            time.sleep(1)


# Get configuration from config file
device_config_path = args.device_service_config_path
# Setup
# First ensure that the connection to the internal message bus can be established
valkey_client = valkey_connection()
# Second get the configuration of the device service
device_config = get_device_config(device_config_path)
# Third connect to the PLC
client = connect_to_plc(device_config)

# Forth Initialize PLCReader and start sampling
plc_reader = PLCReader(device_config, client, valkey_client)
plc_reader.start_sampling()
