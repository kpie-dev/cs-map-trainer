"use strict";

(() => {
  const errors = JSON.parse(document.getElementById("ui-errors").textContent);
  const csrf = () => document.querySelector("[name=csrfmiddlewaretoken]")?.value;
  const message = (code) => errors[code] || `The action failed. Error code: ${code}`;

  const guide = document.getElementById("steam-id-guide");
  const openGuide = document.getElementById("steam-id-guide-open");
  if (guide && openGuide && typeof HTMLDialogElement !== "undefined") {
    const close = document.getElementById("steam-id-guide-close");
    openGuide.addEventListener("click", (event) => {
      event.preventDefault();
      guide.showModal();
      close.focus();
    });
    guide.addEventListener("close", () => openGuide.focus());
  }

  async function request(url, data) {
    let response;
    const controller = new AbortController();
    const timeout = setTimeout(() => controller.abort(), 60000);
    try {
      response = await fetch(url, {
        method: data === undefined ? "GET" : "POST",
        credentials: "same-origin",
        headers: data === undefined ? {} : {
          "Content-Type": "application/json",
          "X-CSRFToken": csrf(),
        },
        body: data === undefined ? undefined : JSON.stringify(data),
        signal: controller.signal,
      });
    } catch (error) {
      throw new Error("Connection failed. Check your network and try again.", { cause: error });
    } finally {
      clearTimeout(timeout);
    }
    if (!response.headers.get("content-type")?.includes("application/json")) {
      throw new Error(`The server returned HTTP ${response.status}. Refresh the page and check that you are signed in.`);
    }
    const result = await response.json();
    if (!response.ok) {
      const error = new Error(message(result.error || `HTTP ${response.status}`));
      error.code = result.error;
      throw error;
    }
    return result;
  }

  const uploadForm = document.getElementById("upload-form");
  if (uploadForm) {
    const input = document.getElementById("demo-file");
    const dropZone = document.getElementById("drop-zone");
    const feedback = document.getElementById("upload-feedback");
    const progress = document.getElementById("upload-progress");
    const submit = document.getElementById("upload-button");
    submit.disabled = false;
    const rights = document.getElementById("upload-rights");
    const steamId = document.getElementById("player-steam-id");
    steamId.addEventListener("change", () => { steamId.value = steamId.value.trim(); });
    const storageKey = `cmt-upload-reservation-account-${uploadForm.dataset.accountId}`;
    let file = null;
    let reservation = null;
    let busy = false;
    let persistenceAvailable = true;
    try {
      const saved = JSON.parse(sessionStorage.getItem(storageKey) || "null");
      if (saved && typeof saved.request_id === "string" && typeof saved.signature === "string"
        && typeof saved.player_steam_id === "string" && /^[0-9]{17}$/.test(saved.player_steam_id)) {
        if (Date.parse(saved.expires_at) <= Date.now()) {
          sessionStorage.removeItem(storageKey);
          feedback.textContent = "Your saved upload reservation has expired. You can choose a new file and SteamID.";
        } else {
          reservation = saved;
          steamId.value = saved.player_steam_id;
          steamId.readOnly = true;
          feedback.textContent = "You have an unfinished upload. Choose the same file to continue with its original SteamID.";
        }
      }
    } catch (error) {
      persistenceAvailable = false;
      feedback.textContent = "Session storage is unavailable. Keep this page open during the upload.";
    }
    function remember(value) {
      reservation = value;
      steamId.readOnly = Boolean(value);
      if (persistenceAvailable) {
        try {
          if (value) sessionStorage.setItem(storageKey, JSON.stringify(value));
          else sessionStorage.removeItem(storageKey);
        } catch (error) {
          persistenceAvailable = false;
          feedback.textContent = "Your upload reservation could not be saved in this browser. Keep this page open.";
        }
      }
    }
    const signature = (candidate) => JSON.stringify([
      candidate.name, candidate.size, candidate.lastModified,
    ]);
    function choose(candidate) {
      if (busy) return;
      file = candidate;
      document.getElementById("file-name").textContent = file
        ? `${file.name} / ${(file.size / 1024 ** 2).toFixed(1)} MiB` : "No file selected.";
    }
    input.addEventListener("change", () => choose(input.files[0]));
    for (const event of ["dragover", "dragleave", "drop"]) {
      dropZone.addEventListener(event, (e) => {
        e.preventDefault();
        dropZone.classList.toggle("drag-over", event === "dragover");
        if (event === "drop" && !busy) {
          if (e.dataTransfer.files.length !== 1) {
            feedback.textContent = "Choose exactly one .dem file.";
            return;
          }
          choose(e.dataTransfer.files[0]);
          // The selected File is held locally; no upload occurs until form submission.
          input.required = !file;
        }
      });
    }
    function transfer(url) {
      return new Promise((resolve, reject) => {
        const xhr = new XMLHttpRequest();
        xhr.open("PUT", url);
        xhr.timeout = 15 * 60 * 1000;
        xhr.upload.onprogress = (event) => {
          if (event.lengthComputable) {
            progress.value = event.loaded / event.total * 100;
            feedback.textContent = `Uploading demo: ${Math.floor(progress.value)}%`;
          }
        };
        xhr.onload = () => {
          if (xhr.status >= 200 && xhr.status < 300) resolve();
          else reject(new Error(`Upload failed: HTTP ${xhr.status}. Retry to refresh the upload link for this reservation.`));
        };
        xhr.onerror = () => reject(new Error("Upload failed. Check your connection and retry. If it keeps failing, ask the administrator to check storage CORS settings."));
        xhr.ontimeout = () => reject(new Error("The upload timed out. Retry this upload reservation."));
        xhr.onabort = () => reject(new Error("Upload canceled. Analysis has not started."));
        xhr.send(file);
      });
    }
    uploadForm.addEventListener("submit", async (event) => {
      event.preventDefault();
      if (busy) return;
      if (!file || !/\.dem$/i.test(file.name) || file.size < 8 || file.size > 1024 ** 3) {
        feedback.textContent = message("invalid_demo_size");
        return;
      }
      if (!rights.checked) {
        feedback.textContent = message("upload_rights_confirmation_required");
        return;
      }
      const playerSteamId = steamId.value.trim();
      if (!/^[0-9]{17}$/.test(playerSteamId)) {
        feedback.textContent = message("invalid_player_steam_id");
        steamId.focus();
        return;
      }
      steamId.value = playerSteamId;
      if (reservation && reservation.player_steam_id !== playerSteamId) {
        feedback.textContent = message("idempotency_conflict");
        return;
      }
      if (reservation && reservation.signature !== signature(file)) {
        feedback.textContent = "Your unfinished upload belongs to a different file. Choose that file or wait for the reservation to expire (24 hours).";
        return;
      }
      const newReservation = !reservation;
      if (newReservation) {
        remember({
          request_id: crypto.randomUUID(), signature: signature(file),
          player_steam_id: playerSteamId, transferred: false,
          expires_at: new Date(Date.now() + 24 * 60 * 60 * 1000).toISOString(),
        });
      }
      busy = true;
      submit.disabled = true;
      input.disabled = true;
      rights.disabled = true;
      steamId.disabled = true;
      feedback.textContent = "Checking your upload reservation and permissions…";
      let accepted = false;
      try {
        const started = await request("/backend/uploads/", {
          request_id: reservation.request_id,
          size_bytes: file.size,
          has_upload_rights: true,
          player_steam_id: reservation.player_steam_id,
        });
        accepted = true;
        if (started.state === "uploading") {
          if (!started.upload_url) {
            remember(null);
            throw new Error(message("upload_expired"));
          }
          remember({ ...reservation, expires_at: started.expires_at });
          if (!reservation.transferred) {
            progress.hidden = false;
            progress.value = 0;
            await transfer(started.upload_url);
            remember({ ...reservation, transferred: true });
          }
          feedback.textContent = "Verifying your file and queuing the analysis…";
          await request(`/backend/uploads/${started.id}/complete/`, {});
        }
        remember(null);
        window.location.assign(`/uploads/${started.id}/`);
      } catch (error) {
        if ((newReservation && !accepted && error.code === "storage_not_configured")
          || ["monthly_demo_limit", "active_upload_exists", "input_cleanup_pending",
          "verified_email_required", "invalid_player_steam_id", "upload_expired"].includes(error.code)) {
          remember(null);
        }
        feedback.textContent = error.message;
        submit.textContent = "Retry this upload";
      } finally {
        busy = false;
        submit.disabled = false;
        input.disabled = false;
        rights.disabled = false;
        steamId.disabled = false;
      }
    });
  }

  const copy = document.getElementById("copy-command");
  if (copy) {
    copy.addEventListener("click", async () => {
      const line = document.getElementById("console-line");
      const feedback = document.getElementById("copy-feedback");
      copy.disabled = true;
      try {
        if (!navigator.clipboard?.writeText) throw new Error("clipboard_unavailable");
        await navigator.clipboard.writeText(line.value);
        feedback.textContent = "Complete line copied. Paste it once into the CS2 console in your Yprac session.";
      } catch (error) {
        line.focus();
        line.select();
        feedback.textContent = "Clipboard access is unavailable. The text is selected; copy it manually.";
      } finally {
        copy.disabled = false;
      }
    });
  }

  const job = document.getElementById("job-status");
  if (job) {
    const refresh = document.getElementById("refresh-status");
    const feedback = document.getElementById("job-feedback");
    const states = {
      uploading: "Waiting for your file",
      queued: "Queued",
      running: "Analyzing demo",
    };
    let remaining = 120;
    let timer;
    let busy = false;
    async function update() {
      if (busy) return;
      clearTimeout(timer);
      busy = true;
      refresh.disabled = true;
      try {
        const result = await request(job.dataset.statusUrl);
        if (!Object.hasOwn(states, result.state)) {
          window.location.reload();
          return;
        }
        document.getElementById("job-state").textContent = states[result.state];
        remaining -= 1;
        if (remaining > 0) {
          feedback.textContent = "Status updated. The analysis has not been restarted.";
          timer = setTimeout(update, 5000);
        } else {
          feedback.textContent = "Automatic updates have stopped. Select Refresh status to check again.";
        }
      } catch (error) {
        feedback.textContent = `${error.message} Automatic status updates have stopped.`;
      } finally {
        busy = false;
        refresh.disabled = false;
      }
    }
    refresh.addEventListener("click", () => { remaining = 120; update(); });
    timer = setTimeout(update, 5000);
    window.addEventListener("pagehide", () => clearTimeout(timer));
  }
})();
