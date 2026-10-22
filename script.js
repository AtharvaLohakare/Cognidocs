
const fileInput = document.getElementById("document-input");
const fileInfo = document.getElementById("file-info");
const uploadCard = document.querySelector(".upload-card");

const MAX_FILE_SIZE = 15 * 1024 * 1024; // 15 MB

// Show selected file information
fileInput.addEventListener("change", function () {
    const file = fileInput.files[0];

    if (!file) {
        fileInfo.textContent = "No file selected";
        return;
    }

    const extension = file.name.split(".").pop().toLowerCase();

    // Check supported file formats
    if (!["pdf", "txt"].includes(extension)) {
        showMessage("Please select a PDF or TXT file.", "error");
        fileInput.value = "";
        return;
    }

    // Check file size
    if (file.size > MAX_FILE_SIZE) {
        showMessage("File size must be less than 15 MB.", "error");
        fileInput.value = "";
        return;
    }

    const sizeInKB = (file.size / 1024).toFixed(2);

    fileInfo.textContent =
        `Selected: ${file.name} (${sizeInKB} KB)`;

    showMessage(
        "File selected successfully. AI processing will be added next.",
        "success"
    );
});

// Display status messages
function showMessage(message, type) {
    let status = document.getElementById("upload-status");

    if (!status) {
        status = document.createElement("p");
        status.id = "upload-status";
        status.className = "status-message";

        fileInfo.insertAdjacentElement("afterend", status);
    }

    status.textContent = message;
    status.className = `status-message ${type}`;
}

// Drag and drop support
uploadCard.addEventListener("dragover", function (event) {
    event.preventDefault();
    uploadCard.classList.add("drag-active");
});

uploadCard.addEventListener("dragleave", function (event) {
    if (!uploadCard.contains(event.relatedTarget)) {
        uploadCard.classList.remove("drag-active");
    }
});

uploadCard.addEventListener("drop", function (event) {
    event.preventDefault();
    uploadCard.classList.remove("drag-active");

    const file = event.dataTransfer.files[0];

    if (!file) return;

    // Assign the dropped file to the input
    const transfer = new DataTransfer();
    transfer.items.add(file);
    fileInput.files = transfer.files;

    // Run the same validation as a normal selection
    fileInput.dispatchEvent(new Event("change"));
});

// Smooth scrolling for section links
document.querySelectorAll('a[href^="#"]').forEach(function (link) {
    link.addEventListener("click", function (event) {
        const targetId = link.getAttribute("href");
        const target = document.querySelector(targetId);

        if (target) {
            event.preventDefault();
            target.scrollIntoView({
                behavior: "smooth",
                block: "start"
            });
        }
    });
});
