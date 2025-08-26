# BOM Detection Smoke Test

This directory contains smoke tests for the BOM detection system.

## Prerequisites

1. Ensure the Flask server is running on port 5000
2. Have a scanned PDF document ready for testing

## Running the Smoke Test

1. Place your test PDF in this directory (do not commit PDFs to version control)
2. Run the smoke test script:

```bash
./scripts/smoke_analyze.sh <your-pdf-file.pdf>
```

## What the Test Does

The smoke test script will:

1. Upload the PDF to the `/v1/analyze` endpoint
2. Process the document through OCR if needed
3. Detect BOM regions using the pure-Python detection system
4. Print the detection results including:
   - Document ID
   - Number of detections found
   - For each detection:
     - Page number
     - Confidence score
     - Detected headers
     - Bounding box coordinates

## Expected Output

A successful test should show:
- Document successfully uploaded and processed
- Detection results with confidence scores >= 0.70
- Processing timings for OCR and detection phases

## Troubleshooting

If no detections are found:
- Ensure the PDF contains table-like BOM structures
- Check that OCR is working (tesseract and ocrmypdf must be installed)
- Verify the PDF has proper text extraction

## Sample PDFs

Do not commit sample PDFs to the repository. Store them locally in this directory and add `*.pdf` to `.gitignore`.