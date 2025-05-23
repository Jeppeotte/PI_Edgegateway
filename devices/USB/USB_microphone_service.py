import time
import threading
from models.devicemodels import USBMicrophoneDevice
import yaml
from pathlib import Path
import valkey
import json
import argparse
import sys
import sounddevice as sd
import numpy as np
import io
import httpx
import wavio
from datetime import datetime
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
parser.add_argument("--device_service_config_path",
                    help="Parse the path for the device service config file from metadata")
parser.add_argument("--backend_ip",
                    help="Parse the ip of the device where the file saver service is running")
args = parser.parse_args()

if not args.device_service_config_path:
    print("Error: You must provide --device_service_config_path (path to the device service config file from metadata.yaml).")
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
        logger.error(f"Error: The configuration file '{config_path}' does not exist.")
        sys.exit(1)

    except yaml.YAMLError as e:
        logger.error(f"Error reading the YAML file: {e}")
        sys.exit(1)

    config = USBMicrophoneDevice.model_validate(device_config)

    # Return all data from configfile
    return config

# Connecting to the internal message bus
def valkey_connection(retries=3, delay=5):
    logger.info("Connecting the to internal messagebus")
    attempt = 0
    while attempt < retries:
        try:
            valkey_client = valkey.Valkey(host="localhost", port=6379)

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


