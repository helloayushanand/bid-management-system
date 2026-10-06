# Bid Management Portal

A Streamlit application for extracting page-referenced text from tender PDF documents.

## Phase 1 Scope

- Upload one PDF document
- Extract embedded text from digital PDF pages
- Identify pages requiring OCR
- Apply local OCR to scanned pages
- Preserve page numbers and extraction metadata
- Preview the extracted text
- Download plain-text and JSON results
- Flag empty, unreadable, or failed pages

## Planned Phases

### Phase 1: PDF Extraction

Convert tender PDF documents into page-referenced text and structured JSON.

### Phase 2: LLM Analysis

Use the extracted document to identify:

- Tender metadata
- Scope of work
- Mandatory eligibility criteria
- Technical evaluation criteria
- Scoring rules
- Commercial requirements
- Important risks
- Tender summary

### Phase 3: Company Knowledge

Compare tender requirements with internal company credentials and supporting evidence.

## Project Structure

- app.py
- requirements.txt
- README.md
- .gitignore
- extraction/
- models/
- utils/
- outputs/
- tests/

## Activate the Environment

Run: .\env\Scripts\Activate.ps1

## Install Dependencies

Run: python -m pip install -r requirements.txt

## Run the Application

Run: python -m streamlit run app.py

## Run Tests

Run: python -m pytest -v

## Extraction Design

1. Validate the uploaded PDF.
2. Attempt native text extraction with PyMuPDF.
3. Evaluate the quality of each page.
4. Run OCR only when native extraction is inadequate.
5. Preserve page-level text and extraction metadata.
6. Generate human-readable TXT and machine-readable JSON output.

## Current Status

Phase 1 implementation in progress.
