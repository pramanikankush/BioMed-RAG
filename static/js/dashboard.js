// core frontend state
let state = {
    activeChatId: null,
    chats: {}, // id -> { name, messages }
    documents: [],
    useWeb: false,
    activeView: 'chat', // 'chat' | 'files' | 'admin'
    isGenerating: false,
    abortController: null
};

// Auto-run on load
document.addEventListener("DOMContentLoaded", () => {
    initApp();
});

async function initApp() {
    setupEventListeners();
    await loadRecentChats();
    await loadDocuments();
    showView('chat');
}

function setupEventListeners() {
    // New Chat Button
    document.getElementById("btn-new-chat").addEventListener("click", startNewChat);

    // Chat form submit
    const submitBtn = document.getElementById("submit-btn");
    const textarea = document.getElementById("chat-textarea");

    submitBtn.addEventListener("click", handleSendMessage);
    textarea.addEventListener("keydown", (e) => {
        if (e.key === "Enter" && !e.shiftKey) {
            e.preventDefault();
            handleSendMessage();
        }
    });

    // Web Search Toggle
    const searchToggle = document.getElementById("web-search-toggle");
    searchToggle.addEventListener("change", (e) => {
        state.useWeb = e.target.checked;
    });

    // Suggested Prompt Cards
    document.querySelectorAll(".suggested-prompt-card").forEach(card => {
        card.addEventListener("click", () => {
            textarea.value = card.dataset.prompt;
            textarea.focus();
        });
    });

    // Navigation Items
    document.getElementById("nav-chat-link").addEventListener("click", () => showView('chat'));
    document.getElementById("nav-files-link").addEventListener("click", () => showView('files'));
    document.getElementById("nav-admin-link").addEventListener("click", () => showView('admin'));

    // File Drag and Drop
    setupDragAndDrop();
}

function showView(viewName) {
    state.activeView = viewName;
    
    // Toggle navigation classes
    document.querySelectorAll(".sidebar-nav-link").forEach(link => link.classList.remove("active"));
    
    const activeLink = document.getElementById(`nav-${viewName}-link`);
    if (activeLink) activeLink.classList.add("active");

    // Toggle container visibilities
    document.getElementById("chat-view-container").classList.add("d-none");
    document.getElementById("files-view-container").classList.add("d-none");
    document.getElementById("admin-view-container").classList.add("d-none");

    if (viewName === 'chat') {
        document.getElementById("chat-view-container").classList.remove("d-none");
    } else if (viewName === 'files') {
        document.getElementById("files-view-container").classList.remove("d-none");
        renderFilesList();
    } else if (viewName === 'admin') {
        document.getElementById("admin-view-container").classList.remove("d-none");
        loadAdminStats();
    }
}

// --- Chat Session Functions ---

async function loadRecentChats() {
    try {
        const response = await fetch("/chats");
        if (response.ok) {
            const data = await response.json();
            state.chats = data;
            renderChatHistory();
            
            // Auto-load most recent chat if any
            const chatIds = Object.keys(state.chats);
            if (chatIds.length > 0) {
                loadChatSession(chatIds[0]);
            } else {
                startNewChat();
            }
        }
    } catch (error) {
        console.error("Failed to load chat history:", error);
    }
}

function startNewChat() {
    const newId = "chat_" + Date.now();
    state.activeChatId = newId;
    state.chats[newId] = {
        name: "New Chat",
        messages: []
    };
    renderChatHistory();
    loadChatSession(newId);
}

function loadChatSession(chatId) {
    state.activeChatId = chatId;
    
    // Highlight active chat item in sidebar
    document.querySelectorAll(".chat-history-item").forEach(item => {
        item.classList.remove("active");
    });
    const activeItem = document.getElementById(`history-item-${chatId}`);
    if (activeItem) activeItem.classList.add("active");

    const chat = state.chats[chatId];
    
    // Update active session title header dynamically
    if (chat) {
        document.getElementById("active-session-title").innerText = chat.name || "Medical Assistant";
    }

    const welcomeScreen = document.getElementById("welcome-screen");
    const messagesFeed = document.getElementById("messages-feed");

    messagesFeed.innerHTML = "";

    if (!chat || chat.messages.length === 0) {
        welcomeScreen.classList.remove("d-none");
    } else {
        welcomeScreen.classList.add("d-none");
        chat.messages.forEach(msg => {
            appendMessageBubble(msg.role, msg.content, msg.metadata);
        });
        scrollToBottom();
    }
}

