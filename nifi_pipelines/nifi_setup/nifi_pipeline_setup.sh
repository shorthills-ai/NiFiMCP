#!/bin/bash

set -e  # Exit on error

NIFI_API_URL="https://localhost:8443/nifi-api"
NIFI_HOME="/nifi_pipelines/nifi_setup/nifi-2.4.0"
PIPELINES_DIR="/nifi_pipelines"

# Function to wait for NiFi API to be ready
wait_for_nifi() {
    for i in {1..30}; do
        if curl --insecure -s -f "${NIFI_API_URL}/flow/about" > /dev/null; then
            echo "✅ NiFi API is ready"
            return 0
        fi
        echo "⏳ Waiting for NiFi API (attempt ${i}/30)..."
        sleep 10
    done
    echo "❌ NiFi API not ready after 5 minutes"
    exit 1
}

# Get root process group ID
get_root_pg_id() {
    curl --insecure -s "${NIFI_API_URL}/flow/about" | jq -r '.about.rootGroupId'
}

wait_for_nifi

ROOT_PG_ID=$(get_root_pg_id)
echo "📍 Root Process Group ID: ${ROOT_PG_ID}"

# Iterate over each pipeline subfolder (skip nifi_setup)
for pipeline_dir in "${PIPELINES_DIR}"/*/; do
    pipeline_name=$(basename "${pipeline_dir}")
    if [ "${pipeline_name}" = "nifi_setup" ]; then
        continue
    fi
    
    # Check for .xml or .json templates
    template_file_xml="${pipeline_dir}/template.xml"
    template_file_json="${pipeline_dir}/*.json"
    if [ -f "${template_file_xml}" ]; then
        template_file="${template_file_xml}"
    elif ls ${template_file_json} 2>/dev/null | grep -q .; then
        template_file=$(ls ${template_file_json} | head -n 1)
    else
        echo "⚠️ Skipping ${pipeline_name}: No template.xml or .json found"
        continue
    fi
    
    echo "🔧 Uploading template for ${pipeline_name}..."
    if [[ "${template_file}" == *.xml ]]; then
        TEMPLATE_ID=$(curl --insecure -s -X POST -H "Content-Type: multipart/form-data" \
            -F "template=@${template_file}" \
            "${NIFI_API_URL}/process-groups/${ROOT_PG_ID}/templates" | jq -r '.id')
    else
        TEMPLATE_ID=$(curl --insecure -s -X POST -H "Content-Type: application/json" \
            -d @${template_file} \
            "${NIFI_API_URL}/process-groups/${ROOT_PG_ID}/process-groups" | jq -r '.id')
    fi
    
    if [ -z "${TEMPLATE_ID}" ]; then
        echo "❌ Failed to upload template for ${pipeline_name}"
        continue
    fi
    
    echo "🚀 Instantiating ${pipeline_name} on canvas..."
    if [[ "${template_file}" == *.xml ]]; then
        curl --insecure -s -X POST \
            -H "Content-Type: application/json" \
            -d "{\"originX\": 0, \"originY\": 0, \"templateId\": \"${TEMPLATE_ID}\"}" \
            "${NIFI_API_URL}/process-groups/${ROOT_PG_ID}/template-instance"
    fi
    echo "✅ ${pipeline_name} deployed"
done

echo "🎉 All pipelines deployed to canvas"
