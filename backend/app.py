import os
import json
from flask import Flask, request, jsonify # type: ignore
from flask_cors import CORS # type: ignore
import requests # type: ignore
from dotenv import load_dotenv # type: ignore

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

# --- Simulated External Tool: Product Catalog (Existing) ---
PRODUCT_CATALOG = {
    "P101": {"name": "Laptop Pro", "price": "$1200", "description": "High-performance laptop for professionals."},
    "P102": {"name": "Wireless Mouse", "price": "$35", "description": "Ergonomic design with long battery life."},
    "P103": {"name": "Mechanical Keyboard", "price": "$90", "description": "RGB backlit keyboard with tactile switches."},
    "P104": {"name": "External SSD 1TB", "price": "$150", "description": "Fast and portable storage solution."},
}

def get_product_details(product_id: str):
    """
    Simulates fetching product details from an internal product catalog.
    """
    print(f"Tool: get_product_details called with product_id: {product_id}")
    product_info = PRODUCT_CATALOG.get(product_id.upper()) # .upper() for case-insensitivity
    if product_info:
        return {"status": "success", "data": product_info}
    else:
        return {"status": "error", "message": f"Product with ID '{product_id}' not found."}

# --- NEW External Resource Tool: JSONPlaceholder API ---
JSONPLACEHOLDER_BASE_URL = "https://jsonplaceholder.typicode.com"

def get_jsonplaceholder_posts(limit: int = 1):
    """
    Fetches a specified number of posts from the JSONPlaceholder API.
    This simulates retrieving data from an external web service.
    """
    print(f"Tool: get_jsonplaceholder_posts called with limit: {limit}")
    try:
        response = requests.get(f"{JSONPLACEHOLDER_BASE_URL}/posts?_limit={limit}")
        response.raise_for_status() # Raise an exception for HTTP errors
        posts = response.json()
        # Return a simplified version of the posts to keep context small
        simplified_posts = [{"id": p["id"], "title": p["title"]} for p in posts]
        return {"status": "success", "data": simplified_posts}
    except requests.exceptions.RequestException as e:
        return {"status": "error", "message": f"Failed to fetch posts: {e}"}

# Map tool names to their corresponding functions
AVAILABLE_TOOLS = {
    "get_product_details": get_product_details,
    "get_jsonplaceholder_posts": get_jsonplaceholder_posts # Add the new tool
}

# --- Tool Definitions for the LLM ---
# This structure tells the LLM about the tools it can use.
# The LLM will be prompted to output a JSON object if it wants to call a tool.
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
