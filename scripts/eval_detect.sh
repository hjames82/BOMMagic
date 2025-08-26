#!/bin/bash

# BOM Detection Evaluation Script
# Usage: ./eval_detect.sh

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(dirname "$SCRIPT_DIR")"

echo "========================================="
echo "BOM Detection Evaluation"
echo "========================================="

# Check if server is running
echo -n "Checking server health... "
HEALTH_RESPONSE=$(curl -s "http://localhost:5000/v1/health" 2>/dev/null)
if [ $? -ne 0 ]; then
    echo "FAILED"
    echo "Error: Server is not running on port 5000"
    exit 1
fi
echo "OK"

# Run Python evaluation script
echo ""
echo "Running evaluation on golden dataset..."
echo "-----------------------------------------"

python3 "$ROOT_DIR/tools/eval_detect.py" \
    --api-url "http://localhost:5000/v1/analyze" \
    --manifest "$ROOT_DIR/tests/golden/manifest.yaml" \
    --pdf-dir "$ROOT_DIR/tests/golden" \
    --output-dir "$ROOT_DIR/reports/detect"

EXIT_CODE=$?

echo ""
echo "========================================="
if [ $EXIT_CODE -eq 0 ]; then
    echo "✅ EVALUATION PASSED"
else
    echo "❌ EVALUATION FAILED"
fi
echo "========================================="

exit $EXIT_CODE