function renderChatHistory() {
    const container = document.getElementById("chat-history-container");
    container.innerHTML = "";

    Object.entries(state.chats).reverse().forEach(([id, chat]) => {
        const item = document.createElement("div");
        item.className = `chat-history-item ${id === state.activeChatId ? 'active' : ''}`;
        item.id = `history-item-${id}`;
        
        item.innerHTML = `
            <div class="chat-history-title" onclick="loadChatSession('${id}')">
                <svg width="14" height="14" fill="currentColor" class="me-2"><path d="M2 2v10h10V2H2zm1 1h8v8H3V3z"/></svg>
                <span>${chat.name}</span>
            </div>
            <div class="chat-history-actions">
                <button class="chat-history-action-btn" onclick="event.stopPropagation(); renameChatSession('${id}')" title="Rename">
                    ✏️
                </button>
                <button class="chat-history-action-btn" onclick="event.stopPropagation(); deleteChatSession('${id}')" title="Delete">
                    🗑️
                </button>
            </div>
        `;
        container.appendChild(item);
    });
}

async function renameChatSession(chatId) {
    const currentName = state.chats[chatId]?.name || "";
    const newName = prompt("Rename conversation to:", currentName);
    if (newName && newName.trim()) {
        try {
            const response = await fetch(`/chats/${chatId}`, {
                method: "PUT",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({ name: newName })
            });
            if (response.ok) {
                state.chats[chatId].name = newName;
                renderChatHistory();
                if (state.activeChatId === chatId) {
                    document.getElementById("active-session-title").innerText = newName;
                }
            }
        } catch (error) {
            alert("Failed to rename chat");
        }
    }
}

async function deleteChatSession(chatId) {
    if (confirm("Are you sure you want to delete this chat?")) {
        try {
            const response = await fetch(`/chats/${chatId}`, {
                method: "DELETE"
            });
            if (response.ok) {
                delete state.chats[chatId];
                renderChatHistory();
                if (state.activeChatId === chatId) {
                    const remainingKeys = Object.keys(state.chats);
                    if (remainingKeys.length > 0) {
                        loadChatSession(remainingKeys[0]);
                    } else {
                        startNewChat();
                    }
                }
            }
        } catch (error) {
            alert("Failed to delete chat");
        }
    }
}

// --- Query Ingestion & Streaming ---

