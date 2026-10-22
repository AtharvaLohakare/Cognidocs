
const fileInput = document.getElementById("document-input");
const fileInfo = document.getElementById("file-info");
const uploadCard = document.querySelector(".upload-card");

const MAX_FILE_SIZE = 15 * 1024 * 1024;

function showMessage(message, type = "") {
    let status = document.getElementById("upload-status");

    if (!status) {
        status = document.createElement("p");
        status.id = "upload-status";
        fileInfo.insertAdjacentElement("afterend", status);
    }

    status.className = `status-message ${type}`;
    status.textContent = message;
}

async function uploadFile(file) {
    if (!file) return;

    const extension = file.name.split(".").pop().toLowerCase();

    if (!["pdf", "txt"].includes(extension)) {
        showMessage("Choose a PDF or TXT file.", "error");
        return;
    }

    if (file.size > MAX_FILE_SIZE) {
        showMessage("File must be smaller than 15 MB.", "error");
        return;
    }

    fileInfo.textContent =
        `${file.name} (${(file.size / 1024).toFixed(1)} KB)`;

    showMessage("Uploading and extracting text...", "");

    const formData = new FormData();
    formData.append("document", file);

    try {
        const response = await fetch("/upload", {
            method: "POST",
            body: formData
        });

        const responseText = await response.text();

        let result;
        try {
            result = JSON.parse(responseText);
        } catch {
            throw new Error(
                `Server returned status ${response.status}. Check the Flask terminal.`
            );
        }

        if (!response.ok) {
            throw new Error(result.error || "Upload failed.");
        }

        showMessage(
            `${result.message} Extracted ${result.characters} characters.`,
            "success"
        );

        console.log("Extracted text preview:", result.preview);

    } catch (error) {
        showMessage(error.message, "error");
        console.error("Upload error:", error);
    }
}

fileInput.addEventListener("change", () => {
    uploadFile(fileInput.files[0]);
});

uploadCard.addEventListener("dragover", event => {
    event.preventDefault();
    uploadCard.classList.add("drag-active");
});

uploadCard.addEventListener("dragleave", event => {
    if (!uploadCard.contains(event.relatedTarget)) {
        uploadCard.classList.remove("drag-active");
    }
});

uploadCard.addEventListener("drop", event => {
    event.preventDefault();
    uploadCard.classList.remove("drag-active");

    const file = event.dataTransfer.files[0];
    if (file) uploadFile(file);
});

document.querySelectorAll('a[href^="#"]').forEach(link => {
    link.addEventListener("click", event => {
        const target = document.querySelector(link.getAttribute("href"));

        if (target) {
            event.preventDefault();
            target.scrollIntoView({ behavior: "smooth" });
        }
    });
});
