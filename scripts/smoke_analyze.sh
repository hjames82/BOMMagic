#!/bin/bash

# Smoke test for BOM detection API
# Usage: ./smoke_analyze.sh <pdf_file>

if [ $# -eq 0 ]; then
    echo "Usage: $0 <pdf_file>"
    exit 1
fi

PDF_FILE="$1"

if [ ! -f "$PDF_FILE" ]; then
    echo "Error: File '$PDF_FILE' not found"
    exit 1
fi

SERVER_URL="http://localhost:5000"
API_URL="${SERVER_URL}/v1/analyze"

echo "========================================="
echo "BOM Detection Smoke Test"
echo "========================================="
echo "PDF File: $PDF_FILE"
echo "API URL: $API_URL"
echo ""

# Check if server is running
echo -n "Checking server health... "
HEALTH_RESPONSE=$(curl -s "${SERVER_URL}/v1/health" 2>/dev/null)
if [ $? -ne 0 ]; then
    echo "FAILED"
    echo "Error: Server is not running on port 5000"
    exit 1
fi
echo "OK"

# Display version info
echo ""
echo "System Versions:"
echo "$HEALTH_RESPONSE" | python3 -m json.tool 2>/dev/null || echo "$HEALTH_RESPONSE"
echo ""

# Upload and analyze PDF
echo "Uploading and analyzing PDF..."
echo "-----------------------------------------"

RESPONSE=$(curl -s -X POST \
    -F "file=@${PDF_FILE}" \
    "${API_URL}")

if [ $? -ne 0 ]; then
    echo "Error: Failed to upload file"
    exit 1
fi

# Pretty print the response
echo ""
echo "Analysis Results:"
echo "-----------------------------------------"
echo "$RESPONSE" | python3 -c "
import sys
import json

try:
    data = json.load(sys.stdin)
    
    if 'error' in data:
        print(f\"ERROR: {data['error']}\")
        if 'details' in data:
            print(f\"Details: {data['details']}\")
        sys.exit(1)
    
    print(f\"Document ID: {data.get('document_id', 'N/A')}\")
    print(f\"Page Count: {data.get('page_count', 'N/A')}\")
    print()
    
    if 'timings' in data:
        print('Processing Times:')
        for key, value in data['timings'].items():
            print(f\"  {key}: {value}ms\")
        print()
    
    detections = data.get('detections', [])
    print(f\"Total Detections: {len(detections)}\")
    print()
    
    if detections:
        for i, det in enumerate(detections, 1):
            print(f\"Detection #{i}:\")
            print(f\"  Page: {det['page']}\")
            print(f\"  Confidence: {det['confidence']:.2%}\")
            print(f\"  Headers: {', '.join(det['headers'])}\")
            bbox = det['bbox']
            print(f\"  Bounding Box: ({bbox[0]:.1f}, {bbox[1]:.1f}, {bbox[2]:.1f}, {bbox[3]:.1f})\")
            print()
            
        # Link to review UI
        doc_id = data.get('document_id')
        if doc_id:
            print(f\"Review URL: {SERVER_URL}/review/{doc_id}\")
    else:
        print('No BOM regions detected in this document.')
        print('This might mean:')
        print('  - The document does not contain table-like BOM structures')
        print('  - The confidence threshold (0.70) filtered out weak detections')
        print('  - OCR quality issues prevented proper text extraction')
        
except json.JSONDecodeError:
    print('Error: Invalid JSON response')
    print('Raw response:', sys.stdin.read())
    sys.exit(1)
except Exception as e:
    print(f'Error processing response: {e}')
    sys.exit(1)
" 2>&1

echo ""
echo "========================================="
echo "Smoke test completed"
echo "========================================="