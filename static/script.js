
const $ = (id) => document.getElementById(id);

let documentReady = false;

function csrfToken() {
    return document.querySelector(
        '#upload-form input[name="csrfmiddlewaretoken"]'
    )?.value || "";
}

async function postData(url, payload, json = false) {
    const headers = { "X-CSRFToken": csrfToken() };
    let body = payload;

    if (json) {
        headers["Content-Type"] = "application/json";
        body = JSON.stringify(payload);
    }

    const response = await fetch(url, {
        method: "POST",
        headers,
        body,
        credentials: "same-origin"
    });

    let data;
    try {
        data = await response.json();
    } catch {
        throw new Error("The server returned an unexpected response.");
    }

    if (!response.ok) {
        throw new Error(data.error || data.message || `Request failed (${response.status}).`);
    }

    return data;
}

function setStatus(id, message, isError = false) {
    const element = $(id);
    if (!element) return;
    element.textContent = message;
    element.style.color = isError ? "#b42318" : "";
}

function show(element, visible = true) {
    if (element) element.classList.toggle("hidden", !visible);
}

function setDocumentReady(ready) {
    documentReady = ready;
    if ($("ask-button")) $("ask-button").disabled = !ready;
    if ($("summarize-button")) $("summarize-button").disabled = !ready;
}

function addText(parent, tag, text, className = "") {
    const element = document.createElement(tag);
    element.textContent = text || "";
    if (className) element.className = className;
    parent.appendChild(element);
    return element;
}

// Display the selected filename before upload.
$("document-input")?.addEventListener("change", (event) => {
    const file = event.target.files[0];
    $("file-info").textContent = file
        ? `${file.name} (${(file.size / (1024 * 1024)).toFixed(2)} MB)`
        : "No file selected.";
});

// Upload a PDF or TXT file.
$("upload-form")?.addEventListener("submit", async (event) => {
    event.preventDefault();

    const file = $("document-input")?.files[0];
    if (!file) {
        setStatus("upload-status", "Please choose a PDF or TXT file.", true);
        return;
    }

    if (file.size > 15 * 1024 * 1024) {
        setStatus("upload-status", "The file must be smaller than 15 MB.", true);
        return;
    }

    const extension = file.name.split(".").pop().toLowerCase();
    if (!["pdf", "txt"].includes(extension)) {
        setStatus("upload-status", "Only PDF and TXT files are supported.", true);
        return;
    }

    const button = $("upload-button");
    button.disabled = true;
    button.textContent = "Processing document...";
    setStatus("upload-status", "Uploading and indexing your document...");
    setDocumentReady(false);

    try {
        const formData = new FormData(event.currentTarget);
        // Ensure the backend receives the expected field name.
        formData.set("file", file);

        const data = await postData("/upload", formData);

        setDocumentReady(true);
        setStatus(
            "upload-status",
            `Uploaded successfully: ${data.filename || file.name}`
        );

        $("document-details").textContent =
            `${data.filename || file.name} · ` +
            `${data.chunks ?? "?"} chunks · ` +
            `${data.characters ?? "?"} characters`;

        $("preview-text").textContent = data.preview || "Document processed and ready for questions.";
        show($("document-preview"));
        show($("answer-output"), false);
        show($("summary-output"), false);
        setStatus("answer-status", "");
        setStatus("summary-status", "");
    } catch (error) {
        setStatus("upload-status", error.message, true);
    } finally {
        button.disabled = false;
        button.textContent = "Upload Document →";
    }
});

// Fill the question box when a suggested question is clicked.
document.querySelectorAll("[data-question]").forEach((button) => {
    button.addEventListener("click", () => {
        $("question-input").value = button.dataset.question;
        $("question-input").focus();
    });
});

// Ask a question and display its answer plus source references.
$("ask-form")?.addEventListener("submit", async (event) => {
    event.preventDefault();

    if (!documentReady) {
        setStatus("answer-status", "Upload a document first.", true);
        return;
    }

    const question = $("question-input").value.trim();
    if (!question) {
        setStatus("answer-status", "Enter a question first.", true);
        return;
    }

    const button = $("ask-button");
    button.disabled = true;
    button.textContent = "Thinking...";
    setStatus("answer-status", "Searching your document for relevant passages...");
    show($("answer-output"), false);

    try {
        const data = await postData("/ask", { question }, true);

        $("answer-text").textContent = data.answer || "No answer was returned.";
        const sources = $("sources-list");
        sources.replaceChildren();

        if (Array.isArray(data.sources) && data.sources.length) {
            addText(sources, "h4", "Sources from your document");

            data.sources.forEach((source, index) => {
                const card = document.createElement("div");
                card.className = "source-reference";

                const page = source.page != null ? ` · Page ${source.page}` : "";
                addText(card, "strong", `Source ${index + 1}${page}`);
                addText(card, "p", source.text || source.content || "");
                sources.appendChild(card);
            });
        } else {
            addText(sources, "p", "No source passages were returned.");
        }

        show($("answer-output"));
        setStatus("answer-status", data.grounded === false
            ? "The answer may not be fully supported by the document."
            : "Answer generated.");
    } catch (error) {
        setStatus("answer-status", error.message, true);
    } finally {
        button.disabled = !documentReady;
        button.textContent = "✦ Ask DocuMind AI";
    }
});

// Summarize the uploaded document.
$("summarize-button")?.addEventListener("click", async () => {
    if (!documentReady) {
        setStatus("summary-status", "Upload a document first.", true);
        return;
    }

    const button = $("summarize-button");
    button.disabled = true;
    button.textContent = "Summarizing...";
    setStatus("summary-status", "Generating your summary...");
    show($("summary-output"), false);

    try {
        const data = await postData("/summarize", {}, true);
        $("summary-text").textContent =
            data.summary || data.error || "No summary was returned.";
        show($("summary-output"));
        setStatus("summary-status", "Summary ready.");
    } catch (error) {
        setStatus("summary-status", error.message, true);
    } finally {
        button.disabled = !documentReady;
        button.textContent = "✦ Summarize Document";
    }
});

// Copy the generated summary.
$("copy-summary-button")?.addEventListener("click", async () => {
    const summary = $("summary-text")?.textContent || "";
    if (!summary) return;

    try {
        await navigator.clipboard.writeText(summary);
        setStatus("summary-status", "Summary copied to clipboard.");
    } catch {
        setStatus("summary-status", "Could not copy automatically. Select the summary text and copy it manually.", true);
    }
});
