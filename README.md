# MCP Project

This repository contains a simple full-stack application demonstrating the Model Context Protocol (MCP) pattern. It consists of a Flask backend and a static frontend.

## Project Structure

```
backend/
  app.py                # Main Flask API server
  requirements.txt      # Python dependencies
  files/
    faq.pdf             # FAQ document (PDF)
    faq.txt             # FAQ document (text)
    product_catalog.json# Product catalog data
frontend/
  index.html            # Simple frontend UI
```

## Features

- **Product Catalog**: Retrieve product details from a JSON catalog.
- **FAQ PDF Search**: Search and extract answers from a PDF FAQ document using regex and text extraction.
- **External API Demo**: Fetches posts from JSONPlaceholder to demonstrate external API integration.
- **LLM Tool Calling**: Integrates with Gemini API for conversational AI and tool invocation.

## Getting Started

### Backend Setup

1. Navigate to the `backend` directory:

   ```sh
   cd backend
   ```

2. Install dependencies:

   ```sh
   pip install -r requirements.txt
   ```

3. Add your Gemini API key to a `.env` file:

   ```
   GEMINI_API_KEY=your_api_key_here
   ```

4. Ensure the `files/` directory contains `faq.pdf` and `product_catalog.json`.
5. Start the Flask server:

   ```sh
   python app.py
   ```

### Frontend Setup

1. Open `frontend/index.html` in your browser.
2. The frontend communicates with the backend at `http://localhost:5000`.

## API Endpoints

- `POST /chat` — Main endpoint for chat and tool invocation.

## MCP Pattern

This project demonstrates the MCP pattern by:

- Structuring context and tool definitions for LLMs.
- Orchestrating tool calls and responses in a conversational flow.
