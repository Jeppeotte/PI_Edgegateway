# Edge Gateway Software – Master's Thesis, Aalborg University

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
