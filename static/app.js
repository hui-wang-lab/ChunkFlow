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
    const qualityPanel = $("#qualityPanel");
    const searchInput = $("#searchInput");
    const exportBtn = $("#exportBtn");
    const parserBadge = $("#parserBadge");
    const chunksTab = $("#chunksTab");
    const monitorTab = $("#monitorTab");
    const chunksView = $("#chunksView");
    const monitorView = $("#monitorView");
    const monitorPanel = $("#monitorPanel");

    let selectedFile = null;
    let lastResult = null;
    const parserLabels = {
        mineru: "MinerU",
        docling: "Docling",
        pypdf: "PyPDF",
        table_file: "Table file",
        text_file: "Text file",
    };
    const supportedExtensions = [".pdf", ".csv", ".tsv", ".xlsx", ".xlsm", ".txt", ".md", ".markdown"];

    fetch("/api/status")
        .then((r) => r.json())
        .then((data) => {
            parserBadge.textContent = parserLabels[data.parser] || data.parser || "offline";
            parserBadge.className = "badge " + data.parser;
        })
        .catch(() => {
            parserBadge.textContent = "offline";
        });

    dropZone.addEventListener("click", () => fileInput.click());
    dropZone.addEventListener("dragover", (e) => {
        e.preventDefault();
        dropZone.classList.add("dragover");
    });
    dropZone.addEventListener("dragleave", () => dropZone.classList.remove("dragover"));
    dropZone.addEventListener("drop", (e) => {
        e.preventDefault();
        dropZone.classList.remove("dragover");
        if (e.dataTransfer.files.length > 0) selectFile(e.dataTransfer.files[0]);
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

    chunksTab.addEventListener("click", () => setActiveView("chunks"));
    monitorTab.addEventListener("click", () => setActiveView("monitor"));

    function selectFile(file) {
        const lowerName = file.name.toLowerCase();
        if (!supportedExtensions.some((ext) => lowerName.endsWith(ext))) {
            showError("请选择 PDF / CSV / TSV / XLSX / TXT / Markdown 文件");
            return;
        }
        selectedFile = file;
        fileName.textContent = file.name;
        fileSize.textContent = formatSize(file.size);
        fileInfo.hidden = false;
        parseBtn.disabled = false;
        hideError();
    }

    parseBtn.addEventListener("click", async () => {
        if (!selectedFile) return;
        hideError();
        results.hidden = true;
        loading.hidden = false;
        parseBtn.disabled = true;

        const formData = new FormData();
        formData.append("file", selectedFile);
        const params = new URLSearchParams({
            parser: $("#parserMode").value,
            max_tokens: $("#maxTokens").value,
            chunk_size_tokens: $("#chunkSize").value,
            overlap_tokens: $("#overlap").value,
            min_chunk_tokens: $("#minChunkTokens").value,
            include_blocks: "true",
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

    function renderResults(data) {
        results.hidden = false;
        setActiveView("monitor");
        const chunks = data.child_chunks || data.chunks || [];
        $("#statChunks").textContent = data.child_chunk_count ?? data.chunk_count ?? chunks.length;
        $("#statParser").textContent = parserLabels[data.parser_used] || data.parser_used || "Unknown";
        $("#statSize").textContent = formatSize(data.file_size_bytes || 0);

        searchInput.value = "";
        renderQuality(data);
        renderMonitor(data);
        renderChunks(chunks, "");
    }

    function setActiveView(view) {
        const monitorActive = view === "monitor";
        monitorView.hidden = !monitorActive;
        chunksView.hidden = monitorActive;
        qualityPanel.hidden = monitorActive || !lastResult;
        chunksTab.classList.toggle("active", !monitorActive);
        monitorTab.classList.toggle("active", monitorActive);
        searchInput.hidden = monitorActive;
    }

    function renderQuality(data) {
        const metrics = (data.parse_report && data.parse_report.metrics) || {};
        const items = [
            ["Parents", data.parent_chunk_count ?? (data.parent_chunks || []).length ?? 0],
            ["Blocks", (data.blocks || []).length || (data.parse_report && data.parse_report.block_count) || 0],
            ["Warnings", (data.warnings || []).length],
            ["Orphans", metrics.orphan_child_count ?? 0],
            ["Missing sources", metrics.chunks_without_source_block_count ?? 0],
            ["Over token", metrics.over_max_token_child_count ?? 0],
            ["Table ctx", pct(metrics.table_context_coverage)],
            ["Avg tokens", number(metrics.avg_tokens_per_child)],
        ];
        qualityPanel.innerHTML = items.map(([label, value]) => `
            <div class="quality-item">
                <span class="quality-label">${esc(label)}</span>
                <span class="quality-value">${esc(String(value))}</span>
            </div>
        `).join("");
    }

    function renderMonitor(data) {
        const monitor = data.quality_monitor || buildClientMonitor(data);
        monitorPanel.innerHTML = `
            ${renderMonitorSummary(monitor.summary)}
            ${renderExecutionChain(monitor.execution_chain || [])}
            ${renderHealthChecks(monitor.health_checks || [])}
            <div class="monitor-grid">
                ${renderMetricList("关键指标", monitor.metrics || {})}
                ${renderDistributions(monitor.distributions || {})}
            </div>
            ${renderWarningGroups(monitor.warning_groups || [])}
            ${renderRiskSamples(monitor.risk_samples || [])}
            ${renderSuggestedChecks(monitor.suggested_checks || [])}
        `;
    }

    function renderMonitorSummary(summary = {}) {
        const cards = [
            ["文件", summary.filename || "-"],
            ["文档类型", summary.document_type || "-"],
            ["解析器", `${summary.parser_requested || "auto"} -> ${summary.parser_used || "-"}`],
            ["切片器", summary.chunker_used || "-"],
            ["页面/块", `${summary.page_count ?? 0} / ${summary.block_count ?? 0}`],
            ["父/子块", `${summary.parent_count ?? 0} / ${summary.child_count ?? 0}`],
        ];
        return `<section class="monitor-section">
            <h3>本次执行概览</h3>
            <div class="monitor-summary">
                ${cards.map(([label, value]) => `
                    <div class="monitor-card">
                        <span>${esc(label)}</span>
                        <strong>${esc(String(value))}</strong>
                    </div>
                `).join("")}
            </div>
        </section>`;
    }

    function renderExecutionChain(chain) {
        return `<section class="monitor-section">
            <h3>核心链路</h3>
            <div class="chain-list">
                ${chain.map((item, index) => `
                    <div class="chain-step ${esc(item.status || "ok")}">
                        <div class="chain-index">${index + 1}</div>
                        <div>
                            <div class="chain-title">${esc(stageLabel(item.stage))}</div>
                            <div class="chain-detail">${esc(item.detail || "-")}</div>
                            ${item.fallback_chain ? `<div class="chain-extra">fallback: ${esc(formatChain(item.fallback_chain))}</div>` : ""}
                        </div>
                    </div>
                `).join("")}
            </div>
        </section>`;
    }

    function renderHealthChecks(checks) {
        return `<section class="monitor-section">
            <h3>健康检查</h3>
            <div class="health-grid">
                ${checks.map((check) => `
                    <div class="health-card ${esc(check.status || "ok")}">
                        <span class="health-status">${check.status === "ok" ? "OK" : "WARN"}</span>
                        <strong>${esc(check.label || check.name || "-")}</strong>
                        <p>${esc(check.detail || "")}</p>
                    </div>
                `).join("")}
            </div>
        </section>`;
    }

    function renderMetricList(title, metrics) {
        const entries = Object.entries(metrics).filter(([, value]) => value !== null && value !== undefined);
        return `<section class="monitor-section">
            <h3>${esc(title)}</h3>
            <div class="metric-table">
                ${entries.length ? entries.map(([key, value]) => `
                    <div><span>${esc(key)}</span><strong>${esc(formatValue(value))}</strong></div>
                `).join("") : `<p class="empty-state">暂无指标</p>`}
            </div>
        </section>`;
    }

    function renderDistributions(distributions) {
        const groups = Object.entries(distributions).filter(([, values]) => values && Object.keys(values).length);
        return `<section class="monitor-section">
            <h3>类型分布</h3>
            ${groups.length ? groups.map(([name, values]) => `
                <div class="dist-group">
                    <h4>${esc(name)}</h4>
                    <div class="dist-bars">
                        ${renderBars(values)}
                    </div>
                </div>
            `).join("") : `<p class="empty-state">暂无分布数据</p>`}
        </section>`;
    }

    function renderBars(values) {
        const entries = Object.entries(values);
        const max = Math.max(...entries.map(([, value]) => Number(value) || 0), 1);
        return entries.map(([key, value]) => {
            const width = Math.max(4, Math.round((Number(value) || 0) / max * 100));
            return `<div class="dist-row">
                <span>${esc(key)}</span>
                <div class="dist-track"><div style="width:${width}%"></div></div>
                <strong>${esc(String(value))}</strong>
            </div>`;
        }).join("");
    }

    function renderWarningGroups(groups) {
        return `<section class="monitor-section">
            <h3>告警分组</h3>
            ${groups.length ? groups.map((group) => `
                <details class="warning-group" open>
                    <summary>${esc(group.group)} <span>${group.count}</span></summary>
                    ${(group.examples || []).map((example) => `<p>${esc(example)}</p>`).join("")}
                </details>
            `).join("") : `<p class="empty-state">没有告警</p>`}
        </section>`;
    }

    function renderRiskSamples(samples) {
        return `<section class="monitor-section">
            <h3>风险样例</h3>
            ${samples.length ? samples.map((sample) => `
                <div class="risk-sample">
                    <div class="risk-head">
                        <strong>${esc(sample.chunk_type || "chunk")}</strong>
                        <span>${esc((sample.reasons || []).join(", "))}</span>
                        <span>${esc(pageSpan(sample.page_span))}</span>
                        <span>${esc(String(sample.token_count ?? "-"))} tokens</span>
                    </div>
                    <p>${esc(sample.text_preview || "")}</p>
                    <code>${esc(sample.chunk_id || "")}</code>
                </div>
            `).join("") : `<p class="empty-state">没有明显风险样例</p>`}
        </section>`;
    }

    function renderSuggestedChecks(suggestions) {
        return `<section class="monitor-section">
            <h3>下一步排查</h3>
            <ul class="suggestion-list">
                ${(suggestions || []).map((item) => `<li>${esc(item)}</li>`).join("")}
            </ul>
        </section>`;
    }

    function renderChunks(chunks, query) {
        chunkList.innerHTML = "";
        const filtered = query
            ? chunks.filter((c) => (c.text || "").toLowerCase().includes(query.toLowerCase()))
            : chunks;

        if (filtered.length === 0) {
            chunkList.innerHTML = `<div class="empty-state">${query ? "没有匹配的 chunk" : "未生成任何 chunk"}</div>`;
            return;
        }

        const fragment = document.createDocumentFragment();
        filtered.forEach((chunk, index) => {
            fragment.appendChild(createChunkCard(chunk, query, index));
        });
        chunkList.appendChild(fragment);
    }

    function createChunkCard(chunk, query, index) {
        const card = document.createElement("div");
        card.className = "chunk-card";

        const header = document.createElement("div");
        header.className = "chunk-card-header";
        header.innerHTML = `<span class="chunk-index">#${chunk.chunk_index ?? index}</span>`;
        header.innerHTML += `<span class="chunk-page">${pageLabel(chunk)}</span>`;

        const headingPath = chunk.heading_path || chunk.headings || [];
        if (headingPath.length > 0) header.innerHTML += `<span class="chunk-meta-tag tag-chapter">${esc(headingPath[0])}</span>`;
        if (headingPath.length > 1) header.innerHTML += `<span class="chunk-meta-tag tag-section">${esc(headingPath[headingPath.length - 1])}</span>`;
        const contentType = chunk.chunk_type || chunk.content_type;
        if (contentType) header.innerHTML += `<span class="chunk-meta-tag tag-content-type">${esc(contentType)}</span>`;

        const body = document.createElement("div");
        body.className = "chunk-card-body";
        const textEl = document.createElement("div");
        textEl.className = "chunk-text";
        let displayText = esc(chunk.text || "");
        if (query) {
            const regex = new RegExp(`(${escRegex(query)})`, "gi");
            displayText = displayText.replace(regex, "<mark>$1</mark>");
        }
        textEl.innerHTML = displayText;
        body.appendChild(textEl);

        const toggle = document.createElement("button");
        toggle.className = "chunk-expand-toggle";
        toggle.textContent = "展开全部";
        toggle.addEventListener("click", () => {
            const isClamped = textEl.classList.contains("clamped");
            textEl.classList.toggle("clamped", !isClamped);
            textEl.style.maxHeight = isClamped ? "none" : "";
            toggle.textContent = isClamped ? "收起" : "展开全部";
        });
        body.appendChild(toggle);
        requestAnimationFrame(() => {
            if (textEl.scrollHeight > 160) textEl.classList.add("clamped");
        });

        const footer = document.createElement("div");
        footer.className = "chunk-card-footer";
        const text = chunk.text || "";
        footer.innerHTML = `
            <span>ID: ${esc((chunk.chunk_id || "").substring(0, 12))}...</span>
            <span>${text.length} chars</span>
            <span>${chunk.token_count ?? text.split(/\s+/).filter(Boolean).length} tokens</span>
        `;

        card.appendChild(header);
        card.appendChild(body);
        card.appendChild(footer);
        return card;
    }

    let searchTimer = null;
    searchInput.addEventListener("input", () => {
        clearTimeout(searchTimer);
        searchTimer = setTimeout(() => {
            if (lastResult) renderChunks(lastResult.child_chunks || lastResult.chunks || [], searchInput.value);
        }, 200);
    });

    exportBtn.addEventListener("click", () => {
        if (!lastResult) return;
        const blob = new Blob([JSON.stringify(lastResult, null, 2)], { type: "application/json" });
        const url = URL.createObjectURL(blob);
        const a = document.createElement("a");
        a.href = url;
        a.download = `chunkflow_${lastResult.filename || "output"}.json`;
        a.click();
        URL.revokeObjectURL(url);
    });

    function buildClientMonitor(data) {
        return {
            summary: {
                filename: data.filename,
                document_type: data.document_type,
                parser_requested: data.parser_requested,
                parser_used: data.parser_used,
                chunker_used: data.chunker_used,
                page_count: data.parse_report?.page_count,
                block_count: data.parse_report?.block_count,
                parent_count: data.parent_chunk_count,
                child_count: data.child_chunk_count,
            },
            execution_chain: [],
            health_checks: [],
            metrics: data.parse_report?.metrics || {},
            distributions: {},
            warning_groups: [],
            risk_samples: [],
            suggested_checks: ["当前响应没有 quality_monitor 字段，请确认后端版本。"],
        };
    }

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
        d.textContent = str == null ? "" : String(str);
        return d.innerHTML;
    }

    function escRegex(str) {
        return str.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
    }

    function pageLabel(chunk) {
        return pageSpan(chunk.page_span) || `Page ${chunk.page_number || "-"}`;
    }

    function pageSpan(span) {
        if (Array.isArray(span) && span.length === 2) {
            return span[0] === span[1] ? `Page ${span[0]}` : `Pages ${span[0]}-${span[1]}`;
        }
        return "";
    }

    function pct(value) {
        if (typeof value !== "number") return "-";
        return `${Math.round(value * 100)}%`;
    }

    function number(value) {
        if (typeof value !== "number") return "-";
        return Number.isInteger(value) ? value : value.toFixed(1);
    }

    function formatValue(value) {
        if (typeof value === "number") return number(value);
        if (typeof value === "boolean") return value ? "true" : "false";
        return String(value);
    }

    function formatChain(chain) {
        return Array.isArray(chain) ? chain.join(" -> ") : String(chain);
    }

    function stageLabel(stage) {
        const labels = {
            upload: "上传",
            parse: "解析",
            normalize: "归一化",
            detect_type: "类型识别",
            chunk: "切片",
            postprocess: "后处理",
        };
        return labels[stage] || stage || "-";
    }
})();
