#!/bin/bash

# Uses environment variables for configuration and maintains detailed logs
set -e

# Define colors for output
GREEN='\033[32m'
RED='\e[31m'
RESET='\033[0m'

# Configuration
ENV_FILE="setup.env"
LOG_FILE="monitoring_install_$(date +%Y%m%d_%H%M%S).log"

# Function to log messages
log_message() {
    local level="$1"
    local message="$2"
    local timestamp=$(date '+%Y-%m-%d %H:%M:%S')
    echo "[$timestamp] [$level] $message" >> "$LOG_FILE"

    case "$level" in
        "INFO")
            echo -e "${GREEN}[INFO] $message${RESET}"
            ;;
        "ERROR")
            echo -e "${RED}[ERROR] $message${RESET}" >&2
            ;;
        "WARNING")
            echo -e "${YELLOW}[WARNING] $message${RESET}"
            ;;
        *)
            echo "[$level] $message"
            ;;
    esac
}

# Function to load environment variables
load_env() {
    if [[ ! -f "$ENV_FILE" ]]; then
        log_message "ERROR" "Environment file not found: $ENV_FILE"
        log_message "ERROR" "Please create a .env file with required variables. See README.md for details."
        exit 1
    fi

    log_message "INFO" "Loading environment variables from $ENV_FILE"
    set -a  # automatically export all variables
    source "$ENV_FILE"
    set +a

    # Validate required variables
    if [[ -z "$IP_ADDRESS" ]]; then
        log_message "ERROR" "IP_ADDRESS is required in .env file"
        exit 1
    fi

    log_message "INFO" "Environment variables loaded successfully"
    log_message "INFO" "Target IP Address: $IP_ADDRESS"
    log_message "INFO" "Install Prometheus: ${INSTALL_PROMETHEUS:-false}"
    log_message "INFO" "Install Grafana: ${INSTALL_GRAFANA:-false}"
    log_message "INFO" "Install Node Exporter: ${INSTALL_NODE_EXPORTER:-false}"
}

load_env

# Set default versions if not provided in env file
echo "${PROMETHEUS_VERSION}"
PROMETHEUS_VERSION="${PROMETHEUS_VERSION:-2.54.1}"
NODE_EXPORTER_VERSION="${NODE_EXPORTER_VERSION:-1.8.2}"


# Function to remove log files older than 2 days
cleanup_old_logs() {
    log_message "INFO" "Starting log cleanup"
    find . -maxdepth 1 -type f -name "monitoring_cleanup_*.log" -mmin +1 -exec rm -f {} \;
    find . -maxdepth 1 -type f -name "monitoring_install_*.log" -mmin +1 -exec rm -f {} \;
    log_message "INFO" "Log cleanup completed"
}

# Function to check if a service should be installed
should_install() {
    local service="$1"
    local install_var="INSTALL_${service^^}"
    local install_value="${!install_var}"
    [[ "${install_value,,}" == "true" || "${install_value,,}" == "yes" || "${install_value,,}" == "1" ]]
}

# Function to clean up existing installations
cleanup_existing() {
    log_message "INFO" "Cleaning up existing installations..."

    # Stop and disable services if they exist
    for service in prometheus node_exporter grafana-server; do
        if systemctl is-active --quiet "$service" 2>/dev/null; then
            log_message "INFO" "Stopping $service"
            sudo systemctl stop "$service" 2>/dev/null || true
        fi
        if systemctl is-enabled --quiet "$service" 2>/dev/null; then
            log_message "INFO" "Disabling $service"
            sudo systemctl disable "$service" 2>/dev/null || true
        fi
    done

    # Remove service files
    sudo rm -f /etc/systemd/system/prometheus.service /etc/systemd/system/node_exporter.service

    # Remove binaries and configuration files
    sudo rm -rf /usr/local/bin/prometheus /usr/local/bin/promtool /usr/local/bin/node_exporter
    sudo rm -rf /etc/prometheus /var/lib/prometheus /etc/node_exporter

    # Remove Grafana package and configuration
    sudo apt-get remove --purge -y grafana 2>/dev/null || true
    sudo rm -rf /etc/grafana /var/lib/grafana /etc/apt/sources.list.d/grafana.list /etc/apt/keyrings/grafana.gpg

    # Clean up downloaded files from previous runs
    rm -rf prometheus-*.linux-amd64* node_exporter-*.linux-amd64*

    log_message "INFO" "Cleanup completed"
}

