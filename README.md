# AI Note Scanner

Chrome extension that analyzes Google Docs lecture notes against uploaded slides to generate quiz questions and detect misconceptions.

# Open Source Code Used
Used some sample/documentation code for connecting the OpenAI API.

## Features

- Upload lecture slides (PDF or images)
- Automatic detection of which slides are covered by your notes
- Interactive quiz questions based on covered slides
- Questions refresh to test different topics

## Setup

### Backend

```bash
cd backend
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt

# Install system dependencies
# macOS: brew install poppler tesseract
# Linux: sudo apt-get install poppler-utils tesseract-ocr

# Create .env file with OPENAI_API_KEY
echo "OPENAI_API_KEY=your_key_here" > .env

# Run server
python main.py
```

### Extension

1. Open `chrome://extensions/`
2. Enable "Developer mode"
3. Click "Load unpacked"
4. Select the `extension/` directory

## Usage

1. Open a Google Docs document with your notes
2. Click the extension icon
3. Upload lecture slides
4. Click "Scan Notes"
5. Answer quiz questions and review misconceptions

## API Endpoints

- `POST /api/upload-slides` - Upload and parse slides
- `POST /api/scan-notes` - Analyze notes and return quiz question
- `POST /api/refresh-question` - Get new question from covered slides
- `GET /api/health` - Health check
