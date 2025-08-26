# BOMMagic

Automated Bill of Materials (BOM) extraction from engineering drawings using OCR, ML table detection, and intelligent data extraction.

## System Status

- **Confidence Threshold**: 0.70 (configurable via `CONFIDENCE_THRESHOLD` env var)
- **Maximum File Size**: 25MB
- **Maximum Pages**: 200
- **Target F1 Score**: ≥ 0.90
- **OCR Engine**: Tesseract 5.5.0 + OCRmyPDF

## Overview

BOMMagic is a production-ready document processing pipeline that:
- Accepts scanned engineering drawings (PDF/images)
- Applies OCR to extract text layers
- Detects BOM tables using computer vision
- Extracts structured data using Camelot/pdfplumber
- Validates data with confidence scoring
- Exports clean CSV/XLSX or routes to manual review

## Quick Start

### Running on Replit

1. Fork this Repl
2. Environment variables are automatically configured (DATABASE_URL, STORAGE)
3. Click Run - the app starts on port 5000
4. Access the dashboard and upload documents

### Local Development

```bash
# Install system dependencies
sudo apt install tesseract-ocr ocrmypdf ghostscript poppler-utils

# Install Python dependencies
pip install -r requirements.txt

# Set environment variables
cp .env.example .env
# Edit .env with your database and storage credentials

# Run database migrations
flask db upgrade

# Start Redis for job queue
redis-server

# Start worker in separate terminal
python worker.py

# Start Flask app
python main.py
```

## Architecture

### Pipeline Stages

1. **Document Upload** - `/v1/documents` endpoint accepts files, stores originals
2. **OCR Processing** - OCRmyPDF adds searchable text layer
3. **Table Detection** - LayoutParser identifies BOM table regions
4. **Data Extraction** - Camelot/pdfplumber parse table structure
5. **Validation** - Rule engine checks data quality (confidence threshold 0.92)
6. **Export/Review** - High confidence → auto-export, Low confidence → manual review

### Components

- **Flask App** - Web interface and API endpoints
- **Worker** - Background job processor (Redis RQ)
- **PostgreSQL** - Document metadata, BOM data, job tracking
- **Object Storage** - Original documents and processed artifacts
- **Review UI** - Manual correction interface with PDF viewer

## API

### Analyze Document
```
POST /v1/analyze
Content-Type: multipart/form-data
file: <pdf>

Response: {
  "document_id": "uuid",
  "detections": [
    {
      "page": 1,
      "bbox": [x0, y0, x1, y1],
      "headers": ["Item", "Part Number", "Qty"],
      "confidence": 0.85,
      "scores": {
        "header_score": 0.9,
        "col_count_score": 1.0,
        "qty_numeric_score": 0.7
      }
    }
  ],
  "timings": {
    "ocr_ms": 1200,
    "detection_ms": 450
  }
}
```

### Health Check
```
GET /v1/health

Response: {
  "ok": true,
  "versions": {
    "tesseract": "5.5.0",
    "ocrmypdf": "16.10.1",
    "pdftotext": "24.11.0"
  },
  "config": {
    "confidence_threshold": 0.70,
    "max_file_size_mb": 25,
    "max_pages": 200
  }
}
```

### Detection Metrics
```
GET /v1/metrics/detect?hours=24

Response: {
  "confidence": { "average": 0.82, "min": 0.70, "max": 0.95 },
  "score_breakdown": { ... },
  "confidence_histogram": { "0.7-0.8": 12, "0.8-0.9": 8, ... },
  "accuracy": 0.91
}
```

### Manual Review
```
GET /review/{job_id} - Review interface
POST /api/jobs/{job_id}/approve - Approve with corrections
```

## Environment Variables

See `.env.example` for all required variables:
- `DATABASE_URL` - PostgreSQL connection string
- `REDIS_URL` - Redis for job queue
- `SECRET_KEY` - Flask secret key
- `STORAGE_BUCKET` - Object storage bucket
- `SENTRY_DSN` - Error tracking (optional)

## Database Schema

- **tenants** - Multi-tenant isolation
- **documents** - Original uploads
- **pages** - Document pages
- **tables** - Detected BOM tables
- **rows** - Extracted BOM line items
- **jobs** - Processing jobs
- **audits** - Change history

## Deployment

### Production Checklist

- [ ] Configure production database (PostgreSQL)
- [ ] Set up Redis for job queue
- [ ] Configure object storage with CDN
- [ ] Set Sentry DSN for monitoring
- [ ] Enable Replit Auth with proper roles
- [ ] Configure backup strategy
- [ ] Set up health checks and alerts

## Evaluation & Calibration

### Dataset Guidelines

The golden dataset (`tests/golden/manifest.yaml`) contains:
- **8 Clear BOMs**: Standard BOM tables with typical headers
- **4 Tricky BOMs**: Edge cases (minimal headers, foreign language, embedded in drawings)
- **3 Non-BOMs**: Documents without BOMs for false positive testing

### Running Evaluation

```bash
# Run full evaluation
./scripts/eval_detect.sh

# Calibrate confidence threshold
python tools/plot_thresholds.py --results reports/detect/eval_*.json

# CI/CD quality gate check
./scripts/mvp_detect_check.sh
```

### Interpreting Metrics

- **Precision**: Fraction of detected BOMs that are correct
- **Recall**: Fraction of actual BOMs that were detected
- **F1 Score**: Harmonic mean of precision and recall (target ≥ 0.90)
- **IoU**: Intersection over Union for bounding box accuracy (threshold 0.60)

### Quality Gates

1. **F1 Score ≥ 0.90**: Overall detection accuracy
2. **False Positives on Negatives ≤ 1**: Maximum 1 FP on non-BOM documents
3. **Confidence Threshold**: Currently 0.70 (adjust via calibration)

## Known Limitations

- **OCR Quality**: Detection accuracy depends on scan quality. Poor quality scans may need preprocessing.
- **Table Structure**: Works best with tabular BOMs. Narrative or paragraph-style parts lists may not be detected.
- **Language**: Primary optimization for English headers. Foreign language BOMs may have lower confidence.
- **Embedded BOMs**: BOMs embedded in CAD drawings may require higher resolution scans.
- **Multi-page BOMs**: Currently detects BOMs per page; continuation tables need manual merging.
- **Column Detection**: Assumes columnar structure with clear gaps. Merged cells may cause issues.

## Development

### Running Tests
```bash
# Unit tests
pytest tests/

# Smoke test
./scripts/smoke_analyze.sh sample.pdf

# Evaluation on golden dataset
./scripts/eval_detect.sh
```

### Adding New Extraction Rules
Edit `services/bom_detect.py` to:
- Add header keywords to `header_keywords` list
- Adjust scoring weights in `score_bom_region()`
- Modify confidence threshold via environment variable

### Debugging OCR Issues
- Check OCR cache: `SELECT * FROM ocr_cache;`
- View intermediate outputs in `/tmp/` 
- Enable debug logging: `export LOG_LEVEL=DEBUG`

## License

Proprietary - BOMMagic SaaS