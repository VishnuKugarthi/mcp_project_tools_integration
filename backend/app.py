import os
import json
import re
from flask import Flask, request, jsonify
from flask_cors import CORS
import requests
from dotenv import load_dotenv
import PyPDF2

# Load environment variables from .env file
load_dotenv()

app = Flask(__name__)
CORS(app)

# In-memory storage for conversation history.
conversation_history = []

GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")
GEMINI_API_URL = "https://generativelanguage.googleapis.com/v1beta/models/gemini-2.0-flash:generateContent"

# --- Load External Product Catalog from JSON file ---
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
PRODUCT_CATALOG_FILE = os.path.join(BASE_DIR, "files", "product_catalog.json")

PRODUCT_CATALOG = {}

try:
    with open(PRODUCT_CATALOG_FILE, "r") as f:
        loaded_catalog = json.load(f)
        PRODUCT_CATALOG = {k.upper(): v for k, v in loaded_catalog.items()}
    print(f"Successfully loaded product catalog from {PRODUCT_CATALOG_FILE}")
except FileNotFoundError:
    print(f"Error: product_catalog.json not found at {PRODUCT_CATALOG_FILE}")
    print(
        "Please ensure 'files/product_catalog.json' exists in your backend directory."
    )
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
    product_info = PRODUCT_CATALOG.get(product_id.upper())
    if product_info:
        return {"status": "success", "data": product_info}
    else:
        return {
            "status": "not_found",
            "message": f"Product with ID '{product_id}' not found.",
        }


# --- External Resource Tool: JSONPlaceholder API ---
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


# --- Live PDF FAQ Search Tool ---
FAQ_PDF_FILE = os.path.join(BASE_DIR, "files", "faq.pdf")
RAW_PDF_TEXT_CONTENT = ""
FAQ_DATA = {}

def load_pdf_content_and_extract_text():
    """
    Loads and extracts raw text content from the faq.pdf file.
    """
    global RAW_PDF_TEXT_CONTENT
    if not os.path.exists(FAQ_PDF_FILE):
        print(f"Error: FAQ PDF file not found at {FAQ_PDF_FILE}")
        print("Please ensure 'files/faq.pdf' exists in your backend directory.")
        return

    try:
        with open(FAQ_PDF_FILE, "rb") as f:
            reader = PyPDF2.PdfReader(f)
            text = ""
            for page_num in range(len(reader.pages)):
                page = reader.pages[page_num]
                extracted_text = page.extract_text()
                if extracted_text:
                    text += extracted_text.strip() + "\n"
            RAW_PDF_TEXT_CONTENT = text
        print(f"Successfully loaded raw text from {FAQ_PDF_FILE}")
    except Exception as e:
        print(f"Error loading or extracting text from PDF: {e}")
        RAW_PDF_TEXT_CONTENT = ""


def parse_faq_pdf_content_into_dictionary():
    """
    Parses the raw extracted PDF text into a structured FAQ_DATA dictionary.
    This function is called once after the raw PDF content is loaded.
    """
    global FAQ_DATA
    if not RAW_PDF_TEXT_CONTENT:
        print("No raw PDF content to parse. FAQ_DATA will be empty.")
        FAQ_DATA = {}
        return

    parsed_data = {}

    # Find all headings first
    # This pattern looks for "Xyz Information:" or "Return Policy:" etc.
    heading_pattern = re.compile(r"([A-Za-z\s]+?):", re.MULTILINE)

    # Get all matches for headings and their start/end positions
    headings_with_spans = [
        (match.group(1).strip().lower(), match.span())
        for match in heading_pattern.finditer(RAW_PDF_TEXT_CONTENT)
    ]

    # Add an artificial end marker for the last section
    if headings_with_spans:
        headings_with_spans.append(
            ("END_OF_DOCUMENT", (len(RAW_PDF_TEXT_CONTENT), len(RAW_PDF_TEXT_CONTENT)))
        )

    # Iterate through the headings to extract content
    for i in range(len(headings_with_spans) - 1):
        current_heading_text, current_span = headings_with_spans[i]
        next_span = headings_with_spans[i + 1][1]

        # Content starts after the current heading's match (end of span)
        # and ends before the next heading's match (start of next span)
        content_start = current_span[1]
        content_end = next_span[0]

        # Extract the raw content for this section
        raw_section_content = RAW_PDF_TEXT_CONTENT[content_start:content_end].strip()

        # Clean up the content: replace multiple spaces/newlines with single space
        cleaned_content = re.sub(r"\s+", " ", raw_section_content).strip()

        if current_heading_text and cleaned_content:
            parsed_data[current_heading_text] = cleaned_content

    # Handle the initial "FAQ's" title if it's present and not a proper section
    # This is a common artifact from PDF extraction
    if "faq's" in parsed_data:
        del parsed_data["faq's"]
    if "faqs" in parsed_data:
        del parsed_data["faqs"]

    FAQ_DATA = parsed_data
    print("FAQ content parsed into structured data.")
    # --- IMPORTANT DEBUGGING STEP ---
    # Uncomment the line below to see the parsed FAQ_DATA in your console when the app starts.
    # print("Parsed FAQ_DATA:")
    # print(json.dumps(FAQ_DATA, indent=2))