# Function to update system
update_system() {
    log_message "INFO" "Updating system packages..."
    sudo apt install openssl
    if sudo apt update && sudo apt upgrade -y; then
        log_message "INFO" "System update completed successfully"
    else
        log_message "ERROR" "System update failed"
        exit 1
    fi
}

# Function to generate SSL certificate
generate_ssl_certificate() {
    local service="$1"
    local cert_dir="$2"
    local cert_file="$3"
    local key_file="$4"
    log_message "INFO" "Generating SSL certificate for $service"
    sudo mkdir -p "$cert_dir"
    sudo openssl req -x509 -nodes -days 365 -newkey rsa:2048 \
        -keyout "$key_file" \
        -out "$cert_file" \
        -subj "/CN=$IP_ADDRESS" \
        -addext "subjectAltName=IP:$IP_ADDRESS,IP:127.0.0.1"
    if [[ -f "$cert_file" && -f "$key_file" ]]; then
        log_message "INFO" "SSL certificate generated successfully for $service"
    else
        log_message "ERROR" "SSL certificate generation failed for $service"
        exit 1
    fi
}

# Function to check if a service is installed and running
check_service_status() {
    local service="$1"
    local binary="$2"
    local expected_version="$3"
    local port="$4"
    log_message "INFO" "Checking status of $service..."
    # Check if service is installed and running
    if systemctl is-active --quiet "$service"; then
        log_message "INFO" "$service is already running"
        # Verify version if applicable
        if [[ -n "$binary" && -n "$expected_version" ]]; then
            if command -v "$binary" >/dev/null 2>&1 && "$binary" --version 2>&1 | grep -q "$expected_version"; then
                log_message "INFO" "$service version $expected_version is installed and running"
                return 0
            else
                log_message "WARNING" "$service is running but version does not match $expected_version. Proceeding with reinstallation."
                return 1
            fi
        fi
        return 0
    else
        log_message "INFO" "$service is not running or not installed"
        return 1
    fi
}

# Function to install Prometheus
install_prometheus() {
    log_message "INFO" "Installing Prometheus..."
    # Download and extract Prometheus
    wget "https://github.com/prometheus/prometheus/releases/download/v$PROMETHEUS_VERSION/prometheus-$PROMETHEUS_VERSION.linux-amd64.tar.gz"
    tar xvfz prometheus-$PROMETHEUS_VERSION.linux-amd64.tar.gz
    cd prometheus-$PROMETHEUS_VERSION.linux-amd64
    if [[ -f "prometheus" && -f "prometheus.yml" ]]; then
        log_message "INFO" "Prometheus files extracted successfully"
    else
        log_message "ERROR" "Prometheus extraction failed"
        exit 1
    fi
    # Create directories and move files
    sudo mkdir -p /etc/prometheus /var/lib/prometheus /etc/prometheus/ssl
    sudo mv prometheus promtool /usr/local/bin/
    sudo mv consoles console_libraries /etc/prometheus/
    # Verify installation
    if prometheus --version > /dev/null 2>&1; then
        log_message "INFO" "Prometheus binaries installed successfully"
    else
        log_message "ERROR" "Prometheus binary verification failed"
        exit 1
    fi
    # Generate SSL certificate
    generate_ssl_certificate "Prometheus" "/etc/prometheus/ssl" "/etc/prometheus/ssl/prometheus.crt" "/etc/prometheus/ssl/prometheus.key"
    # Create web config
    cat <<EOF | sudo tee /etc/prometheus/web-config.yml
tls_server_config:
  cert_file: /etc/prometheus/ssl/prometheus.crt
  key_file: /etc/prometheus/ssl/prometheus.key
EOF
    # Create Prometheus configuration
    create_prometheus_config
    # Create systemd service
    cat <<EOF | sudo tee /etc/systemd/system/prometheus.service
[Unit]
Description=Prometheus Monitoring
Wants=network-online.target
After=network-online.target

[Service]
User=root
ExecStart=/usr/local/bin/prometheus --config.file=/etc/prometheus/prometheus.yml --web.config.file=/etc/prometheus/web-config.yml --storage.tsdb.path=/var/lib/prometheus --web.listen-address=:9090
ExecReload=/bin/kill -HUP \$MAINPID
Restart=always

[Install]
WantedBy=multi-user.target
EOF
    # Start and enable service
    sudo systemctl daemon-reload
    sudo systemctl start prometheus
    sudo systemctl enable prometheus

    if sudo systemctl is-active --quiet prometheus; then
        log_message "INFO" "Prometheus service started successfully"
    else
        log_message "ERROR" "Prometheus service failed to start"
        exit 1
    fi
    cd ..
}

