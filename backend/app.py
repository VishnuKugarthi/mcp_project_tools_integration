import os
import json
import re # Import regex module for parsing
from flask import Flask, request, jsonify
from flask_cors import CORS
import requests
from dotenv import load_dotenv
import PyPDF2 # Import PyPDF2 for PDF reading

# Load environment variables from .env file
load_dotenv()

app = Flask(__name__)
CORS(app) # Enable CORS for frontend communication

# In-memory storage for conversation history.
# In a real application, this would be stored in a database
# and associated with a user session ID.
conversation_history = []

# Replace with your actual Gemini API key from environment variables
# For local development, set GEMINI_API_KEY in your .env file
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")
GEMINI_API_URL = "https://generativelanguage.googleapis.com/v1beta/models/gemini-2.0-flash:generateContent"

# --- Load External Product Catalog from JSON file ---
# Construct the absolute path to the product_catalog.json file
# This makes sure the file is found regardless of where you run app.py from.
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
PRODUCT_CATALOG_FILE = os.path.join(BASE_DIR, 'files', 'product_catalog.json')

PRODUCT_CATALOG = {} # Initialize as an empty dictionary

try:
    with open(PRODUCT_CATALOG_FILE, 'r') as f:
        # Load the content directly. If the JSON is a dictionary, it will be loaded as such.
        loaded_catalog = json.load(f)
        
        # Now, ensure all keys in the loaded catalog are uppercase for consistent lookup.
        PRODUCT_CATALOG = {k.upper(): v for k, v in loaded_catalog.items()}

    print(f"Successfully loaded product catalog from {PRODUCT_CATALOG_FILE}")
except FileNotFoundError:
    print(f"Error: product_catalog.json not found at {PRODUCT_CATALOG_FILE}")
    print("Please ensure 'files/product_catalog.json' exists in your backend directory.")
except json.JSONDecodeError:
    print(f"Error: Could not decode JSON from {PRODUCT_CATALOG_FILE}")
    print("Please check if the JSON file is correctly formatted.")
except Exception as e:
    print(f"An unexpected error occurred while loading product catalog: {e}")


def get_product_details(product_id: str):
    """
    Fetches product details from the loaded product catalog.
    """
    print(f"Tool: get_product_details called with product_id: {product_id}")
    product_info = PRODUCT_CATALOG.get(product_id.upper()) # Use .upper() for case-insensitivity
    if product_info:
        return {"status": "success", "data": product_info}
    else:
        return {"status": "error", "message": f"Product with ID '{product_id}' not found."}

# --- External Resource Tool: JSONPlaceholder API (Existing) ---
JSONPLACEHOLDER_BASE_URL = "https://jsonplaceholder.typicode.com"

def get_jsonplaceholder_posts(limit: int = 1):
    """
    Fetches a specified number of posts from the JSONPlaceholder API.
    This simulates retrieving data from an external web service.
    """
    print(f"Tool: get_jsonplaceholder_posts called with limit: {limit}")
    try:
        response = requests.get(f"{JSONPLACEHOLDER_BASE_URL}/posts?_limit={limit}")
        response.raise_for_status()
        posts = response.json()
        simplified_posts = [{"id": p["id"], "title": p["title"]} for p in posts]
        return {"status": "success", "data": simplified_posts}
    except requests.exceptions.RequestException as e:
        return {"status": "error", "message": f"Failed to fetch posts: {e}"}

# --- NEW Tool: Live PDF FAQ Search ---
FAQ_PDF_FILE = os.path.join(BASE_DIR, 'files', 'faq.pdf')
RAW_PDF_TEXT_CONTENT = "" # Global variable to store raw extracted PDF text
FAQ_DATA = {} # Global variable to store parsed FAQ data (question -> answer)

def load_pdf_content():
    """
    Loads and extracts raw text content from the faq.pdf file.
    """
    global RAW_PDF_TEXT_CONTENT
    if not os.path.exists(FAQ_PDF_FILE):
        print(f"Error: FAQ PDF file not found at {FAQ_PDF_FILE}")
        print("Please ensure 'files/faq.pdf' exists in your backend directory.")
        return

    try:
        with open(FAQ_PDF_FILE, 'rb') as f: # Open in binary read mode
            reader = PyPDF2.PdfReader(f)
            text = ""
            for page_num in range(len(reader.pages)):
                page = reader.pages[page_num]
                text += page.extract_text() + "\n" # Extract text from each page
            RAW_PDF_TEXT_CONTENT = text
        print(f"Successfully loaded raw text from {FAQ_PDF_FILE}")
    except Exception as e:
        print(f"Error loading or extracting text from PDF: {e}")
        RAW_PDF_TEXT_CONTENT = "" # Clear content on error

