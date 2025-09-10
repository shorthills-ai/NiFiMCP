#!/bin/bash

set -e  # Exit on error

NIFI_VERSION="2.4.0"
NIFI_HOME="/nifi_pipelines/nifi_setup/nifi-${NIFI_VERSION}"
NIFI_DOWNLOAD_URL="https://dlcdn.apache.org/nifi/${NIFI_VERSION}/nifi-${NIFI_VERSION}-bin.zip"

echo "📥 Downloading NiFi ${NIFI_VERSION}..."
wget -q "${NIFI_DOWNLOAD_URL}" -O nifi.zip || { echo "❌ Download failed"; exit 1; }

echo "📦 Unzipping NiFi..."
unzip -q nifi.zip -d /nifi_pipelines/nifi_setup/ || { echo "❌ Unzip failed"; exit 1; }
rm nifi.zip

echo "🔧 Setting permissions..."
chmod -R 755 "${NIFI_HOME}"

# Customize nifi.properties for HTTPS on 8443
sed -i 's/nifi.web.http.port=8080/nifi.web.https.port=8443/g' "${NIFI_HOME}/conf/nifi.properties"
# Disable auth by default (enable if needed via secrets)
sed -i 's/nifi.security.user.login.identity.provider=/#nifi.security.user.login.identity.provider=/g' "${NIFI_HOME}/conf/nifi.properties"

echo "✅ NiFi installed at ${NIFI_HOME}"