async function handleSendMessage() {
    if (state.isGenerating) return;

    const textarea = document.getElementById("chat-textarea");
    const queryText = textarea.value.trim();
    if (!queryText) return;

    textarea.value = "";
    document.getElementById("welcome-screen").classList.add("d-none");

    // Push user message to UI & State
    appendMessageBubble("user", queryText);
    const chat = state.chats[state.activeChatId];
    chat.messages.push({ role: "user", content: queryText });

    // Set title on first message
    if (chat.messages.length === 1) {
        chat.name = queryText.substring(0, 24) + (queryText.length > 24 ? "..." : "");
        renderChatHistory();
        // save title to backend
        fetch(`/chats/${state.activeChatId}`, {
            method: "PUT",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ name: chat.name })
        });
    }

    // Append Assistant placeholder with loading skeleton
    const assistantBubble = appendMessageBubble("assistant", "", null, true);
    scrollToBottom();

    state.isGenerating = true;
    state.abortController = new AbortController();

    try {
        const response = await fetch("/get_response", {
            method: "POST",
            headers: {
                "Content-Type": "application/x-www-form-urlencoded"
            },
            body: new URLSearchParams({
                query: queryText,
                chat_id: state.activeChatId,
                use_web: state.useWeb
            }),
            signal: state.abortController.signal
        });

        if (response.status === 429) {
            const data = await response.json();
            showErrorMessage(assistantBubble, data.detail || "Rate limit exceeded. Please wait.");
            state.isGenerating = false;
            return;
        }

        if (!response.ok) {
            throw new Error("Failed to fetch response from server");
        }

        const reader = response.body.getReader();
        const decoder = new TextDecoder("utf-8");
        let buffer = "";
        let markdownContent = "";
        let metadataReceived = null;

        // Remove skeleton loader
        const skeleton = assistantBubble.querySelector(".skeleton-loader");
        if (skeleton) skeleton.remove();

        const contentEl = assistantBubble.querySelector(".message-content");

        while (true) {
            const { value, done } = await reader.read();
            if (done) break;

            buffer += decoder.decode(value, { stream: true });
            const lines = buffer.split("\n");
            buffer = lines.pop(); // save incomplete line to buffer

            for (const line of lines) {
                const cleanLine = line.trim();
                if (cleanLine.startsWith("data: ")) {
                    const rawData = cleanLine.slice(6);
                    if (rawData === "[DONE]") break;

                    try {
                        const parsed = JSON.parse(rawData);
                        if (parsed.metadata) {
                            metadataReceived = parsed.metadata;
                            renderSourcesSection(assistantBubble, metadataReceived);
                        } else if (parsed.token) {
                            markdownContent += parsed.token;
                            // Simple markdown rendering
                            contentEl.innerHTML = parseMarkdown(markdownContent);
                            scrollToBottom();
                        } else if (parsed.error) {
                            showErrorMessage(assistantBubble, parsed.error);
                        }
                    } catch (e) {
                        console.error("Error parsing stream chunk:", e);
                    }
                }
            }
        }

        // Save completed response to state
        chat.messages.push({
            role: "assistant",
            content: markdownContent,
            metadata: metadataReceived
        });

        // Add feedback and actions below bubble
        renderMessageActions(assistantBubble, markdownContent);

    } catch (err) {
        if (err.name === "AbortError") {
            console.log("Request generation aborted by user.");
        } else {
            console.error("Query streaming error:", err);
            showErrorMessage(assistantBubble, "An error occurred while connecting to the medical search engine.");
        }
    } finally {
        state.isGenerating = false;
        state.abortController = null;
    }
}

function appendMessageBubble(role, content, metadata = null, isLoading = false) {
    const container = document.getElementById("messages-feed");
    const bubble = document.createElement("div");
    bubble.className = `message-bubble ${role}`;

    let innerContent = "";
    if (isLoading) {
        innerContent = `
            <div class="skeleton-loader">
                <div class="skeleton-line" style="width: 100%"></div>
                <div class="skeleton-line" style="width: 85%"></div>
                <div class="skeleton-line" style="width: 50%"></div>
            </div>
        `;
    } else {
        innerContent = parseMarkdown(content);
    }

    bubble.innerHTML = `
        <div class="message-avatar">
            ${role === "user" ? "U" : "AI"}
        </div>
        <div class="message-content-wrapper">
            <div class="message-content">
                ${innerContent}
            </div>
            <div class="sources-container"></div>
            <div class="actions-container"></div>
        </div>
    `;

    container.appendChild(bubble);

    if (metadata) {
        renderSourcesSection(bubble, metadata);
        renderMessageActions(bubble, content);
    }

    return bubble;
}

function showErrorMessage(bubble, msg) {
    const contentEl = bubble.querySelector(".message-content");
    contentEl.innerHTML = `<span class="text-danger">⚠️ ${msg}</span>`;
    const loader = bubble.querySelector(".skeleton-loader");
    if (loader) loader.remove();
}

function renderSourcesSection(bubble, metadata) {
    const container = bubble.querySelector(".sources-container");
    container.innerHTML = "";

    const localSources = metadata.local_sources || [];
    const webSources = metadata.web_sources || [];
    const confidence = metadata.confidence || 0.0;

    if (localSources.length === 0 && webSources.length === 0) return;

    let confClass = "confidence-low";
    if (confidence >= 0.7) confClass = "confidence-high";
    else if (confidence >= 0.4) confClass = "confidence-med";

    let sourcesHtml = `
        <div class="mt-3">
            <div class="d-flex align-items-center gap-2 mb-2">
                <span class="small text-muted font-weight-bold">Sources Cited:</span>
                <span class="confidence-badge ${confClass}">
                    Confidence: ${Math.round(confidence * 100)}%
                </span>
            </div>
            <div class="d-flex flex-wrap gap-2">
    `;

    // Local Doc Badges
    localSources.forEach((src) => {
        sourcesHtml += `
            <span class="badge bg-secondary text-light p-2" style="border: 1px solid var(--border-glass);" title="Source matching confidence: ${Math.round(src.score * 100)}%">
                📄 ${src.source} (Page ${src.page})
            </span>
        `;
    });

    // Web Search URL Badges
    webSources.forEach((src) => {
        sourcesHtml += `
            <a href="${src.url}" target="_blank" class="badge bg-dark text-light p-2 text-decoration-none border-glass" style="border: 1px solid var(--border-glass);" title="${src.title}">
                🌐 Web: ${src.title.substring(0, 20)}...
            </a>
        `;
    });

    sourcesHtml += `
            </div>
        </div>
    `;

    container.innerHTML = sourcesHtml;
}

