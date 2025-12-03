# Setup

## Backend

```bash
cd backend
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt

# macOS
brew install poppler tesseract

# Linux
sudo apt-get install poppler-utils tesseract-ocr

# Create .env
echo "OPENAI_API_KEY=your_key" > .env

# Run
python main.py
```

## Extension

1. Open `chrome://extensions/`
2. Enable "Developer mode"
3. Click "Load unpacked"
4. Select `extension/` directory

## Usage

1. Open Google Docs with your notes
2. Click extension icon
3. Upload slides
4. Click "Scan Notes"
5. Answer quiz questions