# Function to create Prometheus configuration
create_prometheus_config() {
    log_message "INFO" "Creating Prometheus configuration..."
    sudo mkdir -p /etc/prometheus
    cat <<EOF | sudo tee /etc/prometheus/prometheus.yml
global:
  scrape_interval: 15s
  evaluation_interval: 15s

scrape_configs:

EOF

    # Add local node exporter if being installed
    if should_install "node_exporter"; then
        cat <<EOF | sudo tee -a /etc/prometheus/prometheus.yml
  - job_name: 'node_exporter_local'
    static_configs:
      - targets: ['127.0.0.1:9100']
    scheme: https
    tls_config:
      insecure_skip_verify: true

EOF
    fi

    # Add remote node exporters
    if [[ -n "$REMOTE_NODE_IPS" ]]; then
        log_message "INFO" "Adding remote node exporters to configuration"
        IFS=',' read -ra REMOTE_IPS <<< "$REMOTE_NODE_IPS"
        for ip in "${REMOTE_IPS[@]}"; do
            ip=$(echo "$ip" | xargs)  # Trim whitespace
            if [[ -n "$ip" ]]; then
                cat <<EOF | sudo tee -a /etc/prometheus/prometheus.yml
  - job_name: 'node_exporter_${ip//./_}'
    static_configs:
      - targets: ['${ip}:9100']
    scheme: https
    tls_config:
      insecure_skip_verify: true

EOF
                log_message "INFO" "Added remote node exporter: $ip"
            fi
        done
    fi

    # Validate configuration
    # if promtool check config /etc/prometheus/prometheus.yml; then
    #     log_message "INFO" "Prometheus configuration validated successfully"
    # else
    #     log_message "ERROR" "Prometheus configuration validation failed"
    #     exit 1
    # fi
}

