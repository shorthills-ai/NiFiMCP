# Monitoring Setup Scripts

This repository contains shell scripts to automate the setup and cleanup of a monitoring environment.

## Overview

The scripts are designed to:

*   **`setup.sh`**: Install and configure monitoring components (Prometheus, Grafana, Node Exporter).
*   **`cleanup.sh`**: Remove the installed monitoring components and cleanup the environment.

The configuration for the installation is managed through the `setup.env` file.

## Prerequisites

Before running the scripts, ensure you have the following dependencies installed:

*   `curl`
*   `tar`
*   `openssl`

You can install them using the following command on Debian/Ubuntu-based systems:

```bash
sudo apt-get update
sudo apt-get install -y curl tar openssl
```

## Configuration

The `setup.env` file is used to configure the installation. The following variables can be set:

| Variable | Description |
|---|---|
| `IP_ADDRESS` | The IP address of the server where the scripts are being run. |
| `REMOTE_NODE_IPS` | A comma-separated list of IP addresses of remote nodes to be monitored. |
| `INSTALL_PROMETHEUS` | Set to `true` to install Prometheus. |
| `PROMETHEUS_VERSION` | The version of Prometheus to install. |
| `INSTALL_NODE_EXPORTER` | Set to `true` to install Node Exporter. |
| `NODE_EXPORTER_VERSION` | The version of Node Exporter to install. |
| `INSTALL_GRAFANA` | Set to `true` to install Grafana. |

## Usage

### 1. Configure the environment

Edit the `setup.env` file to set the IP address, remote node IPs, and which components to install.

### 2. Run the setup script

Execute the `setup.sh` script to install and configure the monitoring components:

```bash
./setup.sh
```

### 3. Cleanup the environment

To remove the installed components and cleanup the environment, run the `cleanup.sh` script:

```bash
./cleanup.sh
```

## Modifying the Scripts

The scripts can be modified to add or remove components, or to change the installation logic.

*   **`setup.sh`**: To add a new component, add a new function to this script to handle the installation of the component. You will also need to add a corresponding `INSTALL_` variable to the `setup.env` file.
*   **`cleanup.sh`**: To add cleanup logic for a new component, add the necessary `rm` or other cleanup commands to this script.

## Logging

The scripts generate log files in the `logs` directory. The log files are named with a timestamp, for example: `monitoring_install_YYYYMMDD_HHMMSS.log`.