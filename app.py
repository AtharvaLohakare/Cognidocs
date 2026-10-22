
import os
import time
import math
from pathlib import Path

from flask import Flask, request, jsonify, render_template
from flask_cors import CORS
from dotenv import load_dotenv
from pypdf import PdfReader
from google import genai


# --------------------------------------------------
# CONFIGURATION
# --------------------------------------------------

load_dotenv()

app = Flask(__name__)
CORS(app)

app.config["MAX_CONTENT_LENGTH"] = 15 * 1024 * 1024

GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")

# Override these in .env if your API key uses different models.
GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-3.8-flash")
EMBEDDING_MODEL = os.getenv(
    "EMBEDDING_MODEL", "gemini-embedding-001"
)

client = genai.Client(api_key=GEMINI_API_KEY) if GEMINI_API_KEY else None

# Document state for this single-user/demo application.
app.config["LAST_DOCUMENT_TEXT"] = ""
app.config["LAST_FILENAME"] = ""
app.config["DOCUMENT_CHUNKS"] = []
app.config["DOCUMENT_EMBEDDINGS"] = []


# --------------------------------------------------
# TEXT EXTRACTION
# --------------------------------------------------

def extract_text(file):
    """Extract text from a PDF or TXT upload."""
    filename = file.filename or ""
    extension = Path(filename).suffix.lower()

    if extension == ".pdf":
        reader = PdfReader(file.stream)
        pages = []

        for page in reader.pages:
            pages.append(page.extract_text() or "")

        text = "\n".join(pages)

    elif extension == ".txt":
        text = file.stream.read().decode("utf-8-sig", errors="replace")

    else:
        raise ValueError("Only PDF and TXT files are supported.")

    text = text.strip()

    if not text:
        raise ValueError(
            "No readable text was found. If this is a scanned PDF, "
            "OCR may be required."
        )

    return text


# --------------------------------------------------
# CHUNKING
# --------------------------------------------------

