
import os
import re
import math
import time

from dotenv import load_dotenv
from django.conf import settings
from django.http import JsonResponse
from django.shortcuts import render
from django.views.decorators.http import require_POST
from pypdf import PdfReader
from google import genai

load_dotenv()

API_KEY = os.getenv("GEMINI_API_KEY", "").strip()
CHAT_MODEL = os.getenv("GEMINI_MODEL", "gemini-3.8-flash").strip()
EMBED_MODEL = os.getenv(
    "GEMINI_EMBEDDING_MODEL", "gemini-embedding-001"
).strip()

client = genai.Client(api_key=API_KEY) if API_KEY else None

# Temporary storage for a single-user hackathon demo.
DOCUMENT = {
    "filename": None,
    "chunks": [],
    "embeddings": [],
}


def home(request):
    return render(request, "index.html")


def make_chunks(page_texts, chunk_size=1200, overlap=180):
    chunks = []

    for page_number, text in page_texts:
        text = re.sub(r"\s+", " ", text).strip()
        start = 0

        while start < len(text):
            end = min(start + chunk_size, len(text))
            snippet = text[start:end].strip()

            if snippet:
                chunks.append({
                    "chunk": len(chunks) + 1,
                    "page": page_number,
                    "text": snippet,
                })

            if end >= len(text):
                break

            start = end - overlap

    return chunks


def embed_texts(texts):
    if not client:
        raise RuntimeError(
            "Gemini API key missing. Add GEMINI_API_KEY to .env."
        )

    vectors = []

    for start in range(0, len(texts), 16):
        batch = texts[start:start + 16]

        result = client.models.embed_content(
            model=EMBED_MODEL,
            contents=batch,
        )

        vectors.extend(
            [list(item.values) for item in result.embeddings or []]
        )

    if len(vectors) != len(texts):
        raise RuntimeError("Embedding API returned incomplete results.")

    return vectors


def cosine_similarity(a, b):
    dot = sum(x * y for x, y in zip(a, b))
    norm_a = math.sqrt(sum(x * x for x in a))
    norm_b = math.sqrt(sum(y * y for y in b))

    if not norm_a or not norm_b:
        return 0.0

    return dot / (norm_a * norm_b)


def retrieve_chunks(question, top_k=5):
    chunks = DOCUMENT["chunks"]

    if not chunks:
        return []

    query_vector = embed_texts([question])[0]

    ranked = []

    for chunk, vector in zip(chunks, DOCUMENT["embeddings"]):
        score = cosine_similarity(query_vector, vector)
        ranked.append((score, chunk))

    ranked.sort(key=lambda item: item[0], reverse=True)

    return [chunk for score, chunk in ranked[:top_k]]


def generate_answer(prompt):
    if not client:
        raise RuntimeError("Gemini API key is missing from .env.")

    last_error = None

    for attempt in range(3):
        try:
            response = client.models.generate_content(
                model=CHAT_MODEL,
                contents=prompt,
            )

            answer = (response.text or "").strip()

            if not answer:
                raise RuntimeError("Gemini returned an empty response.")

            return answer

        except Exception as exc:
            last_error = exc
            message = str(exc).lower()

            retryable = any(
                term in message
                for term in (
                    "429", "503", "504", "overload",
                    "temporarily", "timeout"
                )
            )

            if not retryable or attempt == 2:
                break

            time.sleep(attempt + 1)

    raise RuntimeError(f"Gemini API error: {last_error}")


def error_response(exc, status=500):
    print("DocuMind error:", repr(exc))
    return JsonResponse({"error": str(exc)}, status=status)


