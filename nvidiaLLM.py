import logging
import traceback
from flask import Flask, request, jsonify
from openai import OpenAI
from flask_cors import CORS
import pdfplumber
import pytesseract
import os
from dotenv import load_dotenv
import os

# Get the absolute path to the project root .env
dotenv_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', '.env')
load_dotenv(dotenv_path)
pytesseract.pytesseract.tesseract_cmd = os.getenv("TESSERACT_PATH")

logging.basicConfig(level=logging.DEBUG)

app = Flask(__name__)
CORS(app)

# Load API URLs and keys from .env
NVIDIA_API_BASE_URL = os.getenv("NVIDIA_API_BASE_URL")
API_KEY = os.getenv("API_KEY")
# Add any other URLs/keys you want to use from .env here
# For example:
# ANOTHER_SERVICE_URL = os.getenv("ANOTHER_SERVICE_URL")
# ANOTHER_API_KEY = os.getenv("ANOTHER_API_KEY")

@app.route('/summarize', methods=['POST'])
def summarize_file():
    try:
        logging.debug("Request received for /summarize endpoint")
        if 'file' not in request.files:
            logging.error("No file uploaded")
            return jsonify({"error": "No file uploaded"}), 400
        uploaded_file = request.files['file']
        logging.debug("File uploaded: %s", uploaded_file.filename)
        if uploaded_file.filename == '':
            logging.error("No file selected")
            return jsonify({"error": "No file selected"}), 400
        text_data = ""
        if uploaded_file.filename.endswith('.pdf'):
            logging.debug("Processing PDF file")
            try:
                with pdfplumber.open(uploaded_file) as pdf:
                    for page in pdf.pages:
                        page_text = page.extract_text()
                        if page_text:
                            text_data += page_text + "\n"
                        else:
                            logging.debug("No text found, using OCR on the page")
                            page_image = page.to_image(resolution=300)
                            image = page_image.original
                            ocr_text = pytesseract.image_to_string(image)
                            text_data += ocr_text + "\n"
                logging.debug("Text extracted from PDF successfully")
            except Exception as e:
                logging.error("Error extracting text from PDF: %s", str(e))
                return jsonify({"error": "Error extracting text from PDF", "details": str(e)}), 500
            if not text_data.strip():
                logging.error("No text could be extracted from the PDF.")
                return jsonify({"error": "No text could be extracted from the PDF."}), 400
        else:
            logging.debug("Processing plain text file")
            try:
                text_data = uploaded_file.read().decode('utf-8')
                logging.debug("Text extracted from plain text file successfully")
            except Exception as e:
                logging.error("Error reading plain text file: %s", str(e))
                return jsonify({"error": "Error reading plain text file", "details": str(e)}), 500
            if not text_data.strip():
                logging.error("No text found in the uploaded file.")
                return jsonify({"error": "No text found in the uploaded file."}), 400
        custom_prompt = request.form.get('prompt', 'Summarize the content.')
        logging.debug("Custom prompt: %s", custom_prompt)
        client = OpenAI(base_url=NVIDIA_API_BASE_URL, api_key=API_KEY)
        logging.debug("Calling NVIDIA's API")
        try:
            completion = client.chat.completions.create(
                model="nvidia/llama-3.1-nemotron-70b-instruct",
                messages=[
                    {"role": "system", "content": "summarize this but don't make it too short"},
                    {"role": "user", "content": text_data}
                ],
                temperature=0.8,
                top_p=1,
                max_tokens=2048,
                stream=True
            )
            logging.debug("Model response received")
        except Exception as e:
            logging.error("General error while calling NVIDIA API: %s", str(e))
            return jsonify({"error": "An error occurred while calling NVIDIA API", "details": str(e)}), 500

        # Extract the summarized content
        summary = ""
        try:
            for chunk in completion:
                if hasattr(chunk.choices[0].delta, 'content') and chunk.choices[0].delta.content is not None:
                    summary += chunk.choices[0].delta.content
            logging.debug("Summary generated: %s", summary)
        except Exception as e:
            logging.error("Error while extracting summary: %s", str(e))
            return jsonify({"error": "Error while extracting summary", "details": str(e)}), 500

        if not summary.strip():
            logging.error("No summary was generated by the model.")
            return jsonify({"error": "No summary was generated by the model."}), 500

        return jsonify({"summary": summary}), 200

    except Exception as e:
        logging.error("Error occurred: %s", str(e))
        logging.error("Stack trace: %s", traceback.format_exc())  # Print stack trace for debugging
        return jsonify({"error": "An error occurred during summarization", "details": str(e)}), 500

# Run the Flask app
if __name__ == "__main__":
    # Use port from environment for Render compatibility
    port = int(os.environ.get("PORT", 10000))
    app.run(debug=False, host="0.0.0.0", port=port)