class PLCReader:
    def __init__(self, device_config, valkey_client):
        self.device_config = device_config
        # Get the configuration of the data trigger
        self.data_trigger_config = next((trigger for trigger in device_config.triggers if trigger.trigger_type == "data_trigger"),
                                        None)
        self.USB_device = device_config.USB_device
        self.valkey_client = valkey_client
        self.trigger_event = threading.Event()
        self.stop_event = threading.Event()
        self.DDEATH_topic = f"spBv1.0/{device_config.device.group_id}/DDEATH/{device_config.device.node_id}/{device_config.device.device_id}"
        self.DBIRTH_topic = f"spBv1.0/{device_config.device.group_id}/DBIRTH/{device_config.device.node_id}/{device_config.device.device_id}"
        self.state_topic = f"spBv1.0/{device_config.device.group_id}/STATE/{device_config.device.node_id}/{device_config.device.device_id}"
        self.data_topic = f"spBv1.0/{device_config.device.group_id}/AUDIODATA/{device_config.device.node_id}/{device_config.device.device_id}"
        signal.signal(signal.SIGTERM, self.handle_sigterm)
        # Publish that the device is turning on
        self.valkey_client.publish(self.DBIRTH_topic, json.dumps({"time": time.time(),
                                                                  "status": {"connected": "True"}
                                                                  }))
        logger.info(f"Starting up the USB microphone service for device: {device_config.device.device_id}")

    def monitor_trigger(self):
        trigger_topic = self.data_trigger_config.topic
        trigger_source = self.data_trigger_config.source.get("topic")
        logger.info(f"Source of the trigger: {trigger_source}")
        trigger_condition = self.data_trigger_config.condition
        logger.info(f"Trigger condition: {trigger_condition}")
        previous_value = None
        # Initialise the subscription to a topic
        pubsub = valkey_client.pubsub()
        # Subscribes to source where trigger condition will be posted
        logger.info(f"This is the source of the trigger: {trigger_source}")
        pubsub.subscribe(trigger_source)
        while not self.stop_event.is_set():
            logger.info("Waiting for the trigger")
            for message in pubsub.listen():
                if message['type'] == 'message':
                    message_data = json.loads(message['data'].decode('utf-8'))
                    #As there will come multiple messages on this channel we need to ensure that the message
                    # Is a data trigger message, and will return none if it isnt
                    trigger_value = message_data.get("status", {}).get("data_trigger", None)
                    if trigger_value:
                        logger.info(f"Received sampling trigger")

                        # Publish initial value or changed value
                        if previous_value is None or trigger_value != previous_value:
                            logger.info(f"Data trigger state: {trigger_value}")
                            self.valkey_client.publish(self.state_topic, json.dumps({"time": time.time(),
                                                                                     "status": {
                                                                                         "data_trigger": str(trigger_value)}
                                                                                     }))
                            previous_value = trigger_value
                        if trigger_value == trigger_condition:
                            logger.info("Trigger event set")
                            self.trigger_event.set() # Set event if the trigger_value is = condition
                        else:
                            logger.info("Trigger event cleared")
                            self.trigger_event.clear() # Clear event when trigger_value is != condition

    def sample_microphone_data(self):
        name = self.USB_device.name
        data_type = self.USB_device.data_type
        units = self.USB_device.units
        samplerate = self.USB_device.samplerate
        channel = self.USB_device.channel
        device_id = self.device_config.device.device_id

        logger.info(f"Will sample the microphone with a samplerate of: {samplerate} Hz")

        # Create a directory for saving the audio files locally if the connection drops
        audio_datapath = mounted_dir.joinpath(f"data/audio_data/{device_id}")

        if not audio_datapath.exists():
            audio_datapath.mkdir(parents=True,exist_ok=True)
            logger.info("Created a path for the audio data if the connection drops")

        def audio_callback(indata, frames, time_info, status):
            if status:
                logger.info(status)
            # Append the audio data to the buffer
            audio_buffer.append(indata.copy())

        while not self.stop_event.is_set():
            self.trigger_event.wait()  # Block until trigger is True

            audio_buffer = []
            try:
                logger.info("Starting audio sampling")
                sample_time = time.time()
                with sd.InputStream(samplerate=samplerate, channels=channel, callback=audio_callback, dtype="int16"):
                    while self.trigger_event.is_set():
                        time.sleep(0.1)  # Keep the thread alive while audio is streaming
                logger.info("Audio sampling stopped")

            except sd.PortAudioError as e:
                if "Invalid sample rate" in str(e):
                    logger.error(f"Invalid sample rate: {samplerate}")
                    #Exit thread
                    self.stop_event.set()
                    sys.exit(1)

                else:
                    logger.error("PortAudio error during input stream setup.")
                    devices = sd.query_devices()
                    if not devices:
                        logger.info("No audio devices ws found")
                    else:
                        logger.info(f"The following audio devices are available: {devices}")
                    self.stop_event.set()
                    sys.exit(1)

            except Exception as e:
                logger.error("Unexpected error during audio sampling")
                self.stop_event.set()
                sys.exit(1)

            if audio_buffer:
                audio_buffer = np.concatenate(audio_buffer)
                # save the file in memory buffer
                buffer = io.BytesIO()
                wavio.write(buffer, audio_buffer, samplerate)
                buffer.seek(0)
                #Convert the sample time to date time
                sample_time_dt = datetime.fromtimestamp(sample_time)
                formatted_dt = sample_time_dt.strftime("%Y_%m_%d_%H_%M_%S")
                file_name = f"{formatted_dt}_{device_id}"

                file = {"file": (file_name, buffer, "audio/wav")}

                device = {"device_id": device_id}
                try:
                    with httpx.Client(timeout=2) as client:
                        response = client.post(f"http://{args.backend_ip}:8000/api/data_saver/upload_audio",
                                               files=file,
                                               data=device)

                    if response.status_code == 200:
                        logger.info("Successfully saved the audio file in the backend")

                    else:
                        raise httpx.HTTPStatusError("Unexpected status code", request=response.request, response=response)

                except (httpx.RequestError, httpx.HTTPStatusError) as e:
                    logger.error("Could not save the audio file in the backend, saving locally instead. Check connection.")

                    audio_file = audio_datapath.joinpath(file_name)
                    wavio.write(str(audio_file), audio_buffer, samplerate, sampwidth=2)
                    if audio_file.exists():
                        logger.info("Saved the audio file locally")
                    else:
                        logger.error("Something went wrong when saving the audio file locally")

                # Build metric structure for changed values
                audio_metric = [{
                    "name": name,
                    "value": file_name,
                    "timestamp": sample_time,
                    "datatype": data_type,
                    "units": units
                }]

                # Publish if the information about the data file to the database
                self.valkey_client.publish(self.data_topic, json.dumps({"time": time.time(),
                                                                   "metrics": audio_metric}))

    # Handling the shutdown of the container
    def handle_sigterm(self, signum, frame):
        logger.info("Received SIGTERM, shutting down gracefully...")
        # Stops the while loops of each function
        self.stop_event.set()
        # Stops the audio sampling
        self.trigger_event.clear()
        # give threads a moment to stop
        time.sleep(4)
        sys.exit(0)

    def start_sampling(self):

        # Start thread for trigger monitoring
        trigger_thread = threading.Thread(target=self.monitor_trigger)
        trigger_thread.daemon = True
        trigger_thread.start()

        # Start thread for main data sampling
        data_thread = threading.Thread(target=self.sample_microphone_data)
        data_thread.daemon = True
        data_thread.start()

        # Keep the main program running
        while not self.stop_event.is_set():
            time.sleep(1)

        #Publishing that the service is shutting down
        self.valkey_client.publish(self.DDEATH_topic, json.dumps({"time": time.time(),
                                                                  "status": {"connected": "False"}
                                                                  }))
        logger.info("Shutting down")
        sys.exit(1)



# Get configuration from config file
device_config_path = args.device_service_config_path
# Setup
# First ensure that the connection to the internal message bus can be established
valkey_client = valkey_connection()
# Second get the configuration of the device service
device_config = get_device_config(args.device_service_config_path)

# Forth Initialize PLCReader and start sampling
plc_reader = PLCReader(device_config, valkey_client)
plc_reader.start_sampling()