def parse_faq_pdf_content():
    """
    Parses the raw extracted PDF text into a structured FAQ_DATA dictionary.
    This function is called once after the raw PDF content is loaded.
    """
    global FAQ_DATA
    if not RAW_PDF_TEXT_CONTENT:
        print("No raw PDF content to parse. FAQ_DATA will be empty.")
        FAQ_DATA = {}
        return

    # This regex pattern tries to find "Number. Question?" or "Heading:" followed by content
    # It's a simplified approach based on the provided faq.pdf structure.
    # Adjust regex if your PDF structure changes significantly.
    # It captures the question/heading and the answer content until the next question/heading or end.
    
    # Pattern for numbered questions (e.g., "1. What is Base44?\nA. ...")
    # and for section headings (e.g., "Shipping Information:\n...")
    
    # Split the text by known question/section patterns
    # We'll use a more robust splitting method to capture sections accurately.
    
    # Define markers for the start of a new FAQ entry or section
    # Using regex to split by "Number. Question?" or "Heading:"
    
    # First, let's clean up some common PDF extraction artifacts like extra newlines
    cleaned_text = re.sub(r'\n{2,}', '\n', RAW_PDF_TEXT_CONTENT).strip()
    
    # Split by patterns like "1. Question", "2. Question", "Shipping Information:", "Return Policy:" etc.
    # The regex uses a positive lookahead to split *before* the next pattern, keeping the delimiter.
    sections = re.split(r'(?=\d+\.\s.*?\?|Shipping Information:|Return Policy:|Product Warranty:|Payment Methods:|Customer Support:|Account Management:|Delivery Tracking:)', cleaned_text)
    
    parsed_data = {}
    current_key = None
    
    for section in sections:
        section = section.strip()
        if not section:
            continue

        # Try to match numbered questions (e.g., "1. What is Base44?\nA. ...")
        match_num_q = re.match(r'(\d+\.\s.*?)\n(A\.\s.*)', section, re.DOTALL)
        if match_num_q:
            question = match_num_q.group(1).strip()
            answer = match_num_q.group(2).strip()
            parsed_data[question.lower()] = answer
            current_key = None # Reset for next section
            continue

        # Try to match section headings (e.g., "Shipping Information:\n...")
        match_heading = re.match(r'(.*?):(?=\n|$)', section) # Matches "Heading:"
        if match_heading:
            heading = match_heading.group(1).strip()
            content = section[len(match_heading.group(0)):].strip() # Content after heading
            if content: # Only add if there's actual content
                parsed_data[heading.lower()] = content
            current_key = heading.lower()
            continue
            
        # If it's content that belongs to the previous heading but wasn't captured in the split
        if current_key and current_key in parsed_data:
            parsed_data[current_key] += "\n" + section # Append to previous content
            
    FAQ_DATA = parsed_data
    print("FAQ content parsed into structured data.")
    # print(json.dumps(FAQ_DATA, indent=2)) # Uncomment to see parsed data

# Call functions to load and parse PDF content at startup
load_pdf_content()
parse_faq_pdf_content()


def get_answers_from_pdf(query: str):
    """
    Searches the parsed FAQ data for answers based on a user query.
    Performs a more intelligent lookup than simple keyword search.
    """
    print(f"Tool: get_answers_from_pdf called with query: '{query}'")
    
    if not FAQ_DATA:
        return {"status": "error", "answer": "The FAQ document could not be loaded or parsed, or is empty.", "source": "FAQ PDF"}

    query_lower = query.lower()
    
    found_answer = None
    
    # --- Improved Search Logic ---
    # 1. Try to find direct matches with FAQ questions/headings
    for faq_question, faq_answer in FAQ_DATA.items():
        if query_lower in faq_question or faq_question in query_lower:
            found_answer = faq_answer
            break
    
    # 2. If no direct match, try to find keywords within the answers
    if not found_answer:
        for faq_question, faq_answer in FAQ_DATA.items():
            if any(keyword in faq_answer.lower() for keyword in query_lower.split()):
                found_answer = faq_answer
                break # Found a relevant answer based on keywords
                
    if found_answer:
        return {"status": "success", "answer": found_answer, "source": "FAQ PDF"}
    else:
        # If no direct match or keyword match, return "not_found" status
        return {"status": "not_found", "answer": "I couldn't find a direct answer to your question in the FAQ. Please try rephrasing or contact support.", "source": "FAQ PDF"}


# Map tool names to their corresponding functions
AVAILABLE_TOOLS = {
    "get_product_details": get_product_details,
    "get_jsonplaceholder_posts": get_jsonplaceholder_posts,
    "get_answers_from_pdf": get_answers_from_pdf # Add the new PDF FAQ tool
}

# --- Tool Definitions for the LLM ---
TOOL_DEFINITIONS = [
    {
        "name": "get_product_details",
        "description": "Retrieves details about a product from the product catalog. Use this when the user asks about a specific product ID like P101, P102, etc.",
        "parameters": {
            "type": "object",
            "properties": {
                "product_id": {
                    "type": "string",
                    "description": "The unique identifier of the product (e.g., P101, P102)."
                }
            },
            "required": ["product_id"]
        }
    },
    {
        "name": "get_jsonplaceholder_posts",
        "description": "Fetches a list of recent posts or articles from an external resource. Use this when the user asks for recent news, articles, or blog posts.",
        "parameters": {
            "type": "object",
            "properties": {
                "limit": {
                    "type": "integer",
                    "description": "The maximum number of posts to retrieve (default is 1).",
                    "default": 1
                }
            }
        }
    },
    {
        "name": "get_answers_from_pdf",
        "description": "Searches the FAQ document (PDF) to find answers to common questions about Base44, applications, integrations, deployment, data security, ownership, shipping, returns, warranty, payment methods, customer support, account management, or delivery tracking. Provide the exact question or relevant keywords from the user's query.",
        "parameters": {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "The user's specific question or keywords to search for in the FAQ PDF.",
                }
            },
            "required": ["query"]
        }
    }
]

