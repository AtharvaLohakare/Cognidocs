
const uploadForm = document.getElementById("upload-form");
const fileInput = document.getElementById("document-input");
const fileInfo = document.getElementById("file-info");
const uploadButton = document.getElementById("upload-button");
const uploadStatus = document.getElementById("upload-status");

const documentPreview = document.getElementById("document-preview");
const documentDetails = document.getElementById("document-details");
const previewText = document.getElementById("preview-text");

const askForm = document.getElementById("ask-form");
const questionInput = document.getElementById("question-input");
const askButton = document.getElementById("ask-button");
const answerStatus = document.getElementById("answer-status");
const answerOutput = document.getElementById("answer-output");
const answerText = document.getElementById("answer-text");

const MAX_FILE_SIZE = 15 * 1024 * 1024;
let documentUploaded = false;

function setStatus(element, message, type = "") {
    element.textContent = message;
    element.className = "status";

    if (type) {
        element.classList.add(type);
    }
}

fileInput.addEventListener("change", () => {
    const file = fileInput.files[0];

    if (!file) {
        fileInfo.textContent = "No file selected.";
        return;
    }

    fileInfo.textContent =
        `${file.name} (${(file.size / (1024 * 1024)).toFixed(2)} MB)`;

    if (file.size > MAX_FILE_SIZE) {
        setStatus(uploadStatus, "File exceeds the 15 MB limit.", "error");
    } else {
        setStatus(uploadStatus, "");
    }
});

uploadForm.addEventListener("submit", async (event) => {
    event.preventDefault();

    const file = fileInput.files[0];

    if (!file) {
        setStatus(uploadStatus, "Please select a PDF or TXT file.", "error");
        return;
    }

    const allowedExtensions = [".pdf", ".txt"];
    const lowerName = file.name.toLowerCase();

    if (!allowedExtensions.some(extension => lowerName.endsWith(extension))) {
        setStatus(uploadStatus, "Only PDF and TXT files are supported.", "error");
        return;
    }

    if (file.size > MAX_FILE_SIZE) {
        setStatus(uploadStatus, "File exceeds the 15 MB limit.", "error");
        return;
    }

    const formData = new FormData();
    formData.append("document", file);

    uploadButton.disabled = true;
    uploadButton.textContent = "Uploading...";
    setStatus(uploadStatus, "Reading your document...");
    documentPreview.classList.add("hidden");
    answerOutput.classList.add("hidden");
    documentUploaded = false;
    askButton.disabled = true;

    try {
        const response = await fetch("/upload", {
            method: "POST",
            body: formData
        });

        const result = await response.json();

        if (!response.ok) {
            throw new Error(result.error || "Upload failed.");
        }

        documentUploaded = true;
        askButton.disabled = false;

        setStatus(
            uploadStatus,
            result.message || "Document uploaded successfully!",
            "success"
        );

        documentDetails.textContent =
            `${result.filename} · ${result.characters.toLocaleString()} characters`;

        previewText.textContent = result.preview || "";
        documentPreview.classList.remove("hidden");

        questionInput.focus();

    } catch (error) {
        setStatus(uploadStatus, error.message, "error");
    } finally {
        uploadButton.disabled = false;
        uploadButton.textContent = "Upload document";
    }
});

askForm.addEventListener("submit", async (event) => {
    event.preventDefault();

    if (!documentUploaded) {
        setStatus(answerStatus, "Upload a document first.", "error");
        return;
    }

    const question = questionInput.value.trim();

    if (!question) {
        setStatus(answerStatus, "Please enter a question.", "error");
        return;
    }

    askButton.disabled = true;
    askButton.textContent = "Thinking...";
    answerOutput.classList.add("hidden");
    setStatus(answerStatus, "Analyzing your document...");

    try {
        const response = await fetch("/ask", {
            method: "POST",
            headers: {
                "Content-Type": "application/json"
            },
            body: JSON.stringify({ question })
        });

        const result = await response.json();

        if (!response.ok) {
            throw new Error(result.error || "Could not get an answer.");
        }

        // textContent prevents returned text from being interpreted as HTML.
        answerText.textContent = result.answer || "No answer was returned.";
        answerOutput.classList.remove("hidden");
        setStatus(answerStatus, "Answer generated successfully.", "success");

    } catch (error) {
        setStatus(answerStatus, error.message, "error");
    } finally {
        askButton.disabled = !documentUploaded;
        askButton.textContent = "Ask DocuMind AI";
    }
});



document.querySelectorAll(".suggestion").forEach((button) => {
    button.addEventListener("click", () => {
        questionInput.value = button.dataset.question;
        questionInput.focus();
    });
});