# Function to install Node Exporter
install_node_exporter() {
    log_message "INFO" "Installing Node Exporter..."
    # Download and extract Node Exporter
    wget https://github.com/prometheus/node_exporter/releases/download/v$NODE_EXPORTER_VERSION/node_exporter-$NODE_EXPORTER_VERSION.linux-amd64.tar.gz
    tar xvfz node_exporter-$NODE_EXPORTER_VERSION.linux-amd64.tar.gz
    cd node_exporter-$NODE_EXPORTER_VERSION.linux-amd64
    if [[ -f "node_exporter" ]]; then
        log_message "INFO" "Node Exporter files extracted successfully"
    else
        log_message "ERROR" "Node Exporter extraction failed"
        exit 1
    fi
    # Create directories and move files
    sudo mkdir -p /etc/node_exporter /etc/node_exporter/ssl
    sudo mv node_exporter /usr/local/bin/
    # Verify installation
    if node_exporter --version ; then
        log_message "INFO" "Node Exporter binary installed successfully"
    else
        log_message "ERROR" "Node Exporter binary verification failed"
        exit 1
    fi
    # Generate SSL certificate
    generate_ssl_certificate "Node Exporter" "/etc/node_exporter/ssl" "/etc/node_exporter/ssl/node_exporter.crt" "/etc/node_exporter/ssl/node_exporter.key"
    # Create web config
    cat <<EOF | sudo tee /etc/node_exporter/web-config.yml
tls_server_config:
  cert_file: /etc/node_exporter/ssl/node_exporter.crt
  key_file: /etc/node_exporter/ssl/node_exporter.key
EOF
    # Create systemd service
    cat <<EOF | sudo tee /etc/systemd/system/node_exporter.service
[Unit]
Description=Prometheus Node Exporter
Wants=network-online.target
After=network-online.target

[Service]
User=root
ExecStart=/usr/local/bin/node_exporter --web.config.file=/etc/node_exporter/web-config.yml
Restart=always

[Install]
WantedBy=multi-user.target
EOF
    # Start and enable service
    sudo systemctl daemon-reload
    sudo systemctl start node_exporter
    sudo systemctl enable node_exporter
    if sudo systemctl is-active --quiet node_exporter; then
        log_message "INFO" "Node Exporter service started successfully"
    else
        log_message "ERROR" "Node Exporter service failed to start"
        exit 1
    fi
    cd ..
}

# Function to install Grafana
install_grafana() {
    log_message "INFO" "Installing Grafana..."
    # Install prerequisites
    sudo apt-get install -y apt-transport-https software-properties-common wget
    # Add Grafana repository
    sudo mkdir -p /etc/apt/keyrings/
    wget -q -O - https://apt.grafana.com/gpg.key | gpg --dearmor | sudo tee /etc/apt/keyrings/grafana.gpg > /dev/null
    echo "deb [signed-by=/etc/apt/keyrings/grafana.gpg] https://apt.grafana.com stable main" | sudo tee -a /etc/apt/sources.list.d/grafana.list
    # Update and install Grafana
    sudo apt-get update
    sudo apt-get install grafana -y
    # Verify installation
    if grafana-server --version | grep -q "Version"; then
        log_message "INFO" "Grafana installed successfully"
    else
        log_message "ERROR" "Grafana installation failed"
        exit 1
    fi
    # Configure Grafana for HTTPS if certificates are available
    # if [[ -n "$GRAFANA_CERT_PATH" && -n "$GRAFANA_KEY_PATH" ]]; then
        log_message "INFO" "Configuring Grafana with SSL"
        sudo mkdir -p /etc/grafana/ssl
        # Generate SSL certificate for Grafana
        generate_ssl_certificate "Grafana" "/etc/grafana/ssl" "/etc/grafana/ssl/grafana.crt" "/etc/grafana/ssl/grafana.key"
        # Fix permissions for SSL certificate files
        sudo chown grafana:grafana /etc/grafana/ssl/grafana.crt /etc/grafana/ssl/grafana.key
        sudo chmod 640 /etc/grafana/ssl/grafana.crt /etc/grafana/ssl/grafana.key
        log_message "INFO" "Set permissions for Grafana SSL certificate files"
        # Update Grafana configuration
        sudo sed -i 's/;protocol = http/protocol = https/' /etc/grafana/grafana.ini
        sudo sed -i "s|;cert_file =|cert_file = /etc/grafana/ssl/grafana.crt|" /etc/grafana/grafana.ini
        sudo sed -i "s|;cert_key =|cert_key = /etc/grafana/ssl/grafana.key|" /etc/grafana/grafana.ini
    # fi
    # Start and enable service
    sudo systemctl start grafana-server
    sudo systemctl enable grafana-server
    if sudo systemctl is-active --quiet grafana-server; then
        log_message "INFO" "Grafana service started successfully"
    else
        log_message "ERROR" "Grafana service failed to start"
        exit 1
    fi
}

