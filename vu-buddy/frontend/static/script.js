async function apiCall(url, method = "GET", data = null) {
    const options = { method, headers: { "Content-Type": "application/json" } };
    if (data) {
        options.body = JSON.stringify(data);
    }
    const response = await fetch(url, options);
    const payload = await response.json();
    if (!response.ok) {
        throw new Error(payload.message || "Request failed.");
    }
    return payload;
}

function showMessage(elementId, message, type = "info") {
    const box = document.getElementById(elementId);
    if (!box) return;
    box.textContent = message;
    box.classList.remove("d-none", "alert-info", "alert-success", "alert-danger");
    box.classList.add(`alert-${type}`);
}

function animateNumber(el, nextValue) {
    if (!el) return;
    const target = Number(nextValue);
    if (!Number.isFinite(target)) {
        el.textContent = nextValue;
        return;
    }

    const current = Number(el.textContent) || 0;
    if (current === target) return;

    const duration = 450;
    const start = performance.now();
    const step = (t) => {
        const progress = Math.min((t - start) / duration, 1);
        const value = Math.round(current + (target - current) * progress);
        el.textContent = value;
        if (progress < 1) requestAnimationFrame(step);
    };
    requestAnimationFrame(step);
}

async function refreshDashboard() {
    const data = await apiCall("/api/status");

    // System status
    const statusText = data.is_running ? "Running" : "Stopped";
    const statusEl = document.getElementById("botStatus");
    const statusDot = document.getElementById("statusDot");
    if (statusEl) {
        statusEl.textContent = statusText;
        statusEl.style.color = data.is_running ? "#118a3c" : "#c52233";
    }
    if (statusDot) {
        statusDot.classList.remove("running", "stopped");
        statusDot.classList.add(data.is_running ? "running" : "stopped");
    }
    document.getElementById("lastCheck").textContent = data.last_check_time;
    animateNumber(document.getElementById("notificationsCount"), data.notifications_sent);
    document.getElementById("lastError").textContent = data.last_error || "None";

    // Per-type totals
    animateNumber(document.getElementById("assignmentsTotalCount"), data.assignments_total);
    animateNumber(document.getElementById("gdbsTotalCount"), data.gdbs_total);
    animateNumber(document.getElementById("quizzesTotalCount"), data.quizzes_total);
    animateNumber(document.getElementById("announcementsTotalCount"), data.announcements_total);

    // Per-type new badges
    document.getElementById("assignmentsNewBadge").textContent = data.assignments_new;
    document.getElementById("gdbsNewBadge").textContent = data.gdbs_new;
    document.getElementById("quizzesNewBadge").textContent = data.quizzes_new;
    document.getElementById("announcementsNewBadge").textContent = data.announcements_new;
}

function getSelectedTestType() {
    const sel = document.getElementById("testTypeSelect");
    return sel ? sel.value : "assignment";
}

async function bindDashboardActions() {
    const startBtn = document.getElementById("startBotBtn");
    const runBtn = document.getElementById("runNowBtn");
    const stopBtn = document.getElementById("stopBotBtn");
    const waBtn = document.getElementById("testWhatsappBtn");
    const emailBtn = document.getElementById("testEmailBtn");

    if (startBtn) {
        startBtn.addEventListener("click", async () => {
            try {
                const res = await apiCall("/start", "POST");
                showMessage("actionMessage", res.message, "success");
                refreshDashboard();
            } catch (error) {
                showMessage("actionMessage", error.message, "danger");
            }
        });
    }
    if (runBtn) {
        runBtn.addEventListener("click", async () => {
            try {
                const res = await apiCall("/run", "POST");
                showMessage("actionMessage", res.message, "success");
                refreshDashboard();
            } catch (error) {
                showMessage("actionMessage", error.message, "danger");
            }
        });
    }
    if (stopBtn) {
        stopBtn.addEventListener("click", async () => {
            try {
                const res = await apiCall("/stop", "POST");
                showMessage("actionMessage", res.message, "danger");
                refreshDashboard();
            } catch (error) {
                showMessage("actionMessage", error.message, "danger");
            }
        });
    }
    if (waBtn) {
        waBtn.addEventListener("click", async () => {
            try {
                const ctype = getSelectedTestType();
                const res = await apiCall("/test", "POST", { channel: "whatsapp", content_type: ctype });
                showMessage("actionMessage", res.message, "success");
                refreshDashboard();
            } catch (error) {
                showMessage("actionMessage", error.message, "danger");
            }
        });
    }
    if (emailBtn) {
        emailBtn.addEventListener("click", async () => {
            try {
                const ctype = getSelectedTestType();
                const res = await apiCall("/test", "POST", { channel: "email", content_type: ctype });
                showMessage("actionMessage", res.message, "success");
                refreshDashboard();
            } catch (error) {
                showMessage("actionMessage", error.message, "danger");
            }
        });
    }
}

async function loadSettings() {
    const data = await apiCall("/api/settings");
    const wa = document.getElementById("whatsappToggle");
    const em = document.getElementById("emailToggle");
    const it = document.getElementById("intervalInput");
    if (wa) wa.checked = data.whatsapp_enabled;
    if (em) em.checked = data.email_enabled;
    if (it) it.value = data.check_interval;
}

function bindSettingsSave() {
    const saveBtn = document.getElementById("saveSettingsBtn");
    if (!saveBtn) return;

    saveBtn.addEventListener("click", async () => {
        const payload = {
            whatsapp_enabled: document.getElementById("whatsappToggle")?.checked ?? false,
            email_enabled: document.getElementById("emailToggle")?.checked ?? false,
            check_interval: Number(document.getElementById("intervalInput")?.value || 5),
        };
        try {
            await apiCall("/api/settings", "POST", payload);
            showMessage("settingsMessage", "Settings saved successfully.", "success");
        } catch (error) {
            showMessage("settingsMessage", error.message, "danger");
        }
    });
}

async function refreshLogs() {
    const data = await apiCall("/api/logs");
    const list = document.getElementById("logsList");
    const lastNoti = document.getElementById("lastNotification");
    const count = document.getElementById("logsNotificationCount");

    if (list) {
        list.innerHTML = "";
        data.logs.forEach((line) => {
            const row = document.createElement("div");
            row.className = "log-item";
            row.textContent = line;
            list.appendChild(row);
        });
    }
    if (lastNoti) lastNoti.textContent = data.last_notification;
    animateNumber(count, data.notifications_sent);
}

document.addEventListener("DOMContentLoaded", async () => {
    const page = document.body.dataset.page;

    if (page === "dashboard") {
        await refreshDashboard();
        bindDashboardActions();
        setInterval(refreshDashboard, 5000);
    }

    if (page === "settings") {
        await loadSettings();
        bindSettingsSave();
    }

    if (page === "logs") {
        await refreshLogs();
        setInterval(refreshLogs, 5000);
    }
});