@require_POST
def upload(request):
    uploaded = request.FILES.get("file")

    if not uploaded:
        return JsonResponse(
            {"error": "Choose a PDF or TXT file first."},
            status=400,
        )

    filename = uploaded.name

    if not filename.lower().endswith((".pdf", ".txt")):
        return JsonResponse(
            {"error": "Only PDF and TXT files are supported."},
            status=400,
        )

    if uploaded.size > 15 * 1024 * 1024:
        return JsonResponse(
            {"error": "Maximum file size is 15 MB."},
            status=413,
        )

    try:
        page_texts = []

        if filename.lower().endswith(".pdf"):
            reader = PdfReader(uploaded)

            for page_number, page in enumerate(reader.pages, start=1):
                text = (page.extract_text() or "").strip()

                if text:
                    page_texts.append((page_number, text))

        else:
            raw = uploaded.read()

            try:
                text = raw.decode("utf-8-sig")
            except UnicodeDecodeError:
                text = raw.decode("latin-1")

            if text.strip():
                page_texts.append((None, text))

        if not page_texts:
            return JsonResponse(
                {
                    "error": (
                        "No readable text was found. "
                        "Scanned PDFs require OCR."
                    )
                },
                status=400,
            )

        chunks = make_chunks(page_texts)

        if not chunks:
            return JsonResponse(
                {"error": "No document text could be processed."},
                status=400,
            )

        # Do not replace the current document until indexing succeeds.
        embeddings = embed_texts([c["text"] for c in chunks])

        DOCUMENT.update({
            "filename": filename,
            "chunks": chunks,
            "embeddings": embeddings,
        })

        return JsonResponse({
            "message": "Document uploaded and indexed successfully.",
            "filename": filename,
            "chunks": len(chunks),
            "characters": sum(len(c["text"]) for c in chunks),
            "preview": chunks[0]["text"][:500],
        })

    except Exception as exc:
        return error_response(exc)


@require_POST
def ask(request):
    import json

    try:
        data = json.loads(request.body or b"{}")
    except (ValueError, UnicodeDecodeError):
        return JsonResponse({"error": "Invalid JSON request."}, status=400)

    question = (data.get("question") or "").strip()

    if not question:
        return JsonResponse(
            {"error": "Enter a question first."}, status=400
        )

    if not DOCUMENT["chunks"]:
        return JsonResponse(
            {"error": "Upload a document before asking questions."},
            status=400,
        )

    try:
        sources = retrieve_chunks(question)

        if not sources:
            return JsonResponse({
                "answer": (
                    "I couldn't find enough information in the "
                    "uploaded document to answer that question."
                ),
                "filename": DOCUMENT["filename"],
                "sources": [],
                "grounded": False,
            })

        context = "\n\n".join(
            f"[Chunk {c['chunk']}; page "
            f"{c['page'] if c['page'] is not None else 'N/A'}]\n"
            f"{c['text']}"
            for c in sources
        )

        prompt = f"""
You are DocuMind AI, a document question-answering assistant.

Answer using ONLY the source passages below.
Do not use outside knowledge or invent facts.
If the passages do not contain enough evidence, state:
"I couldn't find this information in the uploaded document."

Be concise. Do not invent citations or page numbers.

SOURCE PASSAGES:
{context}

QUESTION:
{question}

ANSWER:
"""

        answer = generate_answer(prompt)

        not_found = (
            "couldn't find this information in the uploaded document"
            in answer.lower()
        )

        return JsonResponse({
            "answer": answer,
            "filename": DOCUMENT["filename"],
            "grounded": not not_found,
            "sources": [
                {
                    "chunk": c["chunk"],
                    "page": c["page"],
                    "text": c["text"],
                }
                for c in sources
            ],
        })

    except Exception as exc:
        return error_response(exc)


@require_POST
def summarize(request):
    if not DOCUMENT["chunks"]:
        return JsonResponse(
            {"error": "Upload a document before summarizing."},
            status=400,
        )

    try:
        partial_summaries = []

        for start in range(0, len(DOCUMENT["chunks"]), 5):
            batch = DOCUMENT["chunks"][start:start + 5]
            text = "\n\n".join(c["text"] for c in batch)

            partial_summaries.append(
                generate_answer(
                    "Summarize these document passages faithfully. "
                    "Preserve key findings, facts, names, and numbers. "
                    "Do not add unsupported information.\n\n" + text
                )
            )

        if len(partial_summaries) == 1:
            summary = partial_summaries[0]
        else:
            summary = generate_answer(
                "Combine these partial summaries into one clear, "
                "structured summary. Remove repetition and do not add "
                "unsupported facts.\n\n"
                + "\n\n".join(partial_summaries)
            )

        return JsonResponse({
            "summary": summary,
            "filename": DOCUMENT["filename"],
        })

    except Exception as exc:
        return error_response(exc)


def health(request):
    return JsonResponse({
        "ok": True,
        "api_key_configured": bool(API_KEY),
        "model": CHAT_MODEL,
    })