# Function to clean up downloaded files
cleanup_downloads() {
    log_message "INFO" "Cleaning up downloaded files..."
    rm -rf prometheus-*.linux-amd64* node_exporter-*.linux-amd64*
    log_message "INFO" "Cleanup completed"
}

# Function to display installation summary
display_summary() {
    log_message "INFO" "Installation Summary:"
    log_message "INFO" "===================="
    if should_install "prometheus"; then
        log_message "INFO" "✓ Prometheus installed - Access at: https://$IP_ADDRESS:9090"
    fi
    if should_install "node_exporter"; then
        log_message "INFO" "✓ Node Exporter installed - Running on: https://$IP_ADDRESS:9100"
    fi
    if should_install "grafana"; then
        local grafana_protocol="https"
        # if [[ -n "$GRAFANA_CERT_PATH" && -n "$GRAFANA_KEY_PATH" ]]; then
        grafana_protocol="https"
        # fi
        log_message "INFO" "✓ Grafana installed - Access at: ${grafana_protocol}://$IP_ADDRESS:3000"
        log_message "INFO" "  Default login: admin/admin"
    fi
    log_message "INFO" "===================="
    log_message "INFO" "Installation completed successfully!"
    log_message "INFO" "Log file: $LOG_FILE"
}

main() {
    # Initialize log file
    echo "=== Monitoring Stack Installation Started at $(date) ===" > "$LOG_FILE"
    log_message "INFO" "Starting monitoring stack installation"

    # Check if any component should be installed
    if ! should_install "prometheus" && ! should_install "grafana" && ! should_install "node_exporter"; then
        log_message "ERROR" "No components selected for installation. Please set INSTALL_PROMETHEUS, INSTALL_GRAFANA, or INSTALL_NODE_EXPORTER to true in .env file"
        exit 1
    fi

    # Check existing services and skip if already installed and running
    local skip_prometheus=false skip_grafana=false skip_node_exporter=false

    if should_install "prometheus"; then
        if check_service_status "prometheus" "prometheus" "$PROMETHEUS_VERSION" "9090"; then
            skip_prometheus=true
            log_message "INFO" "Skipping Prometheus installation as it is already running with correct version"
        fi
    fi

    if should_install "grafana"; then
        if check_service_status "grafana-server" "" "" "3000"; then
            skip_grafana=true
            log_message "INFO" "Skipping Grafana installation as it is already running"
        fi
    fi

    if should_install "node_exporter"; then
        if check_service_status "node_exporter" "node_exporter" "$NODE_EXPORTER_VERSION" "9100"; then
            skip_node_exporter=true
            log_message "INFO" "Skipping Node Exporter installation as it is already running with correct version"
        fi
    fi

    # cleanup_existing

    # update_system

    # Call the cleanup function
    cleanup_old_logs

    # Install components based on configuration
    if should_install "node_exporter" && [[ "$skip_node_exporter" != "true" ]]; then
        install_node_exporter
        if check_service_status "prometheus" "prometheus" "$PROMETHEUS_VERSION" "9090"; then
            create_prometheus_config
            sudo systemctl stop prometheus
            sudo systemctl start prometheus
        fi
    fi
    if should_install "prometheus" && [[ "$skip_prometheus" != "true" ]]; then
        install_prometheus
        # Restart Prometheus if Node Exporter was also installed or updated
        if should_install "node_exporter" && [[ "$skip_node_exporter" != "true" ]]; then
            log_message "INFO" "Restarting Prometheus to apply updated configuration"
            sudo systemctl restart prometheus
        fi
    fi
    if should_install "grafana" && [[ "$skip_grafana" != "true" ]]; then
        install_grafana
    fi
    # Clean up downloaded files
    cleanup_downloads
    # Display summary
    display_summary
    log_message "INFO" "Script execution completed successfully"
}

main "$@"