# Call functions to load and parse PDF content at startup
load_pdf_content_and_extract_text()
parse_faq_pdf_content_into_dictionary()


def get_answers_from_pdf(query: str):
    """
    Searches the parsed FAQ data for answers based on a user query.
    Performs a more robust search by checking the query against FAQ questions/answers.
    """
    print(f"Tool: get_answers_from_pdf called with query: '{query}'")

    if not FAQ_DATA:
        # This error means parsing failed, not that an answer wasn't found.
        return {
            "status": "error",
            "answer": "The FAQ document could not be loaded or parsed, or is empty.",
            "source": "FAQ PDF",
        }

    query_lower = query.lower()

    found_answer = None

    # --- Improved Search Logic ---
    # 1. Try to find direct matches with FAQ questions/headings (exact or partial match of query in key)
    # Prioritize finding the best match by checking how much of the query matches the key
    best_match_key = None
    max_match_len = 0

    for faq_question_key, faq_answer_content in FAQ_DATA.items():
        # Check if the query is directly contained within a FAQ question/heading key
        if query_lower in faq_question_key:
            if len(query_lower) > max_match_len:  # Prefer longer, more specific matches
                best_match_key = faq_question_key
                max_match_len = len(query_lower)
        # Also check if a part of the FAQ question/heading key is in the query (for broader matches)
        elif faq_question_key in query_lower:
            if (
                len(faq_question_key) > max_match_len
            ):  # Prefer longer, more specific matches
                best_match_key = faq_question_key
                max_match_len = len(faq_question_key)

    if best_match_key:
        found_answer = FAQ_DATA[best_match_key]

    # 2. If no direct match, try to find keywords within the answers
    # This is a fallback to find relevant content even if the query isn't a direct question.
    if not found_answer:
        query_keywords = (
            query_lower.split()
        )  # Split query into keywords for broader search

        # Iterate through all FAQ answers to find relevant keywords
        for faq_question_key, faq_answer_content in FAQ_DATA.items():
            # Check if any keyword from the query is present in the answer
            # Ensure keywords are not too short to avoid irrelevant matches (e.g., 'a', 'the')
            if any(
                keyword in faq_answer_content.lower()
                for keyword in query_keywords
                if len(keyword) > 4
            ):
                found_answer = faq_answer_content
                # For this demo, we take the first answer that contains any keyword.
                # In a real RAG, you'd use embeddings to find the *most* relevant chunk.
                break

    if found_answer:
        return {"status": "success", "answer": found_answer, "source": "FAQ PDF"}
    else:
        # If no direct match or keyword match, return "not_found" status
        return {
            "status": "not_found",
            "answer": "I couldn't find a direct answer to your question in the FAQ. Please try rephrasing or contact support.",
            "source": "FAQ PDF",
        }


# Map tool names to their corresponding functions
AVAILABLE_TOOLS = {
    "get_product_details": get_product_details,
    "get_jsonplaceholder_posts": get_jsonplaceholder_posts,
    "get_answers_from_pdf": get_answers_from_pdf,  # Add the new PDF FAQ tool
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
                    "description": "The unique identifier of the product (e.g., P101, P102).",
                }
            },
            "required": ["product_id"],
        },
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
                    "default": 1,
                }
            },
        },
    },
    {
        "name": "get_answers_from_pdf",
        "description": "Searches the FAQ document (PDF) to find answers to common questions about shipping, returns, warranty, payment methods, customer support, account management, or delivery tracking. Provide the exact question or relevant keywords from the user's query.",
        "parameters": {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "The user's specific question or keywords to search for in the FAQ PDF.",
                }
            },
            "required": ["query"],
        },
    },
]


