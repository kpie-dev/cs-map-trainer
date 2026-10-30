"use strict";

(() => {
  const errors = JSON.parse(document.getElementById("ui-errors").textContent);
  const csrf = () => document.querySelector("[name=csrfmiddlewaretoken]")?.value;
  const message = (code) => errors[code] || `The action failed. Error code: ${code}`;
  function showStage(container, state) {
    const labels = {
      uploading: "Upload", verifying: "Verify file", queued: "Queued",
      running: "Processing demo", ready: "Ready",
    };
    const current = container.querySelector("[data-current-stage]");
    if (current) current.textContent = labels[state] || "Checking status";
  }

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

  async function request(url, data, timeoutMs = 60000) {
    let response;
    const controller = new AbortController();
    const timeout = setTimeout(() => controller.abort(), timeoutMs);
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
    const mode = document.getElementById("analysis-mode");
    function updateMode() {
      steamId.required = mode.value !== "team";
      steamId.hidden = mode.value === "team";
      mode.disabled = Boolean(reservation);
    }
    steamId.addEventListener("change", () => { steamId.value = steamId.value.trim(); });
    const storageKey = `cmt-upload-reservation-account-${uploadForm.dataset.accountId}`;
    let file = null;
    let reservation = null;
    let busy = false;
    let persistenceAvailable = true;
    try {
      const saved = JSON.parse(sessionStorage.getItem(storageKey) || "null");
      if (saved && typeof saved.request_id === "string" && typeof saved.signature === "string"
        && (saved.mode === "team"
          || (typeof saved.player_steam_id === "string" && /^[0-9]{17}$/.test(saved.player_steam_id)))) {
        if (Date.parse(saved.expires_at) <= Date.now()) {
          sessionStorage.removeItem(storageKey);
          feedback.textContent = "Your saved upload reservation has expired. You can choose a new file and SteamID.";
        } else {
          reservation = saved;
          if (saved.mode === "team" && !mode.querySelector('[value="team"]')) {
            mode.add(new Option("Saved team upload reservation", "team"));
          }
          mode.value = saved.mode || "individual";
          steamId.value = saved.player_steam_id || "";
          steamId.readOnly = true;
          feedback.textContent = "You have an unfinished upload. Choose the same file to continue with its original player or team roster.";
        }
      }
    } catch (error) {
      persistenceAvailable = false;
      feedback.textContent = "Session storage is unavailable. Keep this page open during the upload.";
    }
    updateMode();
    mode.addEventListener("change", updateMode);
    function remember(value) {
      reservation = value;
      steamId.readOnly = Boolean(value);
      updateMode();
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
      const analysisMode = mode.value;
      if (analysisMode === "individual" && !/^[0-9]{17}$/.test(playerSteamId)) {
        feedback.textContent = message("invalid_player_steam_id");
        steamId.focus();
        return;
      }
      steamId.value = playerSteamId;
      if (reservation && ((reservation.mode || "individual") !== analysisMode
        || (analysisMode === "individual" && reservation.player_steam_id !== playerSteamId))) {
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
          mode: analysisMode,
          ...(analysisMode === "individual" ? { player_steam_id: playerSteamId } : {}),
          transferred: false,
          expires_at: new Date(Date.now() + 24 * 60 * 60 * 1000).toISOString(),
        });
      }
      busy = true;
      const stages = document.getElementById("upload-stages");
      stages.hidden = false;
      stages.classList.remove("polling-paused");
      showStage(stages, reservation.transferred ? "verifying" : "uploading");
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
          mode: reservation.mode || "individual",
          ...(reservation.mode === "team" ? {} : { player_steam_id: reservation.player_steam_id }),
        });
        accepted = true;
        if (started.state === "uploading") {
          if (!started.upload_url) {
            remember(null);
            throw new Error(message("upload_expired"));
          }
          remember({ ...reservation, expires_at: started.expires_at, players: started.players });
          if (!reservation.transferred) {
            progress.hidden = false;
            progress.value = 0;
            await transfer(started.upload_url);
            remember({ ...reservation, transferred: true });
          }
          feedback.textContent = "Verifying your file and queuing the analysis…";
          showStage(stages, "verifying");
          progress.hidden = true;
          await request(`/backend/uploads/${started.id}/complete/`, {});
        }
        showStage(stages, started.state === "uploading" ? "queued" : started.state);
        remember(null);
        window.location.assign(`/uploads/${started.id}/`);
      } catch (error) {
        if ((newReservation && !accepted && error.code === "storage_not_configured")
          || ["monthly_demo_limit", "active_upload_exists", "input_cleanup_pending",
          "verified_email_required", "invalid_player_steam_id", "upload_expired",
          "coach_required", "team_roster_required", "invalid_analysis_mode"].includes(error.code)) {
          remember(null);
        }
        feedback.textContent = error.message;
        stages.classList.add("polling-paused");
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

  const selection = document.getElementById("selection-form");
  if (selection) {
    const choices = [...selection.querySelectorAll('input[name="group"]')];
    const count = document.getElementById("selection-count");
    const feedback = document.getElementById("selection-feedback");
    const bar = selection.querySelector(".selection-actions");
    if (typeof ResizeObserver !== "undefined") {
      new ResizeObserver(() => {
        selection.style.setProperty("--selection-bar-height", `${bar.offsetHeight + 20}px`);
      }).observe(bar);
    }
    const partialControl = (item) => selection.querySelector(`[name="partial_${item.value}"]`);
    choices.forEach((item) => {
      item.indeterminate = item.dataset.partial === "true";
      item.addEventListener("change", () => {
        const partial = partialControl(item);
        if (partial) partial.value = "clear";
        item.indeterminate = false;
      });
    });
    const selectedCount = (item) => item.checked ? Number(item.dataset.count)
      : partialControl(item)?.value === "preserve" ? Number(item.dataset.selected) : 0;
    const updateCount = () => {
      count.textContent = choices.reduce((sum, item) => sum + selectedCount(item), 0);
      document.getElementById("group-count").textContent = choices.filter(
        (item) => selectedCount(item) > 0,
      ).length;
      choices.forEach((item) => {
        item.indeterminate = !item.checked && selectedCount(item) > 0;
      });
    };
    updateCount();
    selection.addEventListener("change", updateCount);
    for (const [id, checked] of [["select-all", true], ["clear-selection", false]]) {
      const button = document.getElementById(id);
      button.hidden = false;
      button.addEventListener("click", () => {
        choices.forEach((item) => {
          item.checked = checked;
          item.indeterminate = false;
          const partial = partialControl(item);
          if (partial) partial.value = "clear";
        });
        updateCount();
      });
    }
    let downloading = false;
    selection.addEventListener("submit", async (event) => {
      const intent = event.submitter?.value || "download";
      if (downloading) { event.preventDefault(); return; }
      if (!choices.some((item) => selectedCount(item) > 0)) {
        event.preventDefault();
        feedback.textContent = message("invalid_scenario_selection");
        return;
      }
      if (intent !== "download") return;
      event.preventDefault();
      const data = new FormData(selection);
      data.set("intent", "download");
      const controls = [...selection.querySelectorAll("button, input[type=checkbox], select")];
      downloading = true;
      controls.forEach((control) => { control.disabled = true; });
      feedback.textContent = "Preparing your selected training…";
      const controller = new AbortController();
      const timeout = setTimeout(() => controller.abort(), 60000);
      try {
        const response = await fetch(selection.action, {
          method: "POST", body: data, credentials: "same-origin",
          headers: { "Accept": "application/json", "X-CSRFToken": csrf() },
          signal: controller.signal,
        });
        const type = response.headers.get("content-type") || "";
        if (!response.ok || !type.includes("application/zip")) {
          if (type.includes("application/json")) {
            const result = await response.json();
            selection.querySelectorAll(".export-failure").forEach((item) => item.remove());
            for (const id of result.scenario_ids || []) {
              const choice = choices.find((item) => item.closest(".situation").dataset.members.split(" ").includes(id));
              if (!choice) continue;
              const warning = document.createElement("p");
              warning.className = "danger export-failure";
              warning.textContent = "Cannot export a member of this group. Uncheck the group to continue.";
              choice.closest(".situation").append(warning);
            }
            throw new Error(message(result.error || `HTTP ${response.status}`));
          }
          throw new Error(`Download not confirmed (HTTP ${response.status}). Check that you are signed in, then retry.`);
        }
        const blob = await response.blob();
        const url = URL.createObjectURL(blob);
        const link = document.createElement("a");
        link.href = url;
        const disposition = response.headers.get("content-disposition") || "";
        link.download = disposition.match(/filename="([^"]+)"/)?.[1] || "training.zip";
        document.body.append(link);
        link.click();
        link.remove();
        setTimeout(() => URL.revokeObjectURL(url), 60000);
        feedback.textContent = "Selection saved. Training ZIP with CFG files download started.";
      } catch (error) {
        feedback.textContent = error.name === "AbortError"
          ? "Download timed out. Your checkboxes are unchanged; retry to confirm the selection and download."
          : `Download failed. ${error.message} Your checkboxes are unchanged; retry when ready.`;
      } finally {
        clearTimeout(timeout);
        downloading = false;
        controls.forEach((control) => { control.disabled = false; });
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
        document.getElementById("command-text").open = true;
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
      running: "Processing demo",
    };
    showStage(job, job.dataset.state);
    let deadline = performance.now() + 10 * 60 * 1000;
    let timer;
    let busy = false;
    function pause(text) {
      feedback.textContent = text;
      job.classList.add("polling-paused");
      refresh.hidden = false;
      job.setAttribute("aria-busy", "false");
    }
    async function update() {
      if (busy) return;
      clearTimeout(timer);
      if (performance.now() >= deadline) {
        pause("Automatic updates paused after 10 minutes. Retry status updates to continue; analysis is not restarted.");
        return;
      }
      busy = true;
      job.setAttribute("aria-busy", "true");
      refresh.disabled = true;
      try {
        const result = await request(
          job.dataset.statusUrl, undefined, Math.min(60000, deadline - performance.now()),
        );
        if (!Object.hasOwn(states, result.state)) {
          if (["ready", "unsupported", "failed", "expired"].includes(result.state)) {
            window.location.reload();
            return;
          }
          throw new Error("The server returned an unknown analysis state. Retry status updates to try again.");
        }
        document.getElementById("job-state").textContent = states[result.state];
        showStage(job, result.state);
        if (performance.now() < deadline) {
          feedback.textContent = "Status updated. The analysis has not been restarted.";
          timer = setTimeout(update, Math.min(2500, deadline - performance.now()));
        } else {
          pause("Automatic updates paused after 10 minutes. Retry status updates to continue; analysis is not restarted.");
        }
      } catch (error) {
        pause(performance.now() >= deadline
          ? "Automatic updates paused after 10 minutes. Retry status updates to continue; analysis is not restarted."
          : `${error.message} Automatic status updates have stopped. Retry status updates to continue.`);
      } finally {
        busy = false;
        refresh.disabled = false;
      }
    }
    refresh.addEventListener("click", () => {
      deadline = performance.now() + 10 * 60 * 1000;
      job.classList.remove("polling-paused");
      refresh.hidden = true;
      update();
    });
    job.setAttribute("aria-busy", "true");
    timer = setTimeout(update, 2500);
    window.addEventListener("pagehide", () => clearTimeout(timer));
  }
})();
