# Edge Gateway Software

This repository was created as part of a Master’s Thesis project at Aalborg University. Its purpose is to simplify data acquisition at the edge by installing this software on an edge gateway device.

> **Note**: This is **Repository 1 of 2**. This repository contains the **software** that should be installed on an edge gateway to sample data from industrial processes—either through PLCs or directly connected sensors.

Currently, the software supports:
- **Siemens PLCs**
- **USB microphones**

For instructions on how to use and connect different services/devices to this system, refer to the second GitHub repository.

---

## 🧰 Prerequisites

This setup guide is written for a **Raspberry Pi 5 (8 GB RAM)** running **Raspberry Pi OS 64-bit**, released on **2025-05-13**.  
However, the software should work on any Linux system with either **amd64** or **arm64** architecture and sufficient resources.

> ⚠️ No minimum system resource benchmarks have been conducted yet.

---

## ⚙️ Installation Guide

### 1. Install Docker

Run the following command to install Docker:

```bash
curl -sSL https://get.docker.com | sh
```

Add your user to the Docker group:

```bash
sudo usermod -aG docker $USER
```

Restart your device after adding the user to the Docker group.

### 2. Prepare the Project Folder

To prepare the environment for running the software, follow these steps:

1. **Create a folder** to store all the project files and navigate into it:

    ```bash
    mkdir edge-gateway-software
    cd edge-gateway-software
    ```

2. **Create a new file** named `docker-compose.yaml` inside this folder:

    ```bash
    touch docker-compose.yaml
    ```

3. **Copy the contents** of the Docker Compose configuration from this repository into the `docker-compose.yaml` file.

4. **Edit the file** and update the `volumes` and `environment` sections to match your setup. Here’s an example:

    ```yaml
    services:
      configurator:
        volumes:
          - /absolute/path/to/this/folder:/mounted_dir:rw
          - /var/run/docker.sock:/var/run/docker.sock:rw
        environment:
          HOST_PLATFORM: linux   # Change to linux, windows, or mac
          HOST_ARCH: arm64       # Change to amd64 or arm64
    ```

    Replace:
    - `/absolute/path/to/this/folder` with the absolute path to the directory where `docker-compose.yaml` is stored.
    - `your_service_name` with the actual service name defined in your configuration.
    - `HOST_PLATFORM` and `HOST_ARCH` according to your system.

Once this is complete, you're ready to launch the software.

### 3. Launch the Software

After setting up the `docker-compose.yaml` file, you can now launch the software using Docker Compose:

1. **Navigate to the folder** where your `docker-compose.yaml` file is located:

    ```bash
    cd /path/to/your/edge-gateway-software
    ```

2. **Start the containers** in detached mode:

    ```bash
    sudo docker compose up -d
    ```

3. **Verify that the containers are running** by listing the active Docker containers:

    ```bash
    sudo docker ps
    ```

If everything is set up correctly, you should see the containers for your edge gateway software running.


### 4. Set a Static IP Address for Ethernet Communication

If you're connecting your edge gateway directly to a PLC or sensor via Ethernet, it's important to assign a **static IP address** to ensure reliable communication.

#### Temporary Setup (for quick testing)

You can manually assign an IP address to the Ethernet interface using the following command:

```bash
sudo ifconfig eth0 172.20.1.153 netmask 255.255.255.0
````

> **Note:** This configuration is temporary and will reset after a reboot.

---

#### Persistent Setup (recommended)

To make the static IP address persist across reboots, configure the `dhcpcd` service as follows:

```bash
# Open the dhcpcd.conf file in a text editor
sudo nano /etc/dhcpcd.conf
```

Add the following lines at the end of the file:

```conf
interface eth0
static ip_address=172.20.1.153/24
```

* Replace `172.20.1.153` with the desired static IP address.
* `/24` means the subnet mask is `255.255.255.0`.

Save and exit the editor (`Ctrl + X`, then `Y`, then `Enter`).

Reboot your device for changes to take effect:

```bash
sudo reboot
```

---

#### Verify the Static IP Address

After reboot, check the IP address assigned to the Ethernet interface:

```bash
ip a show eth0
```

You should see the static IP address you configured.

---

#### Understanding IP and Subnet Compatibility

To communicate properly over Ethernet:

* Devices must be on the **same subnet** (matching subnet mask).
* Each device must have a **unique IP address** within that subnet.

For example, with subnet mask `255.255.255.0` (`/24`):

| Device       | IP Address   | Can communicate? |
| ------------ | ------------ | ---------------- |
| Edge Gateway | 172.20.1.153 | ✅ Yes            |
| PLC          | 172.20.1.10  | ✅ Yes            |
| Other device | 192.168.0.5  | ❌ No             |

Make sure the first three segments (e.g., `172.20.1`) of the IP address match for all devices in the network.


