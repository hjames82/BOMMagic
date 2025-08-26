# BOMMagic

Automated Bill of Materials (BOM) extraction from engineering drawings using OCR, ML table detection, and intelligent data extraction.

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

### Upload Document
```
POST /v1/documents
Content-Type: multipart/form-data
file: <binary>

Response: { "job_id": "uuid", "status": "processing" }
```

### Check Job Status
```
GET /v1/jobs/{job_id}

Response: { 
  "status": "completed|processing|failed|requires_review",
  "confidence": 0.95,
  "export_url": "https://..."
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

## Development

### Running Tests
```bash
pytest tests/
```

### Adding New Extraction Rules
Edit `services/validation_service.py` to add domain-specific validation rules.

### Debugging OCR Issues
Check `/tmp/ocr_debug/` for intermediate OCR outputs.

## License

Proprietary - BOMMagic SaaS