def split_into_chunks(text, chunk_size=1200, overlap=200):
    """
    Split text into overlapping character chunks.
    Overlap helps preserve context between adjacent chunks.
    """
    if chunk_size <= 0 or overlap < 0 or overlap >= chunk_size:
        raise ValueError("Invalid chunk size or overlap.")

    text = text.strip()
    chunks = []
    start = 0

    while start < len(text):
        end = min(start + chunk_size, len(text))

        # Prefer ending at a nearby word boundary.
        if end < len(text):
            boundary = text.rfind(" ", start + chunk_size // 2, end)
            if boundary > start:
                end = boundary

        chunk = text[start:end].strip()

        if chunk:
            chunks.append(chunk)

        if end >= len(text):
            break

        start = max(end - overlap, start + 1)

    return chunks


# --------------------------------------------------
# HOSTED EMBEDDINGS
# --------------------------------------------------

def create_embeddings(texts):
    """
    Convert text into vectors using Gemini's hosted embedding API.
    No local PyTorch or vector database is needed.
    """
    if not client:
        raise RuntimeError(
            "GEMINI_API_KEY is missing. Add it to your .env file."
        )

    vectors = []

    # Small batches keep requests manageable.
    for start in range(0, len(texts), 16):
        batch = texts[start:start + 16]

        response = client.models.embed_content(
            model=EMBEDDING_MODEL,
            contents=batch,
        )

        embeddings = getattr(response, "embeddings", None)

        if not embeddings or len(embeddings) != len(batch):
            raise RuntimeError(
                "The embedding API returned an unexpected response."
            )

        for item in embeddings:
            vector = list(item.values)

            if not vector:
                raise RuntimeError("An empty embedding was returned.")

            vectors.append(vector)

    return vectors


# --------------------------------------------------
# SEMANTIC SIMILARITY SEARCH
# --------------------------------------------------

def cosine_similarity(vector_a, vector_b):
    """Calculate cosine similarity without NumPy."""
    if len(vector_a) != len(vector_b):
        raise ValueError("Embedding dimensions do not match.")

    dot_product = sum(a * b for a, b in zip(vector_a, vector_b))
    norm_a = math.sqrt(sum(a * a for a in vector_a))
    norm_b = math.sqrt(sum(b * b for b in vector_b))

    if norm_a == 0 or norm_b == 0:
        return 0.0

    return dot_product / (norm_a * norm_b)


def retrieve_relevant_chunks(question, top_k=5):
    """
    Embed the user's question and return the most relevant
    document chunks based on cosine similarity.
    """
    chunks = app.config["DOCUMENT_CHUNKS"]
    document_vectors = app.config["DOCUMENT_EMBEDDINGS"]

    if not chunks or not document_vectors:
        return []

    question_vector = create_embeddings([question])[0]
    scored_chunks = []

    for chunk, vector in zip(chunks, document_vectors):
        score = cosine_similarity(question_vector, vector)
        scored_chunks.append((score, chunk))

    scored_chunks.sort(key=lambda item: item[0], reverse=True)

    return [
        {"score": score, "text": chunk}
        for score, chunk in scored_chunks[:top_k]
    ]


# --------------------------------------------------
# GEMINI GENERATION WITH RETRIES
# --------------------------------------------------

def generate_ai_response(prompt, max_attempts=3):
    if not client:
        raise RuntimeError(
            "GEMINI_API_KEY is missing. Add it to your .env file."
        )

    for attempt in range(max_attempts):
        try:
            response = client.models.generate_content(
                model=GEMINI_MODEL,
                contents=prompt,
            )

            answer = getattr(response, "text", None)

            if not answer:
                raise RuntimeError(
                    "Gemini returned an empty response. Please try again."
                )

            return answer.strip()

        except Exception as exc:
            error_text = str(exc).lower()

            temporary_error = any(
                marker in error_text
                for marker in (
                    "429",
                    "500",
                    "502",
                    "503",
                    "504",
                    "unavailable",
                    "overloaded",
                    "resource_exhausted",
                    "deadline",
                    "timed out",
                    "timeout",
                )
            )

            if not temporary_error or attempt == max_attempts - 1:
                raise

            time.sleep(2 ** attempt)

    raise RuntimeError("The AI request failed. Please try again.")


# --------------------------------------------------
# ROUTES: HOME
# --------------------------------------------------

@app.route("/")
def home():
    return render_template("index.html")


# --------------------------------------------------
# ROUTE: UPLOAD DOCUMENT
# --------------------------------------------------

@app.route("/upload", methods=["POST"])
def upload_document():
    if "file" not in request.files:
        return jsonify({"error": "Please select a file to upload."}), 400

    file = request.files["file"]

    if not file.filename:
        return jsonify({"error": "No file was selected."}), 400

    try:
        # Extract and split the document.
        document_text = extract_text(file)
        chunks = split_into_chunks(document_text)

        # Calculate embeddings once during upload.
        # Questions can then search the saved vectors.
        embeddings = create_embeddings(chunks)

        # Store results for subsequent /ask and /summarize requests.
        app.config["LAST_DOCUMENT_TEXT"] = document_text
        app.config["LAST_FILENAME"] = Path(file.filename).name
        app.config["DOCUMENT_CHUNKS"] = chunks
        app.config["DOCUMENT_EMBEDDINGS"] = embeddings

        preview = document_text[:500]

        return jsonify({
            "message": "Document uploaded and indexed successfully.",
            "filename": Path(file.filename).name,
            "characters": len(document_text),
            "preview": preview,
            "chunks": len(chunks),
        })

    except ValueError as exc:
        return jsonify({"error": str(exc)}), 400

    except Exception as exc:
        app.logger.exception("Document upload/indexing failed")

        return jsonify({
            "error": (
                "Could not process the document or create embeddings. "
                "Check your API key, model access, internet connection, "
                "and Gemini API limits, then try again."
            ),
            "details": str(exc)[:500],
        }), 500


# --------------------------------------------------
# ROUTE: ASK A QUESTION
# --------------------------------------------------

@app.route("/ask", methods=["POST"])
def ask_question():
    data = request.get_json(silent=True) or {}
    question = str(data.get("question", "")).strip()

    if not question:
        return jsonify({"error": "Please enter a question."}), 400

    if not app.config["LAST_DOCUMENT_TEXT"]:
        return jsonify({
            "error": "Please upload a document first."
        }), 400

    try:
        # Retrieve only the most relevant document passages.
        relevant_chunks = retrieve_relevant_chunks(question, top_k=5)

        if not relevant_chunks:
            return jsonify({
                "error": "No relevant document text was found."
            }), 400

        context = "\n\n".join(
            f"[Passage {index + 1}]\n{item['text']}"
            for index, item in enumerate(relevant_chunks)
        )

        prompt = f"""
You are DocuMind AI, a helpful document analysis assistant.

Answer the user's question using the document passages below.

Rules:
- Ground factual answers in the supplied passages.
- Do not invent information that is absent from the passages.
- If the passages do not contain the answer, say so clearly.
- Explain the answer in simple, useful language.
- Use bullet points when they improve readability.

DOCUMENT PASSAGES:
{context}

USER QUESTION:
{question}

ANSWER:
"""

        answer = generate_ai_response(prompt)

        return jsonify({
            "answer": answer,
            "filename": app.config["LAST_FILENAME"],
        })

    except Exception as exc:
        app.logger.exception("Question answering failed")

        return jsonify({
            "error": (
                "Could not generate an answer. Check your Gemini "
                "API key, model access, API limits, and connection."
            ),
            "details": str(exc)[:500],
        }), 500


# --------------------------------------------------
# ROUTE: SUMMARIZE DOCUMENT
# --------------------------------------------------

@app.route("/summarize", methods=["POST"])
def summarize_document():
    document_text = app.config["LAST_DOCUMENT_TEXT"]
    chunks = app.config["DOCUMENT_CHUNKS"]

    if not document_text or not chunks:
        return jsonify({
            "error": "Please upload a document first."
        }), 400

    try:
        # Summarize in batches so a long document is less likely
        # to exceed the model's input limit.
        partial_summaries = []
        batch_size = 5

        for start in range(0, len(chunks), batch_size):
            batch = chunks[start:start + batch_size]
            batch_text = "\n\n".join(batch)

            prompt = f"""
Summarize the following passages from a document.

Keep the main ideas, important facts, dates, names, conclusions,
and actionable points. Do not invent details.

PASSAGES:
{batch_text}

SUMMARY:
"""
            partial_summaries.append(generate_ai_response(prompt))

        if len(partial_summaries) == 1:
            summary = partial_summaries[0]
        else:
            combined = "\n\n".join(
                f"Section {i + 1}:\n{item}"
                for i, item in enumerate(partial_summaries)
            )

            summary = generate_ai_response(f"""
Create one coherent summary of this document using the section
summaries below. Preserve important facts and conclusions.
Remove repetition. Do not add unsupported information.

SECTION SUMMARIES:
{combined}

FINAL DOCUMENT SUMMARY:
""")

        return jsonify({
            "summary": summary,
            "filename": app.config["LAST_FILENAME"],
        })

    except Exception as exc:
        app.logger.exception("Document summarization failed")

        return jsonify({
            "error": (
                "Could not summarize the document. Check your Gemini "
                "API key, model access, API limits, and connection."
            ),
            "details": str(exc)[:500],
        }), 500


# --------------------------------------------------
# ERROR HANDLERS
# --------------------------------------------------

@app.errorhandler(413)
def file_too_large(_error):
    return jsonify({
        "error": "File is too large. Maximum upload size is 15 MB."
    }), 413


if __name__ == "__main__":
    app.run(debug=True)