@app.route('/chat', methods=['POST'])
def chat():
    """
    Handles incoming chat messages, manages conversation context,
    and interacts with the LLM, including tool calling.
    """
    user_message = request.json.get('message')
    if not user_message:
        return jsonify({"error": "No message provided"}), 400

    print(f"Received message: {user_message}")

    # Add user's message to history
    conversation_history.append({"role": "user", "parts": [{"text": user_message}]})

    # --- Context Orchestration: Prepare initial prompt with history and tool definitions ---
    MAX_HISTORY_TURNS = 5
    recent_history = conversation_history[-MAX_HISTORY_TURNS * 2:]

    payload_initial_call = {
        "contents": recent_history,
        "tools": [{"function_declarations": TOOL_DEFINITIONS}] # Declare all available tools
    }

    headers = {
        "Content-Type": "application/json"
    }

    try:
        # --- First LLM Call: Get LLM's initial decision (direct response or tool call) ---
        response_initial = requests.post(
            f"{GEMINI_API_URL}?key={GEMINI_API_KEY}",
            headers=headers,
            json=payload_initial_call
        )
        response_initial.raise_for_status()
        
        llm_response_data_initial = response_initial.json()
        
        llm_text = "" # Initialize llm_text here

        if (llm_response_data_initial and 
            llm_response_data_initial.get('candidates') and 
            llm_response_data_initial['candidates'][0].get('content') and
            llm_response_data_initial['candidates'][0]['content'].get('parts')):
            
            first_part = llm_response_data_initial['candidates'][0]['content']['parts'][0]

            if first_part.get('functionCall'):
                # LLM wants to call a tool!
                function_call = first_part['functionCall']
                tool_name = function_call['name']
                tool_args = function_call['args']
                
                print(f"LLM requested tool: {tool_name} with args: {tool_args}")

                if tool_name in AVAILABLE_TOOLS:
                    tool_function = AVAILABLE_TOOLS[tool_name]
                    
                    # Execute the tool
                    tool_output = tool_function(**tool_args)
                    print(f"Tool output: {tool_output}")

                    # --- Second LLM Call: Send tool output back to LLM for final response ---
                    # Add the LLM's tool call and the tool's response to the history for the next turn.
                    conversation_history.append({
                        "role": "model",
                        "parts": [{"functionCall": function_call}]
                    })
                    conversation_history.append({
                        "role": "function",
                        "parts": [{"functionResponse": {"name": tool_name, "response": tool_output}}]
                    })

                    payload_second_call = {
                        "contents": conversation_history[-MAX_HISTORY_TURNS * 2:]
                    }
                    
                    response_second = requests.post(
                        f"{GEMINI_API_URL}?key={GEMINI_API_KEY}",
                        headers=headers,
                        json=payload_second_call
                    )
                    response_second.raise_for_status()
                    llm_response_data_second = response_second.json()

                    if llm_response_data_second and llm_response_data_second.get('candidates'):
                        final_candidate = llm_response_data_second['candidates'][0]
                        if final_candidate.get('content') and final_candidate['content'].get('parts'):
                            for part in final_candidate['content']['parts']:
                                if part.get('text'):
                                    llm_text += part['text']
                    
                    if not llm_text:
                        llm_text = "I'm sorry, I couldn't generate a response after using the tool."

                else:
                    llm_text = f"I tried to use a tool called '{tool_name}', but it's not available."
            else:
                # LLM provided a direct text response
                if isinstance(first_part.get('text'), str):
                    llm_text = first_part.get('text')
                elif isinstance(llm_response_data_initial['candidates'][0]['content']['parts'], list):
                     for p in llm_response_data_initial['candidates'][0]['content']['parts']:
                         if p.get('text'):
                             llm_text += p['text']
                
                if not llm_text:
                    llm_text = "I'm sorry, I couldn't generate a direct response."
        else:
            llm_text = "I'm sorry, I couldn't understand the AI's initial response."

        # Add model's final response to history
        conversation_history.append({"role": "model", "parts": [{"text": llm_text}]})

        return jsonify({"response": llm_text})

    except requests.exceptions.RequestException as e:
        print(f"Error calling Gemini API: {e}")
        return jsonify({"error": "Failed to communicate with the AI model."}), 500
    except json.JSONDecodeError as e:
        print(f"Error decoding JSON from LLM response: {e}")
        return jsonify({"error": "Invalid response from AI model."}), 500
    except Exception as e:
        print(f"An unexpected error occurred: {e}")
        return jsonify({"error": "An internal server error occurred."}), 500

if __name__ == '__main__':
    # Run the Flask app
    # In a production environment, use a WSGI server like Gunicorn
    app.run(debug=True, port=5000)
