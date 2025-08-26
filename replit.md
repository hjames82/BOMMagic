# Overview

BOMMagic is a Flask-based web application that automates the extraction of Bill of Materials (BOMs) from engineering drawings and documents. The system uses OCR, computer vision, and machine learning techniques to identify and extract structured BOM data from uploaded PDF files and images. Users can upload documents, monitor processing jobs, review extracted data for accuracy, and export results in various formats (CSV, Excel).

# User Preferences

Preferred communication style: Simple, everyday language.

# System Architecture

## Web Framework Architecture
- **Flask Application**: Core web framework with modular blueprint structure
- **Authentication**: Replit Auth integration using OAuth2 with Flask-Dance for user management
- **Session Management**: Flask-Login for user session handling with permanent sessions
- **Database ORM**: SQLAlchemy with Flask-SQLAlchemy for database operations

## Processing Pipeline Architecture
- **Document Processor**: Main orchestration service coordinating the entire BOM extraction pipeline
- **OCR Service**: Handles text extraction from PDFs and images using OCRmyPDF and Tesseract
- **Table Detector**: Computer vision service for identifying BOM tables within documents using OpenCV
- **Data Extractor**: Structured data extraction using Camelot and pdfplumber for table parsing
- **Validation Service**: Rule-based validation system with confidence scoring for extracted data
- **Export Service**: Multi-format export capabilities (CSV, Excel) with pandas

## Data Architecture
- **Job Management**: Asynchronous job processing with status tracking (pending, processing, completed, failed, requires_review)
- **BOM Items**: Structured storage of extracted BOM components with fields like part numbers, descriptions, quantities
- **Accuracy Metrics**: Confidence scoring and validation results for quality assessment
- **User Management**: OAuth-based user system with job ownership and access control

## Processing Architecture
- **Asynchronous Processing**: Background worker system for handling document processing jobs
- **Multi-step Pipeline**: Sequential processing stages with error handling and recovery
- **Confidence Scoring**: Weighted validation system for assessing extraction quality
- **Review Workflow**: Manual review capability for low-confidence extractions

## Frontend Architecture
- **Bootstrap 5**: Responsive UI framework with custom CSS styling
- **Feather Icons**: Consistent iconography throughout the interface
- **Interactive Dashboard**: Real-time job monitoring with statistics and progress tracking
- **File Upload**: Drag-and-drop interface with client-side validation
- **Data Review Interface**: Editable table interface for manual correction of extracted data

# External Dependencies

## Authentication Services
- **Replit Auth**: OAuth2 authentication provider for user login and session management
- **Flask-Dance**: OAuth integration library for handling authentication flows

## OCR and Document Processing
- **Tesseract**: Open-source OCR engine for text extraction from images
- **OCRmyPDF**: PDF OCR processing tool for searchable PDF generation
- **PyPDF2**: Python PDF manipulation library for text extraction
- **Camelot**: Table extraction library specifically designed for PDF documents
- **pdfplumber**: Alternative PDF processing library for text and table extraction

## Computer Vision and Image Processing
- **OpenCV (cv2)**: Computer vision library for image processing and table detection
- **Pillow (PIL)**: Python imaging library for image format handling and manipulation
- **NumPy**: Numerical computing library supporting image processing operations

## Database System
- **SQLAlchemy**: Python SQL toolkit and ORM for database operations
- **Database**: Configurable database backend (PostgreSQL recommended for production)

## Data Processing and Export
- **Pandas**: Data manipulation library for BOM data processing and export formatting
- **openpyxl**: Excel file format support for XLSX export functionality

## Web Framework Dependencies
- **Flask**: Core web framework for HTTP handling and routing
- **Werkzeug**: WSGI utilities including proxy fix for deployment
- **Bootstrap**: Frontend CSS framework for responsive design
- **Feather Icons**: SVG icon library for consistent UI elements

## Development and Deployment
- **Gunicorn**: WSGI HTTP server for production deployment (implied by app structure)
- **Environment Configuration**: Environment variable-based configuration for sensitive settings