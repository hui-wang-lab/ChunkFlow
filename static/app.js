(() => {
    "use strict";

    const $ = (sel) => document.querySelector(sel);
    const dropZone = $("#dropZone");
    const fileInput = $("#fileInput");
    const parseBtn = $("#parseBtn");
    const fileInfo = $("#fileInfo");
    const fileName = $("#fileName");
    const fileSize = $("#fileSize");
    const clearFile = $("#clearFile");
    const loading = $("#loading");
    const errorMsg = $("#errorMsg");
    const results = $("#results");
    const chunkList = $("#chunkList");
    const searchInput = $("#searchInput");
    const exportBtn = $("#exportBtn");
    const parserBadge = $("#parserBadge");

    let selectedFile = null;
    let lastResult = null;

    // --- Init: fetch parser status ---
    fetch("/api/status")
        .then((r) => r.json())
        .then((data) => {
            parserBadge.textContent = data.parser === "docling" ? "Docling" : "PyPDF";
            parserBadge.className = "badge " + data.parser;
        })
        .catch(() => {
            parserBadge.textContent = "offline";
        });

    // --- File selection ---
    dropZone.addEventListener("click", () => fileInput.click());

    dropZone.addEventListener("dragover", (e) => {
        e.preventDefault();
        dropZone.classList.add("dragover");
    });

    dropZone.addEventListener("dragleave", () => {
        dropZone.classList.remove("dragover");
    });

    dropZone.addEventListener("drop", (e) => {
        e.preventDefault();
        dropZone.classList.remove("dragover");
        const files = e.dataTransfer.files;
        if (files.length > 0) selectFile(files[0]);
    });

    fileInput.addEventListener("change", () => {
        if (fileInput.files.length > 0) selectFile(fileInput.files[0]);
    });

    clearFile.addEventListener("click", () => {
        selectedFile = null;
        fileInput.value = "";
        fileInfo.hidden = true;
        parseBtn.disabled = true;
    });

    function selectFile(file) {
        if (!file.name.toLowerCase().endsWith(".pdf")) {
            showError("请选择 PDF 文件");
            return;
        }
        selectedFile = file;
        fileName.textContent = file.name;
        fileSize.textContent = formatSize(file.size);
        fileInfo.hidden = false;
        parseBtn.disabled = false;
        hideError();
    }

    // --- Parse ---
    parseBtn.addEventListener("click", async () => {
        if (!selectedFile) return;
        hideError();
        results.hidden = true;
        loading.hidden = false;
        parseBtn.disabled = true;

        const formData = new FormData();
        formData.append("file", selectedFile);

        const maxTokens = $("#maxTokens").value;
        const chunkSize = $("#chunkSize").value;
        const overlap = $("#overlap").value;
        const minChunkTokens = $("#minChunkTokens").value;

        const params = new URLSearchParams({
            max_tokens: maxTokens,
            chunk_size_tokens: chunkSize,
            overlap_tokens: overlap,
            min_chunk_tokens: minChunkTokens,
        });

        try {
            const resp = await fetch(`/api/parse?${params}`, {
                method: "POST",
                body: formData,
            });

            if (!resp.ok) {
                const err = await resp.json().catch(() => ({ detail: resp.statusText }));
                throw new Error(err.detail || `HTTP ${resp.status}`);
            }

            lastResult = await resp.json();
            renderResults(lastResult);
        } catch (e) {
            showError(`解析失败: ${e.message}`);
        } finally {
            loading.hidden = true;
            parseBtn.disabled = false;
        }
    });

    // --- Render results ---
    function renderResults(data) {
        results.hidden = false;
        $("#statChunks").textContent = data.chunk_count;
        $("#statParser").textContent = data.parser_used === "docling" ? "Docling" : "PyPDF";
        $("#statSize").textContent = formatSize(data.file_size_bytes);

        searchInput.value = "";
        renderChunks(data.chunks, "");
    }

    function renderChunks(chunks, query) {
        chunkList.innerHTML = "";

        const filtered = query
            ? chunks.filter((c) =>
                c.text.toLowerCase().includes(query.toLowerCase())
            )
            : chunks;

        if (filtered.length === 0) {
            chunkList.innerHTML = `<div style="text-align:center;padding:32px;color:var(--text-muted)">
                ${query ? "没有匹配的 chunk" : "未生成任何 chunk"}
            </div>`;
            return;
        }

        const fragment = document.createDocumentFragment();
        filtered.forEach((chunk) => {
            fragment.appendChild(createChunkCard(chunk, query));
        });
        chunkList.appendChild(fragment);
    }

    function createChunkCard(chunk, query) {
        const card = document.createElement("div");
        card.className = "chunk-card";

        // Header
        const header = document.createElement("div");
        header.className = "chunk-card-header";

        header.innerHTML = `<span class="chunk-index">#${chunk.chunk_index}</span>`;
        header.innerHTML += `<span class="chunk-page">Page ${chunk.page_number}</span>`;

        if (chunk.chapter) {
            header.innerHTML += `<span class="chunk-meta-tag tag-chapter">${esc(chunk.chapter)}</span>`;
        }
        if (chunk.section) {
            header.innerHTML += `<span class="chunk-meta-tag tag-section">${esc(chunk.section)}</span>`;
        }
        if (chunk.domain_hint) {
            header.innerHTML += `<span class="chunk-meta-tag tag-domain">${esc(chunk.domain_hint)}</span>`;
        }
        if (chunk.content_type) {
            header.innerHTML += `<span class="chunk-meta-tag tag-content-type">${esc(chunk.content_type)}</span>`;
        }

        // Body
        const body = document.createElement("div");
        body.className = "chunk-card-body";

        const textEl = document.createElement("div");
        textEl.className = "chunk-text";
        let displayText = esc(chunk.text);
        if (query) {
            const regex = new RegExp(`(${escRegex(query)})`, "gi");
            displayText = displayText.replace(regex, "<mark>$1</mark>");
        }
        textEl.innerHTML = displayText;

        // Clamp long text
        body.appendChild(textEl);

        const toggle = document.createElement("button");
        toggle.className = "chunk-expand-toggle";
        toggle.textContent = "展开全部";
        toggle.addEventListener("click", () => {
            const isClamped = textEl.classList.contains("clamped");
            if (isClamped) {
                textEl.classList.remove("clamped");
                textEl.style.maxHeight = "none";
                toggle.textContent = "收起";
                toggle.style.display = "inline-block";
            } else {
                textEl.classList.add("clamped");
                textEl.style.maxHeight = "";
                toggle.textContent = "展开全部";
            }
        });
        body.appendChild(toggle);

        // Check if text needs clamping after render
        requestAnimationFrame(() => {
            if (textEl.scrollHeight > 160) {
                textEl.classList.add("clamped");
            }
        });

        // Footer
        const footer = document.createElement("div");
        footer.className = "chunk-card-footer";
        const charCount = chunk.text.length;
        const wordCount = chunk.text.split(/\s+/).filter(Boolean).length;
        footer.innerHTML = `
            <span>ID: ${chunk.chunk_id.substring(0, 12)}...</span>
            <span>${charCount} chars</span>
            <span>${wordCount} tokens (approx)</span>
        `;

        card.appendChild(header);
        card.appendChild(body);
        card.appendChild(footer);
        return card;
    }

    // --- Search ---
    let searchTimer = null;
    searchInput.addEventListener("input", () => {
        clearTimeout(searchTimer);
        searchTimer = setTimeout(() => {
            if (lastResult) {
                renderChunks(lastResult.chunks, searchInput.value);
            }
        }, 200);
    });

    // --- Export ---
    exportBtn.addEventListener("click", () => {
        if (!lastResult) return;
        const blob = new Blob([JSON.stringify(lastResult, null, 2)], {
            type: "application/json",
        });
        const url = URL.createObjectURL(blob);
        const a = document.createElement("a");
        a.href = url;
        a.download = `chunkflow_${lastResult.filename || "output"}.json`;
        a.click();
        URL.revokeObjectURL(url);
    });

    // --- Utils ---
    function showError(msg) {
        errorMsg.textContent = msg;
        errorMsg.hidden = false;
    }

    function hideError() {
        errorMsg.hidden = true;
    }

    function formatSize(bytes) {
        if (bytes < 1024) return bytes + " B";
        if (bytes < 1024 * 1024) return (bytes / 1024).toFixed(1) + " KB";
        return (bytes / (1024 * 1024)).toFixed(1) + " MB";
    }

    function esc(str) {
        const d = document.createElement("div");
        d.textContent = str;
        return d.innerHTML;
    }

    function escRegex(str) {
        return str.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
    }
})();
