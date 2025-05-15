import sounddevice as sd
import threading
import numpy as np
import time
import httpx

# Create an event to control the process
process_event = threading.Event()
process_event.set()  # Start as running

# Audio parameters
samplerate = 44100
channels = 1

# List to store chunks of audio data
audio_buffer = []

def audio_callback(indata, frames, time_info, status):
    if status:
        print(status)
    # Append the audio data to the buffer
    audio_buffer.append(indata.copy())

def monitor_process():
    """Simulate monitoring a process that stops after 2 seconds."""
    time.sleep(5)
    process_event.clear()
    print("Process stopped.")

def sample_audio_data():
    """Sample audio and collect it until the process stops."""
    print("Starting audio sampling...")
    with sd.InputStream(samplerate=samplerate, channels=channels, callback=audio_callback):
        while process_event.is_set():
            time.sleep(0.1)  # Keep the thread alive while audio is streaming
    print("Audio sampling stopped.")

# Start the monitor and audio threads
monitor_thread = threading.Thread(target=monitor_process)
audio_thread = threading.Thread(target=sample_audio_data)

monitor_thread.start()
audio_thread.start()

monitor_thread.join()
audio_thread.join()

# After stopping, combine all audio chunks
if audio_buffer:
    full_audio = np.concatenate(audio_buffer, axis=0)
    print(f"Collected {len(full_audio)} total samples.")

    # Flatten if multi-channel (even though channels=1, good to generalize)
    if full_audio.ndim > 1:
        full_audio = full_audio[:, 0]

    # Create a time axis for the plot
    time_axis = np.linspace(0, len(full_audio) / samplerate, num=len(full_audio))

    # Plot the waveform
    plt.figure(figsize=(12, 4))
    plt.plot(time_axis, full_audio)
    plt.title("Audio Waveform")
    plt.xlabel("Time [seconds]")
    plt.ylabel("Amplitude")
    plt.show()

else:
    print("No audio data was collected.")
