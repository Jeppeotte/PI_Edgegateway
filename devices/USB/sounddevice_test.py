import sounddevice as sd

def list_microphones():
    print("Available input (microphone) devices:\n")

    devices = sd.query_devices()
    for i, device in enumerate(devices):
        if device['max_input_channels'] > 0:
            print(f"Device #{i}: {device['name']}")
            print(f"  Max input channels : {device['max_input_channels']}")
            print(f"  Default samplerate : {device['default_samplerate']} Hz")
            print(f"  Host API           : {sd.query_hostapis()[device['hostapi']]['name']}")
            print("")

if __name__ == "__main__":
    sd._terminate()
    sd._initialize()

    list_microphones()
