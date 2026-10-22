
from flask import Flask, request, jsonify, send_from_directory
from pypdf import PdfReader
from werkzeug.utils import secure_filename
from io import BytesIO

app = Flask(__name__)

app.config["MAX_CONTENT_LENGTH"] = 15 * 1024 * 1024

ALLOWED_EXTENSIONS = {"pdf", "txt"}


@app.route("/")
def home():
    return send_from_directory(".", "index.html")


@app.route("/<path:filename>")
def frontend_files(filename):
    if filename in {"style.css", "script.js"}:
        return send_from_directory(".", filename)
    return jsonify({"error": "Not found"}), 404


@app.route("/upload", methods=["POST"])
def upload_document():
    if "document" not in request.files:
        return jsonify({"error": "Please select a file."}), 400

    file = request.files["document"]

    if not file.filename:
        return jsonify({"error": "No file selected."}), 400

    filename = secure_filename(file.filename)
    extension = filename.rsplit(".", 1)[-1].lower() if "." in filename else ""

    if extension not in ALLOWED_EXTENSIONS:
        return jsonify({"error": "Only PDF and TXT files are supported."}), 400

    try:
        if extension == "pdf":
            reader = PdfReader(BytesIO(file.read()))

            if reader.is_encrypted:
                return jsonify({
                    "error": "Password-protected PDFs are not supported."
                }), 400

            text = "\n".join(
                page.extract_text() or "" for page in reader.pages
            )
        else:
            text = file.read().decode("utf-8-sig")

        if not text.strip():
            return jsonify({
                "error": "No readable text found. Scanned PDFs may need OCR."
            }), 400

        app.config["LAST_DOCUMENT_TEXT"] = text[:200000]

        return jsonify({
            "message": "Document uploaded and text extracted successfully!",
            "filename": filename,
            "characters": len(text),
            "preview": text[:500]
        })

    except Exception as e:
        print("Upload error:", e)
        return jsonify({
            "error": "Could not read this document. Please try another file."
        }), 400


@app.errorhandler(413)
def file_too_large(error):
    return jsonify({
        "error": "File size must not exceed 15 MB."
    }), 413


if __name__ == "__main__":
    app.run(debug=True)