@app.route("/chat", methods=["POST"])
def chat():
    """
    Handles incoming chat messages, manages conversation context,
    and interacts with the LLM, including tool calling.
    """
    user_message = request.json.get("message")
    if not user_message:
        return jsonify({"error": "No message provided"}), 400

    print(f"Received message: {user_message}")

    # Add user's message to history
    conversation_history.append({"role": "user", "parts": [{"text": user_message}]})

    # --- Context Orchestration: Prepare initial prompt with history and tool definitions ---
    MAX_HISTORY_TURNS = 5
    recent_history = conversation_history[-MAX_HISTORY_TURNS * 2 :]

    payload_initial_call = {
        "contents": recent_history,
        "tools": [
            {"function_declarations": TOOL_DEFINITIONS}
        ],  # Declare all available tools
    }

    headers = {"Content-Type": "application/json"}

    try:
        # --- First LLM Call: Get LLM's initial decision (direct response or tool call) ---
        response_initial = requests.post(
            f"{GEMINI_API_URL}?key={GEMINI_API_KEY}",
            headers=headers,
            json=payload_initial_call,
        )
        response_initial.raise_for_status()

        llm_response_data_initial = response_initial.json()

        llm_text = ""  # Initialize llm_text here

        if (
            llm_response_data_initial
            and llm_response_data_initial.get("candidates")
            and llm_response_data_initial["candidates"][0].get("content")
            and llm_response_data_initial["candidates"][0]["content"].get("parts")
        ):

            first_part = llm_response_data_initial["candidates"][0]["content"]["parts"][
                0
            ]

            if first_part.get("functionCall"):
                # LLM wants to call a tool!
                function_call = first_part["functionCall"]
                tool_name = function_call["name"]
                tool_args = function_call["args"]

                print(f"LLM requested tool: {tool_name} with args: {tool_args}")

                if tool_name in AVAILABLE_TOOLS:
                    tool_function = AVAILABLE_TOOLS[tool_name]

                    # Execute the tool
                    tool_output = tool_function(**tool_args)
                    print(f"Tool output: {tool_output}")

                    # --- Second LLM Call: Send tool output back to LLM for final response ---
                    # Add the LLM's tool call and the tool's response to the history for the next turn.
                    conversation_history.append(
                        {"role": "model", "parts": [{"functionCall": function_call}]}
                    )
                    conversation_history.append(
                        {
                            "role": "function",
                            "parts": [
                                {
                                    "functionResponse": {
                                        "name": tool_name,
                                        "response": tool_output,
                                    }
                                }
                            ],
                        }
                    )

                    payload_second_call = {
                        "contents": conversation_history[-MAX_HISTORY_TURNS * 2 :]
                    }

                    response_second = requests.post(
                        f"{GEMINI_API_URL}?key={GEMINI_API_KEY}",
                        headers=headers,
                        json=payload_second_call,
                    )
                    response_second.raise_for_status()
                    llm_response_data_second = response_second.json()

                    if llm_response_data_second and llm_response_data_second.get(
                        "candidates"
                    ):
                        final_candidate = llm_response_data_second["candidates"][0]
                        if final_candidate.get("content") and final_candidate[
                            "content"
                        ].get("parts"):
                            for part in final_candidate["content"]["parts"]:
                                if part.get("text"):
                                    llm_text += part["text"]

                    if not llm_text:
                        llm_text = "I'm sorry, I couldn't generate a response after using the tool."

                else:
                    llm_text = f"I tried to use a tool called '{tool_name}', but it's not available."
            else:
                # LLM provided a direct text response
                if isinstance(first_part.get("text"), str):
                    llm_text = first_part.get("text")
                elif isinstance(
                    llm_response_data_initial["candidates"][0]["content"]["parts"], list
                ):
                    for p in llm_response_data_initial["candidates"][0]["content"][
                        "parts"
                    ]:
                        if p.get("text"):
                            llm_text += p["text"]

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


if __name__ == "__main__":
    # Run the Flask app
    # In a production environment, use a WSGI server like Gunicorn
    app.run(debug=True, port=5000)
