#!/bin/bash

# MVP Detection Check - CI/CD Quality Gate
# Runs evaluation and enforces quality gates

set -e  # Exit on error

echo "========================================="
echo "MVP BOM Detection Quality Gate Check"
echo "========================================="

# Check if server is running
echo -n "Checking server health... "
HEALTH_RESPONSE=$(curl -s "http://localhost:5000/v1/health" 2>/dev/null)
if [ $? -ne 0 ]; then
    echo "FAILED"
    echo "Error: Server is not running. Start it with: python main.py"
    exit 1
fi
echo "OK"

# Display system configuration
echo ""
echo "System Configuration:"
echo "$HEALTH_RESPONSE" | python3 -c "
import sys, json
data = json.load(sys.stdin)
print(f\"  Tesseract: {data['versions'].get('tesseract', 'N/A')}\")
print(f\"  Confidence Threshold: {data['config'].get('confidence_threshold', 'N/A')}\")
print(f\"  Max File Size: {data['config'].get('max_file_size_mb', 'N/A')}MB\")
print(f\"  Max Pages: {data['config'].get('max_pages', 'N/A')}\")
"

echo ""
echo "Running evaluation on golden dataset..."
echo "-----------------------------------------"

# Run evaluation
python3 tools/eval_detect.py \
    --api-url "http://localhost:5000/v1/analyze" \
    --manifest "tests/golden/manifest.yaml" \
    --pdf-dir "tests/golden" \
    --output-dir "reports/detect"

EVAL_EXIT_CODE=$?

# Check evaluation results
if [ $EVAL_EXIT_CODE -eq 0 ]; then
    echo ""
    echo "========================================="
    echo "✅ QUALITY GATES PASSED"
    echo "========================================="
    echo "The BOM detection system meets quality requirements:"
    echo "  - F1 Score ≥ 0.90"
    echo "  - False Positives on negatives ≤ 1"
    exit 0
else
    echo ""
    echo "========================================="
    echo "❌ QUALITY GATES FAILED"
    echo "========================================="
    echo "The BOM detection system does not meet quality requirements."
    echo "Review the evaluation report in reports/detect/"
    echo ""
    echo "Common issues:"
    echo "  - Low F1 score: Check detection thresholds and scoring logic"
    echo "  - Too many false positives: Adjust confidence threshold"
    echo "  - Missing detections: Review header keywords and column detection"
    exit 1
fi