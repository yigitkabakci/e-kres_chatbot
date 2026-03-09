(function () {
    "use strict";

    const API_URL = "/api/v1/chat";
    const AUTH_URL = "/api/v1/chat/parent-auth";
    const CLIENT_CONFIG_URL = "/api/v1/chat/client-config";
    const UPLOAD_PDF_URL = "/api/v1/chat/upload-pdf";
    const UPLOAD_URL_API = "/api/v1/chat/upload-url";
    const SESSION_KEY = "ekres_session_id";
    const AUTH_KEY = "ekres_parent_auth";
    const PROFILE_KEY = "ekres_parent_profile";
    const PARENT_NAME_KEY = "ekres_parent_name";
    const ASSISTANT_AVATAR = '<i class="fa-solid fa-robot"></i>';

    let clientConfig = { apiKey: "", appName: "e-Kres" };

    function generateUUID() {
        return "xxxxxxxx-xxxx-4xxx-yxxx-xxxxxxxxxxxx".replace(/[xy]/g, function (c) {
            const r = (Math.random() * 16) | 0;
            const v = c === "x" ? r : (r & 0x3) | 0x8;
            return v.toString(16);
        });
    }

    function getSessionId() {
        let sid = localStorage.getItem(SESSION_KEY);
        if (!sid) {
            sid = crypto.randomUUID ? crypto.randomUUID() : generateUUID();
            localStorage.setItem(SESSION_KEY, sid);
        }
        return sid;
    }

    function getStoredAuth() {
        try {
            return JSON.parse(localStorage.getItem(AUTH_KEY) || "null");
        } catch (error) {
            return null;
        }
    }

    function getStoredProfile() {
        try {
            return JSON.parse(localStorage.getItem(PROFILE_KEY) || "null");
        } catch (error) {
            return null;
        }
    }

    function storeLoginState(auth, profile) {
        localStorage.setItem(AUTH_KEY, JSON.stringify(auth));
        localStorage.setItem(PROFILE_KEY, JSON.stringify(profile));
        localStorage.setItem(PARENT_NAME_KEY, profile.parent_name || "");
        localStorage.setItem(SESSION_KEY, getSessionId());
    }

    async function loadClientConfig() {
        try {
            const response = await fetch(CLIENT_CONFIG_URL, { method: "GET" });
            const data = await response.json().catch(function () { return {}; });
            if (response.ok) {
                clientConfig = {
                    apiKey: data.api_key || "",
                    appName: data.app_name || "e-Kres",
                };
            }
        } catch (error) {
            clientConfig = { apiKey: "", appName: "e-Kres" };
        }
    }

    function buildHeaders(extraHeaders) {
        const headers = Object.assign({}, extraHeaders || {});
        headers["X-API-Key"] = clientConfig.apiKey || "";
        return headers;
    }

    function buildCitation(source, page) {
        if (!source) {
            return null;
        }
        if (page !== null && page !== undefined) {
            return "Kaynak: " + source + " - Sayfa " + page;
        }
        return "Kaynak: " + source;
    }

    const chatToggle = document.getElementById("chatToggle");
    const chatPanel = document.getElementById("chatPanel");
    const chatClose = document.getElementById("chatClose");
    const chatMessages = document.getElementById("chatMessages");
    const chatInput = document.getElementById("chatInput");
    const chatSend = document.getElementById("chatSend");
    const chatQuick = document.getElementById("chatQuick");
    const toggleBadge = document.getElementById("toggleBadge");
    const landingCta = document.getElementById("landingCta");
    const chatAttach = document.getElementById("chatAttach");
    const chatAttachUrl = document.getElementById("chatAttachUrl");
    const pdfFileInput = document.getElementById("pdfFileInput");
    const urlInputContainer = document.getElementById("urlInputContainer");
    const urlInputField = document.getElementById("urlInputField");
    const urlSubmitBtn = document.getElementById("urlSubmitBtn");
    const loginGate = document.getElementById("loginGate");
    const loginPhone = document.getElementById("loginPhone");
    const loginStartBtn = document.getElementById("loginStartBtn");
    const loginError = document.getElementById("loginError");
    const welcomeBubble = document.getElementById("welcomeBubble");

    let isOpen = false;
    let isSending = false;
    const savedAuth = getStoredAuth();
    const savedProfile = getStoredProfile();
    let parentAuth = null;
    let parentProfile = null;

    function updateWelcomeMessage() {
        if (parentProfile && parentProfile.greeting) {
            welcomeBubble.textContent = parentProfile.greeting;
            loginGate.classList.add("is-hidden");
            return;
        }

        if (savedProfile && savedProfile.parent_name) {
            welcomeBubble.textContent = "Hoþ geldiniz. Devam etmeden önce veliye ait telefon numarasýný yeniden doðrulayýn.";
        } else {
            welcomeBubble.textContent = "Hoþ geldiniz. Devam etmeden önce veliye ait telefon numarasýný girin.";
        }
        loginGate.classList.remove("is-hidden");
    }

    function openChat() {
        isOpen = true;
        chatPanel.classList.add("is-open");
        chatToggle.classList.add("is-active");
        toggleBadge.classList.remove("is-visible");
        if (loginGate.classList.contains("is-hidden")) {
            chatInput.focus();
        } else {
            loginPhone.focus();
        }
        scrollToBottom();
    }

    function closeChat() {
        isOpen = false;
        chatPanel.classList.remove("is-open");
        chatToggle.classList.remove("is-active");
    }

    function toggleChat() {
        isOpen ? closeChat() : openChat();
    }

    async function handleLogin() {
        const phone = (loginPhone.value || "").trim();

        if (!phone) {
            loginError.textContent = "Telefon numarasý zorunludur.";
            return;
        }

        loginError.textContent = "";
        loginStartBtn.disabled = true;
        loginStartBtn.textContent = "Giriþ yapýlýyor...";

        try {
            const response = await fetch(AUTH_URL, {
                method: "POST",
                headers: buildHeaders({
                    "Content-Type": "application/json",
                    "X-Auth-Flow": "parent-login",
                }),
                body: JSON.stringify({ phone: phone }),
            });

            const data = await response.json().catch(function () { return {}; });
            if (!response.ok) {
                throw new Error(data.detail || "Giriþ baþarýsýz.");
            }

            parentAuth = { phone: phone };
            parentProfile = data;
            storeLoginState(parentAuth, parentProfile);
            updateWelcomeMessage();
            chatInput.focus();
        } catch (error) {
            loginError.textContent = error.message || "Giriþ baþarýsýz.";
        } finally {
            loginStartBtn.disabled = false;
            loginStartBtn.textContent = "Sohbete Baþla";
        }
    }

    async function sendMessage(text) {
        if (isSending) {
            return;
        }

        isSending = true;
        chatSend.disabled = true;
        chatInput.value = "";
        appendMessage("user", text);
        const typingEl = showTyping();

        try {
            const response = await fetch(API_URL, {
                method: "POST",
                headers: buildHeaders({ "Content-Type": "application/json" }),
                body: JSON.stringify({
                    session_id: getSessionId(),
                    message: text,
                    parent_phone: parentAuth ? parentAuth.phone : null,
                    password: null,
                }),
            });

            const data = await response.json().catch(function () { return {}; });
            if (!response.ok) {
                throw new Error(data.detail || ("HTTP " + response.status));
            }

            removeTyping(typingEl);
            appendMessage("bot", data.response, buildCitation(data.source, data.page));
        } catch (error) {
            removeTyping(typingEl);
            appendMessage("bot", error.message || "Ýstek iþlenemedi.");
        } finally {
            isSending = false;
            chatSend.disabled = !chatInput.value.trim();
        }
    }

    async function submitUrl() {
        const urlVal = (urlInputField.value || "").trim();
        if (!urlVal) {
            return;
        }

        try {
            new URL(urlVal);
        } catch (error) {
            appendMessage("bot", "Lütfen geçerli bir URL girin.");
            return;
        }

        urlInputContainer.style.display = "none";
        urlInputField.value = "";
        chatAttachUrl.classList.add("is-uploading");
        appendMessage("user", "URL taranýyor: " + urlVal);
        const typingEl = showTyping();

        try {
            const response = await fetch(UPLOAD_URL_API, {
                method: "POST",
                headers: buildHeaders({ "Content-Type": "application/json" }),
                body: JSON.stringify({ url: urlVal, session_id: getSessionId() }),
            });
            const data = await response.json().catch(function () { return {}; });
            removeTyping(typingEl);
            if (!response.ok) {
                throw new Error(data.detail || "Tarama baþarýsýz.");
            }
            appendMessage("bot", data.message || "Web sayfasý baþarýyla tarandý.");
        } catch (error) {
            removeTyping(typingEl);
            appendMessage("bot", "URL taranýrken hata oluþtu: " + error.message);
        } finally {
            chatAttachUrl.classList.remove("is-uploading");
        }
    }

    function appendMessage(role, text, citation) {
        const wrapper = document.createElement("div");
        wrapper.className = role === "user" ? "chat-msg chat-msg--user" : "chat-msg chat-msg--bot";

        if (role !== "user") {
            const avatar = document.createElement("div");
            avatar.className = "chat-msg__avatar";
            avatar.innerHTML = ASSISTANT_AVATAR;
            wrapper.appendChild(avatar);
        }

        const content = document.createElement("div");
        content.className = "chat-msg__content";

        const bubble = document.createElement("div");
        bubble.className = "chat-msg__bubble";
        bubble.innerHTML = formatText(text);
        content.appendChild(bubble);

        if (role !== "user" && citation) {
            const citationEl = document.createElement("div");
            citationEl.className = "chat-msg__citation";
            citationEl.textContent = citation;
            content.appendChild(citationEl);
        }

        wrapper.appendChild(content);
        chatMessages.appendChild(wrapper);
        scrollToBottom();
    }

    function formatText(text) {
        if (!text) {
            return "";
        }

        let html = text.replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;");
        html = html.replace(/\*\*(.*?)\*\*/g, "<strong>$1</strong>");
        html = html.replace(/__(.*?)__/g, "<strong>$1</strong>");
        html = html.replace(/\*(.*?)\*/g, "<em>$1</em>");
        html = html.replace(/^[\-•]\s+(.+)/gm, "<li>$1</li>");
        html = html.replace(/(<li>.*<\/li>)/gs, "<ul>$1</ul>");
        html = html.replace(/<\/ul>\s*<ul>/g, "");
        html = html.replace(/\n/g, "<br>");
        return html;
    }

    function showTyping() {
        const wrapper = document.createElement("div");
        wrapper.className = "chat-msg chat-msg--bot chat-msg--typing";

        const avatar = document.createElement("div");
        avatar.className = "chat-msg__avatar";
        avatar.innerHTML = ASSISTANT_AVATAR;

        const content = document.createElement("div");
        content.className = "chat-msg__content";

        const bubble = document.createElement("div");
        bubble.className = "chat-msg__bubble";
        bubble.innerHTML = '<span class="typing-dot"></span><span class="typing-dot"></span><span class="typing-dot"></span>';

        content.appendChild(bubble);
        wrapper.appendChild(avatar);
        wrapper.appendChild(content);
        chatMessages.appendChild(wrapper);
        scrollToBottom();
        return wrapper;
    }

    function removeTyping(el) {
        if (el && el.parentNode) {
            el.parentNode.removeChild(el);
        }
    }

    function scrollToBottom() {
        requestAnimationFrame(function () {
            chatMessages.scrollTop = chatMessages.scrollHeight;
        });
    }

    chatToggle.addEventListener("click", toggleChat);
    chatClose.addEventListener("click", closeChat);
    if (landingCta) {
        landingCta.addEventListener("click", openChat);
    }

    const featureCards = document.querySelectorAll(".feature-card[data-msg]");
    featureCards.forEach(function (card) {
        card.style.cursor = "pointer";
        card.addEventListener("click", function () {
            const msg = card.getAttribute("data-msg");
            if (!msg || isSending) {
                return;
            }
            if (!isOpen) {
                openChat();
            }
            setTimeout(function () { sendMessage(msg); }, 150);
        });
        card.addEventListener("keydown", function (event) {
            if (event.key === "Enter" || event.key === " ") {
                event.preventDefault();
                card.click();
            }
        });
    });

    chatQuick.addEventListener("click", function (event) {
        const btn = event.target.closest(".quick-btn");
        if (!btn || isSending) {
            return;
        }
        const msg = btn.getAttribute("data-msg");
        if (msg) {
            sendMessage(msg);
        }
    });

    chatInput.addEventListener("input", function () {
        chatSend.disabled = !chatInput.value.trim();
    });

    chatInput.addEventListener("keydown", function (event) {
        if (event.key === "Enter" && !event.shiftKey) {
            event.preventDefault();
            if (chatInput.value.trim() && !isSending) {
                sendMessage(chatInput.value.trim());
            }
        }
    });

    chatSend.addEventListener("click", function () {
        if (chatInput.value.trim() && !isSending) {
            sendMessage(chatInput.value.trim());
        }
    });

    loginStartBtn.addEventListener("click", handleLogin);
    loginPhone.addEventListener("keydown", function (event) {
        if (event.key === "Enter") {
            event.preventDefault();
            handleLogin();
        }
    });

    if (chatAttachUrl && urlInputContainer) {
        chatAttachUrl.addEventListener("click", function () {
            if (!isOpen) {
                openChat();
            }
            urlInputContainer.style.display = urlInputContainer.style.display === "none" ? "flex" : "none";
            if (urlInputContainer.style.display === "flex") {
                urlInputField.focus();
            }
        });
        urlSubmitBtn.addEventListener("click", submitUrl);
        urlInputField.addEventListener("keydown", function (event) {
            if (event.key === "Enter") {
                event.preventDefault();
                submitUrl();
            }
        });
    }

    if (chatAttach && pdfFileInput) {
        chatAttach.addEventListener("click", function () {
            if (!isOpen) {
                openChat();
            }
            pdfFileInput.click();
        });

        pdfFileInput.addEventListener("change", async function () {
            const file = pdfFileInput.files[0];
            if (!file) {
                return;
            }
            if (!file.name.toLowerCase().endsWith(".pdf")) {
                appendMessage("bot", "Sadece PDF dosyalarý kabul edilir.");
                pdfFileInput.value = "";
                return;
            }
            if (file.size > 10 * 1024 * 1024) {
                appendMessage("bot", "PDF dosyasý 10MB'dan büyük olamaz.");
                pdfFileInput.value = "";
                return;
            }

            chatAttach.classList.add("is-uploading");
            appendMessage("user", "PDF yükleniyor: " + file.name);
            const typingEl = showTyping();

            try {
                const formData = new FormData();
                formData.append("file", file);
                formData.append("session_id", getSessionId());

                const response = await fetch(UPLOAD_PDF_URL, {
                    method: "POST",
                    headers: buildHeaders(),
                    body: formData,
                });
                const data = await response.json().catch(function () { return {}; });
                removeTyping(typingEl);
                if (!response.ok) {
                    throw new Error(data.detail || "Yükleme baþarýsýz.");
                }
                appendMessage("bot", data.message || (file.name + " baþarýyla yüklendi."));
            } catch (error) {
                removeTyping(typingEl);
                appendMessage("bot", "PDF yüklenirken hata oluþtu: " + error.message);
            } finally {
                chatAttach.classList.remove("is-uploading");
                pdfFileInput.value = "";
            }
        });
    }

    document.addEventListener("keydown", function (event) {
        if (event.key === "Escape" && isOpen) {
            closeChat();
        }
    });

    setTimeout(function () {
        if (!isOpen) {
            toggleBadge.classList.add("is-visible");
        }
    }, 2000);

    if (savedAuth) {
        loginPhone.value = savedAuth.phone || "";
    }
    localStorage.removeItem(AUTH_KEY);
    localStorage.removeItem(PROFILE_KEY);
    localStorage.removeItem(PARENT_NAME_KEY);

    loadClientConfig().finally(function () {
        updateWelcomeMessage();
        getSessionId();
    });
})();