function renderMessageActions(bubble, content) {
    const container = bubble.querySelector(".actions-container");
    container.innerHTML = `
        <div class="message-actions mt-2">
            <button class="message-action-btn" onclick="copyToClipboard(this, \`${content.replace(/`/g, '\\`').replace(/\$/g, '\\$')}\`)">
                📋 Copy
            </button>
            <button class="message-action-btn" onclick="thumbsUp(this)">
                👍
            </button>
            <button class="message-action-btn" onclick="thumbsDown(this)">
                👎
            </button>
            <button class="message-action-btn" onclick="downloadResponse(\`${content.replace(/`/g, '\\`').replace(/\$/g, '\\$')}\`)">
                📥 Download
            </button>
        </div>
    `;
}

// --- Helpers & UI micro-interactions ---

function parseMarkdown(text) {
    if (!text) return "";
    
    // escape HTML
    let html = text
        .replace(/&/g, "&amp;")
        .replace(/</g, "&lt;")
        .replace(/>/g, "&gt;");

    // Code blocks
    html = html.replace(/```([\s\S]*?)```/g, '<pre class="bg-dark p-3 rounded text-success"><code>$1</code></pre>');
    // Inline code
    html = html.replace(/`([^`\n]+)`/g, '<code class="bg-dark text-success px-1.5 py-0.5 rounded font-monospace small">$1</code>');
    // Bold
    html = html.replace(/\*\*(.*?)\*\*/g, "<strong>$1</strong>");
    // Bullet points
    html = html.replace(/^\s*-\s+(.*)$/gm, "<li>$1</li>");
    // Line breaks
    html = html.replace(/\n/g, "<br>");
    
    return html;
}

function scrollToBottom() {
    const chatWindow = document.getElementById("chat-window");
    chatWindow.scrollTop = chatWindow.scrollHeight;
}

function copyToClipboard(btn, text) {
    navigator.clipboard.writeText(text);
    const originalText = btn.innerHTML;
    btn.innerHTML = "✅ Copied!";
    setTimeout(() => {
        btn.innerHTML = originalText;
    }, 2000);
}

function thumbsUp(btn) {
    btn.classList.add("text-success");
    // send feedback
}

function thumbsDown(btn) {
    btn.classList.add("text-danger");
    // send feedback
}

function downloadResponse(text) {
    const blob = new Blob([text], { type: "text/markdown;charset=utf-8" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = "RAG_Medical_Response.md";
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
}

// --- Document Ingestion (File uploads & stats) ---

async function loadDocuments() {
    try {
        const response = await fetch("/documents");
        if (response.ok) {
            const data = await response.json();
            state.documents = data.files;
            
            // Render files list in sidebar stats
            updateDocumentStatsHeader(data);
        }
    } catch (e) {
        console.error("Failed to load documents list:", e);
    }
}

function updateDocumentStatsHeader(data) {
    const statsContainer = document.getElementById("sidebar-document-stats");
    if (statsContainer) {
        statsContainer.innerHTML = `
            <div class="mt-3 small text-muted">
                <div>Total Uploaded: <strong>${data.total_files} files</strong></div>
                <div>Chunk size: <strong>${data.total_chunks} chunks</strong></div>
            </div>
        `;
    }
}

function renderFilesList() {
    const tableBody = document.getElementById("documents-table-body");
    tableBody.innerHTML = "";

    if (state.documents.length === 0) {
        tableBody.innerHTML = `
            <tr>
                <td colspan="4" class="text-center text-muted p-4">No documents uploaded. Drag and drop PDF, DOCX, or TXT files above to add them.</td>
            </tr>
        `;
        return;
    }

    state.documents.forEach((doc, idx) => {
        const tr = document.createElement("tr");
        tr.innerHTML = `
            <td>${idx + 1}</td>
            <td class="font-weight-bold text-light">${doc.name}</td>
            <td>${(doc.size / (1024 * 1024)).toFixed(2)} MB</td>
            <td>
                <span class="badge bg-secondary me-2">${doc.chunks} chunks</span>
                <button class="btn btn-sm btn-outline-danger" onclick="deleteDocument('${doc.name}')">🗑️ Delete</button>
            </td>
        `;
        tableBody.appendChild(tr);
    });
}

async function deleteDocument(filename) {
    if (confirm(`Are you sure you want to delete ${filename}?`)) {
        try {
            const response = await fetch(`/documents/${filename}`, {
                method: "DELETE"
            });
            if (response.ok) {
                await loadDocuments();
                renderFilesList();
            }
        } catch (e) {
            alert("Failed to delete document.");
        }
    }
}

function setupDragAndDrop() {
    const zone = document.getElementById("drag-drop-zone");
    const fileInput = document.getElementById("file-upload-input");

    zone.addEventListener("click", () => fileInput.click());

    zone.addEventListener("dragover", (e) => {
        e.preventDefault();
        zone.classList.add("dragover");
    });

    zone.addEventListener("dragleave", () => {
        zone.classList.remove("dragover");
    });

    zone.addEventListener("drop", (e) => {
        e.preventDefault();
        zone.classList.remove("dragover");
        const files = e.dataTransfer.files;
        if (files.length > 0) {
            uploadFiles(files);
        }
    });

    fileInput.addEventListener("change", (e) => {
        const files = e.target.files;
        if (files.length > 0) {
            uploadFiles(files);
        }
    });
}

async function uploadFiles(files) {
    const uploadStatus = document.getElementById("upload-status");
    uploadStatus.innerHTML = `<span class="text-primary">Uploading and processing ${files.length} document(s)...</span>`;

    for (let i = 0; i < files.length; i++) {
        const file = files[i];
        const formData = new FormData();
        formData.append("file", file);

        try {
            const response = await fetch("/upload", {
                method: "POST",
                body: formData
            });

            if (response.status === 429) {
                uploadStatus.innerHTML = `<span class="text-danger">Rate limit exceeded for uploads. Please wait an hour.</span>`;
                return;
            }

            if (!response.ok) {
                const err = await response.json();
                uploadStatus.innerHTML = `<span class="text-danger">Upload failed: ${err.detail || file.name}</span>`;
                return;
            }

            uploadStatus.innerHTML = `<span class="text-success">✅ Successfully uploaded and parsed ${file.name}!</span>`;
        } catch (e) {
            uploadStatus.innerHTML = `<span class="text-danger">Failed to connect to upload API.</span>`;
        }
    }

    await loadDocuments();
    renderFilesList();
    setTimeout(() => {
        uploadStatus.innerHTML = "";
    }, 5000);
}

// --- Admin Dashboard Stats ---

async function loadAdminStats() {
    try {
        const response = await fetch("/admin/health");
        if (response.ok) {
            const data = await response.json();
            
            document.getElementById("admin-sys-status").innerHTML = `<span class="text-success">Healthy</span>`;
            document.getElementById("admin-chunks-count").innerHTML = `${data.vector_db.total_chunks}`;
            document.getElementById("admin-files-count").innerHTML = `${data.vector_db.total_files}`;
            
            // Cache performance
            const cache = data.cache;
            document.getElementById("admin-cache-size").innerHTML = `${cache.size} / ${cache.limit}`;
            document.getElementById("admin-cache-hits").innerHTML = `${cache.hits}`;
            document.getElementById("admin-cache-misses").innerHTML = `${cache.misses}`;
            document.getElementById("admin-cache-ratio").innerHTML = `${Math.round(cache.hit_ratio * 100)}%`;
            
            // Diagnostics
            document.getElementById("admin-diag-cpu").innerHTML = `${data.diagnostics.cpu_percent}%`;
            document.getElementById("admin-diag-ram").innerHTML = `${data.diagnostics.ram_percent}%`;
        }
    } catch (e) {
        console.error("Failed to load admin stats:", e);
    }
}
