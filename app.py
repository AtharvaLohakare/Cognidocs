
import os
from pathlib import Path

from flask import Flask, request, jsonify, render_template
from flask_cors import CORS
from dotenv import load_dotenv
from pypdf import PdfReader
from google import genai

load_dotenv()

app = Flask(__name__)
CORS(app)

app.config["MAX_CONTENT_LENGTH"] = 15 * 1024 * 1024
app.config["LAST_DOCUMENT_TEXT"] = ""
app.config["LAST_FILENAME"] = ""

api_key = os.getenv("GEMINI_API_KEY")
client = genai.Client(api_key=api_key) if api_key else None


@app.route("/")
def home():
    return render_template("index.html")


def extract_text(file):
    filename = file.filename.lower()

    if filename.endswith(".pdf"):
        reader = PdfReader(file)
        pages = []

        for page in reader.pages:
            pages.append(page.extract_text() or "")

        return "\n".join(pages)

    if filename.endswith(".txt"):
        return file.read().decode("utf-8", errors="replace")

    raise ValueError("Only PDF and TXT files are supported.")


@app.route("/upload", methods=["POST"])
def upload_document():
    if "document" not in request.files:
        return jsonify({"error": "Please select a document."}), 400

    file = request.files["document"]

    if not file.filename:
        return jsonify({"error": "No file was selected."}), 400

    try:
        text = extract_text(file)

        if not text.strip():
            return jsonify({
                "error": "No readable text was found. If this is a scanned PDF, use OCR first."
            }), 400

        app.config["LAST_DOCUMENT_TEXT"] = text
        app.config["LAST_FILENAME"] = file.filename

        return jsonify({
            "message": "Document uploaded successfully!",
            "filename": file.filename,
            "characters": len(text),
            "preview": text[:500]
        })

    except ValueError as error:
        return jsonify({"error": str(error)}), 400

    except Exception as error:
        app.logger.exception("Document upload failed")
        return jsonify({
            "error": "Could not read the document. Please check that the file is valid."
        }), 400


@app.route("/ask", methods=["POST"])
def ask_question():
    if not client:
        return jsonify({
            "error": "Gemini API key is missing. Add GEMINI_API_KEY to your .env file."
        }), 500

    document_text = app.config["LAST_DOCUMENT_TEXT"]

    if not document_text:
        return jsonify({
            "error": "Upload a document before asking a question."
        }), 400

    data = request.get_json(silent=True) or {}
    question = data.get("question", "").strip()

    if not question:
        return jsonify({"error": "Please enter a question."}), 400

    prompt = f"""
You are DocuMind AI, an assistant that answers questions about documents.

Answer the user's question using the document provided below.
If the answer is not present in the document, clearly say that you could not
find the answer in the uploaded document. Do not invent facts.
Give a clear, helpful answer.

DOCUMENT:
{document_text}

USER QUESTION:
{question}
"""

    try:
        response = client.models.generate_content(
            model="gemini-3.8-flash",
            contents=prompt
        )

        answer = response.text or "No answer was returned."

        return jsonify({
            "answer": answer,
            "filename": app.config["LAST_FILENAME"]
        })

    except Exception:
        app.logger.exception("Gemini request failed")
        return jsonify({
            "error": "The AI request failed. Check your API key, model availability, internet connection, and server terminal."
        }), 500


@app.errorhandler(413)
def file_too_large(error):
    return jsonify({
        "error": "File is too large. Maximum allowed size is 15 MB."
    }), 413


if __name__ == "__main__":
    app.run(debug=True)
