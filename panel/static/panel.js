const panelMeta = window.PANEL_META;

let panelState = null;
let analysisState = null;
let browserState = {
  targetId: null,
  mode: "file",
  currentPath: "",
};
let timelineState = {
  open: false,
  targetId: "",
  fieldKey: "",
  fieldLabel: "",
  profileName: "",
  sourceKey: "",
  sourcePath: "",
  sourceValuePath: "",
  durationSec: 0,
  videoFps: 0,
  mediaKind: "unknown",
  mode: "time",
  startSec: 0,
  endSec: 0,
  playheadSec: 0,
  playUntilSec: null,
  mediaUrl: "",
  lastPreviewFetchMs: 0,
  lastPreviewTimeSec: -1,
  drag: null,
};

function escapeHtml(value) {
  return String(value ?? "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#39;");
}

function eventElement(event) {
  const target = event?.target;
  if (target instanceof Element) {
    return target;
  }
  if (target && target.parentElement instanceof Element) {
    return target.parentElement;
  }
  return null;
}

function setNotice(message, tone = "default") {
  const bar = document.getElementById("noticeBar");
  bar.textContent = message;
  bar.dataset.tone = tone;
}

window.addEventListener("error", (event) => {
  const message = event?.error?.message || event?.message || "前端發生未預期錯誤。";
  const bar = document.getElementById("noticeBar");
  if (bar) {
    setNotice(`前端錯誤：${message}`, "error");
  }
});

window.addEventListener("unhandledrejection", (event) => {
  const reason = event?.reason;
  const message = reason?.message || String(reason || "前端 Promise 發生未處理錯誤。");
  const bar = document.getElementById("noticeBar");
  if (bar) {
    setNotice(`前端錯誤：${message}`, "error");
  }
});

function fieldId(section, key) {
  return `field-${section}-${key}`;
}

function profileFieldId(index, key) {
  return `profile-${index}-${key.replaceAll(".", "-")}`;
}

function formatSecondsToken(value) {
  const total = Number(value);
  if (!Number.isFinite(total)) {
    return String(value ?? "");
  }

  const hours = Math.floor(total / 3600);
  const minutes = Math.floor((total % 3600) / 60);
  const seconds = total % 60;
  const secText = seconds.toFixed(3).padStart(6, "0").replace(/\.?0+$/, (match) => (match === ".000" ? "" : match));

  if (hours > 0) {
    return `${String(hours).padStart(2, "0")}:${String(minutes).padStart(2, "0")}:${secText.padStart(2, "0")}`;
  }
  return `${String(minutes).padStart(2, "0")}:${secText.padStart(2, "0")}`;
}

function formatRangeToken(start, end) {
  return `${formatSecondsToken(start)}-${formatSecondsToken(end)}`;
}

function isTimeLikeKey(key) {
  return /(?:_times|_ranges|_source_ranges)$/.test(String(key || ""));
}

function resolveTimeSourceKey(fieldKey) {
  return fieldKey === "mechanical.water_source_ranges" ? "mechanical_audio" : "main_video";
}

function timeEditorMarkup(targetId, fieldKey, fieldLabel) {
  return `
    <div
      class="time-editor"
      data-target="${escapeHtml(targetId)}"
      data-field-key="${escapeHtml(fieldKey || "")}"
      data-field-label="${escapeHtml(fieldLabel || "")}"
      data-selected-index=""
    >
      <div class="time-chip-list" data-role="chips"></div>
      <div class="time-editor-form">
        <input class="time-editor-start" type="text" placeholder="起點，例如 00:12.500">
        <input class="time-editor-end" type="text" placeholder="終點（留空＝時間點）">
      </div>
      <div class="time-editor-actions">
        <button class="time-editor-add-point" data-target="${escapeHtml(targetId)}" type="button">加入時間點</button>
        <button class="time-editor-add-range" data-target="${escapeHtml(targetId)}" type="button">加入時間段</button>
        <button class="time-editor-update" data-target="${escapeHtml(targetId)}" type="button">覆蓋所選</button>
        <button class="time-editor-delete" data-target="${escapeHtml(targetId)}" type="button">刪除所選</button>
      </div>
      <div class="time-editor-actions secondary">
        <button class="time-editor-nudge" data-target="${escapeHtml(targetId)}" data-delta="-0.5" type="button">-0.5s</button>
        <button class="time-editor-nudge" data-target="${escapeHtml(targetId)}" data-delta="-0.1" type="button">-0.1s</button>
        <button class="time-editor-nudge" data-target="${escapeHtml(targetId)}" data-delta="0.1" type="button">+0.1s</button>
        <button class="time-editor-nudge" data-target="${escapeHtml(targetId)}" data-delta="0.5" type="button">+0.5s</button>
        <button class="time-editor-open-timeline" data-target="${escapeHtml(targetId)}" type="button">時間軸調整</button>
        <button class="time-editor-sort" data-target="${escapeHtml(targetId)}" type="button">排序</button>
        <button class="time-editor-clear" data-target="${escapeHtml(targetId)}" type="button">清空</button>
      </div>
      <div class="time-editor-hint">點上方標籤可編輯；選取後可用 ±0.1 / ±0.5 秒微調，也可以開時間軸直接拖拉。</div>
    </div>
  `;
}

function splitTimeTokens(value) {
  return String(value ?? "")
    .split(/[\n,;]+/)
    .map((item) => item.trim())
    .filter(Boolean);
}

function parseTimeTextToSeconds(value) {
  const text = String(value ?? "").trim();
  if (!text) {
    return null;
  }

  if (/^\d+(?:\.\d+)?$/.test(text)) {
    return Number(text);
  }

  const parts = text.split(":").map((item) => item.trim());
  if (!parts.length || parts.length > 3 || parts.some((item) => !/^\d+(?:\.\d+)?$/.test(item))) {
    return null;
  }

  if (parts.length === 3) {
    return Number(parts[0]) * 3600 + Number(parts[1]) * 60 + Number(parts[2]);
  }
  if (parts.length === 2) {
    return Number(parts[0]) * 60 + Number(parts[1]);
  }
  return Number(parts[0]);
}

function parseTimeEntry(token) {
  const raw = String(token ?? "").trim();
  if (!raw) {
    return null;
  }

  const dashIndex = raw.indexOf("-");
  if (dashIndex > 0 && dashIndex < raw.length - 1) {
    const startRaw = raw.slice(0, dashIndex).trim();
    const endRaw = raw.slice(dashIndex + 1).trim();
    const startSec = parseTimeTextToSeconds(startRaw);
    const endSec = parseTimeTextToSeconds(endRaw);
    if (startSec !== null && endSec !== null) {
      return {
        kind: "range",
        startSec: Math.min(startSec, endSec),
        endSec: Math.max(startSec, endSec),
        raw,
      };
    }
  }

  const timeSec = parseTimeTextToSeconds(raw);
  if (timeSec !== null) {
    return {
      kind: "time",
      startSec: timeSec,
      raw,
    };
  }

  return {
    kind: "raw",
    raw,
  };
}

function parseTimeEntries(value) {
  return splitTimeTokens(value)
    .map((token) => parseTimeEntry(token))
    .filter(Boolean);
}

function serializeTimeEntry(entry) {
  if (!entry) {
    return "";
  }
  if (entry.kind === "range") {
    return formatRangeToken(entry.startSec, entry.endSec);
  }
  if (entry.kind === "time") {
    return formatSecondsToken(entry.startSec);
  }
  return String(entry.raw || "").trim();
}

function getTimeEditor(targetId) {
  return document.querySelector(`.time-editor[data-target="${targetId}"]`);
}

function getTimeEditorEntries(targetId) {
  const textarea = document.getElementById(targetId);
  return textarea ? parseTimeEntries(textarea.value) : [];
}

function setTimeEditorInputs(editor, entry) {
  const startInput = editor.querySelector(".time-editor-start");
  const endInput = editor.querySelector(".time-editor-end");
  if (!startInput || !endInput) {
    return;
  }

  if (!entry) {
    startInput.value = "";
    endInput.value = "";
    editor.dataset.selectedIndex = "";
    return;
  }

  if (entry.kind === "range") {
    startInput.value = formatSecondsToken(entry.startSec);
    endInput.value = formatSecondsToken(entry.endSec);
  } else if (entry.kind === "time") {
    startInput.value = formatSecondsToken(entry.startSec);
    endInput.value = "";
  } else {
    startInput.value = entry.raw || "";
    endInput.value = "";
  }
}

function syncTimeEditorForTextarea(textarea) {
  if (!textarea || textarea.dataset.timeEditor !== "true") {
    return;
  }

  const editor = getTimeEditor(textarea.id);
  if (!editor) {
    return;
  }

  const chipsHost = editor.querySelector('[data-role="chips"]');
  if (!chipsHost) {
    return;
  }

  const entries = parseTimeEntries(textarea.value);
  const selectedIndex = Number.parseInt(editor.dataset.selectedIndex || "", 10);
  const activeIndex = Number.isInteger(selectedIndex) && selectedIndex >= 0 && selectedIndex < entries.length
    ? selectedIndex
    : -1;
  editor.dataset.selectedIndex = activeIndex >= 0 ? String(activeIndex) : "";

  if (!entries.length) {
    chipsHost.innerHTML = `<div class="time-chip empty">目前還沒有時間項目。</div>`;
    if (activeIndex === -1) {
      const startInput = editor.querySelector(".time-editor-start");
      const endInput = editor.querySelector(".time-editor-end");
      if (startInput && endInput && !startInput.matches(":focus") && !endInput.matches(":focus")) {
        startInput.value = "";
        endInput.value = "";
      }
    }
    bindInteractiveButtons(editor);
    return;
  }

  chipsHost.innerHTML = entries.map((entry, index) => {
    const selected = index === activeIndex ? " selected" : "";
    const invalid = entry.kind === "raw" ? " invalid" : "";
    return `
      <button
        class="time-chip${selected}${invalid}"
        data-target="${escapeHtml(textarea.id)}"
        data-index="${index}"
        type="button"
      >${escapeHtml(serializeTimeEntry(entry))}</button>
    `;
  }).join("");

  if (activeIndex >= 0) {
    setTimeEditorInputs(editor, entries[activeIndex]);
  }
  bindInteractiveButtons(editor);
}

function syncAllTimeEditors() {
  document.querySelectorAll('textarea[data-time-editor="true"]').forEach((textarea) => {
    syncTimeEditorForTextarea(textarea);
  });
}

function writeTimeEntries(targetId, entries, nextSelectedIndex = null) {
  const textarea = document.getElementById(targetId);
  const editor = getTimeEditor(targetId);
  if (!textarea || !editor) {
    return;
  }

  textarea.value = entries
    .map((entry) => serializeTimeEntry(entry))
    .filter(Boolean)
    .join(", ");

  if (nextSelectedIndex === null || nextSelectedIndex === undefined || nextSelectedIndex < 0 || nextSelectedIndex >= entries.length) {
    editor.dataset.selectedIndex = "";
  } else {
    editor.dataset.selectedIndex = String(nextSelectedIndex);
  }
  syncTimeEditorForTextarea(textarea);
}

function createTimeEntryFromInputs(editor, mode = "point") {
  const startRaw = editor.querySelector(".time-editor-start")?.value.trim() || "";
  const endRaw = editor.querySelector(".time-editor-end")?.value.trim() || "";
  if (!startRaw) {
    throw new Error("請先填起點時間。");
  }

  const startSec = parseTimeTextToSeconds(startRaw);
  if (startSec === null) {
    throw new Error(`起點格式不正確：${startRaw}`);
  }

  if (mode === "range" || endRaw) {
    if (!endRaw) {
      throw new Error("時間段需要終點時間。");
    }
    const endSec = parseTimeTextToSeconds(endRaw);
    if (endSec === null) {
      throw new Error(`終點格式不正確：${endRaw}`);
    }
    return {
      kind: "range",
      startSec: Math.min(startSec, endSec),
      endSec: Math.max(startSec, endSec),
    };
  }

  return {
    kind: "time",
    startSec,
  };
}

function selectTimeEditorEntry(targetId, index) {
  const editor = getTimeEditor(targetId);
  if (!editor) {
    return;
  }

  const entries = getTimeEditorEntries(targetId);
  if (!entries.length || index < 0 || index >= entries.length) {
    editor.dataset.selectedIndex = "";
    setTimeEditorInputs(editor, null);
  } else {
    editor.dataset.selectedIndex = String(index);
    setTimeEditorInputs(editor, entries[index]);
  }

  const textarea = document.getElementById(targetId);
  if (textarea) {
    syncTimeEditorForTextarea(textarea);
    flashField(textarea);
  }
}

function addTimeEditorEntry(targetId, mode) {
  const editor = getTimeEditor(targetId);
  if (!editor) {
    return;
  }

  const nextEntry = createTimeEntryFromInputs(editor, mode);
  const entries = getTimeEditorEntries(targetId);
  const nextToken = serializeTimeEntry(nextEntry);
  const existingIndex = entries.findIndex((entry) => serializeTimeEntry(entry) === nextToken);
  if (existingIndex >= 0) {
    selectTimeEditorEntry(targetId, existingIndex);
    return;
  }
  entries.push(nextEntry);
  writeTimeEntries(targetId, entries, entries.length - 1);
}

function updateTimeEditorEntry(targetId) {
  const editor = getTimeEditor(targetId);
  if (!editor) {
    return;
  }

  const selectedIndex = Number.parseInt(editor.dataset.selectedIndex || "", 10);
  if (!Number.isInteger(selectedIndex) || selectedIndex < 0) {
    throw new Error("請先點選一個時間項目再覆蓋。");
  }

  const entries = getTimeEditorEntries(targetId);
  if (selectedIndex >= entries.length) {
    throw new Error("目前沒有可覆蓋的時間項目。");
  }

  entries[selectedIndex] = createTimeEntryFromInputs(editor, editor.querySelector(".time-editor-end")?.value.trim() ? "range" : "point");
  writeTimeEntries(targetId, entries, selectedIndex);
}

function deleteTimeEditorEntry(targetId) {
  const editor = getTimeEditor(targetId);
  if (!editor) {
    return;
  }

  const selectedIndex = Number.parseInt(editor.dataset.selectedIndex || "", 10);
  if (!Number.isInteger(selectedIndex) || selectedIndex < 0) {
    throw new Error("請先點選要刪除的時間項目。");
  }

  const entries = getTimeEditorEntries(targetId);
  entries.splice(selectedIndex, 1);
  const nextIndex = Math.min(selectedIndex, entries.length - 1);
  writeTimeEntries(targetId, entries, nextIndex >= 0 ? nextIndex : null);
}

function nudgeTimeEditor(targetId, delta) {
  const editor = getTimeEditor(targetId);
  if (!editor) {
    return;
  }

  const selectedIndex = Number.parseInt(editor.dataset.selectedIndex || "", 10);
  const entries = getTimeEditorEntries(targetId);
  if (Number.isInteger(selectedIndex) && selectedIndex >= 0 && selectedIndex < entries.length) {
    const entry = entries[selectedIndex];
    if (entry.kind === "raw") {
      throw new Error("這個項目不是可辨識時間，無法微調。");
    }

    const startSec = Math.max(0, entry.startSec + delta);
    if (entry.kind === "range") {
      const duration = Math.max(0, entry.endSec - entry.startSec);
      entries[selectedIndex] = {
        kind: "range",
        startSec,
        endSec: startSec + duration,
      };
    } else {
      entries[selectedIndex] = {
        kind: "time",
        startSec,
      };
    }
    writeTimeEntries(targetId, entries, selectedIndex);
    return;
  }

  const startInput = editor.querySelector(".time-editor-start");
  const endInput = editor.querySelector(".time-editor-end");
  if (!startInput) {
    return;
  }

  const startSec = parseTimeTextToSeconds(startInput.value);
  if (startSec === null) {
    throw new Error("請先填一個可辨識的起點時間，或先選一個時間項目。");
  }
  startInput.value = formatSecondsToken(Math.max(0, startSec + delta));

  if (endInput && endInput.value.trim()) {
    const endSec = parseTimeTextToSeconds(endInput.value);
    if (endSec !== null) {
      endInput.value = formatSecondsToken(Math.max(0, endSec + delta));
    }
  }
}

function sortTimeEditorEntries(targetId) {
  const entries = getTimeEditorEntries(targetId);
  const sortable = entries.every((entry) => entry.kind !== "raw");
  if (!sortable) {
    throw new Error("有無法辨識的原始文字，請先修正後再排序。");
  }

  entries.sort((left, right) => {
    if (left.startSec !== right.startSec) {
      return left.startSec - right.startSec;
    }
    const leftEnd = left.kind === "range" ? left.endSec : left.startSec;
    const rightEnd = right.kind === "range" ? right.endSec : right.startSec;
    return leftEnd - rightEnd;
  });
  writeTimeEntries(targetId, entries, null);
}

function clearTimeEditorEntries(targetId) {
  writeTimeEntries(targetId, [], null);
}

function profileNameForTargetId(targetId) {
  const element = document.getElementById(targetId);
  const profileCard = element ? element.closest(".profile-card") : null;
  if (!profileCard) {
    return "";
  }
  const index = Number(profileCard.dataset.profileIndex);
  if (!Number.isInteger(index) || index < 0 || index >= (panelState?.profiles || []).length) {
    return "";
  }
  return panelState.profiles[index]?.name || "";
}

function activeEntryForTarget(targetId) {
  const editor = getTimeEditor(targetId);
  const entries = getTimeEditorEntries(targetId);
  if (!editor || !entries.length) {
    return null;
  }
  const selectedIndex = Number.parseInt(editor.dataset.selectedIndex || "", 10);
  if (!Number.isInteger(selectedIndex) || selectedIndex < 0 || selectedIndex >= entries.length) {
    return null;
  }
  const entry = entries[selectedIndex];
  return entry && entry.kind !== "raw" ? { entry, index: selectedIndex } : null;
}

async function fetchMediaInfo({ sourceKey = "", profileName = "", path = "" } = {}) {
  const query = new URLSearchParams();
  if (sourceKey) {
    query.set("source_key", sourceKey);
  }
  if (profileName) {
    query.set("profile", profileName);
  }
  if (path) {
    query.set("path", path);
  }
  return fetchJson(`/api/media/info?${query.toString()}`);
}

function timelineMediaQuery({ sourceKey = "", profileName = "", path = "" } = {}) {
  const query = new URLSearchParams();
  if (sourceKey) {
    query.set("source_key", sourceKey);
  }
  if (profileName) {
    query.set("profile", profileName);
  }
  if (path) {
    query.set("path", path);
  }
  return query.toString();
}

function currentTimelineMediaElement() {
  if (timelineState.mediaKind === "video") {
    return document.getElementById("timelineVideoPlayer");
  }
  if (timelineState.mediaKind === "audio") {
    return document.getElementById("timelineAudioPlayer");
  }
  return null;
}

function updateTimelinePlaybackText() {
  const text = document.getElementById("timelinePlaybackText");
  const playPauseButton = document.getElementById("timelinePlayPauseButton");
  const media = currentTimelineMediaElement();
  const current = media ? Number(media.currentTime || 0) : Number(timelineState.playheadSec || 0);
  const total = media && Number.isFinite(media.duration) && media.duration > 0
    ? Number(media.duration)
    : Number(timelineState.durationSec || 0);
  text.textContent = `${formatSecondsToken(current)} / ${formatSecondsToken(total)}`;
  playPauseButton.textContent = media && !media.paused ? "暫停" : "播放";
}

function maybeRefreshTimelinePreview(previewTimeSec = timelineState.playheadSec, { force = false, reason = "目前位置" } = {}) {
  if (!timelineState.open || timelineState.mediaKind !== "video") {
    return;
  }

  const safeTime = Math.max(0, Number(previewTimeSec || 0));
  const now = Date.now();
  if (!force) {
    const recentEnough = now - Number(timelineState.lastPreviewFetchMs || 0) < 220;
    const tinyMove = Math.abs(Number(timelineState.lastPreviewTimeSec || 0) - safeTime) < 0.18;
    if (recentEnough || tinyMove) {
      return;
    }
  }

  timelineState.lastPreviewFetchMs = now;
  timelineState.lastPreviewTimeSec = safeTime;
  renderTimelinePreview({ previewTimeSec: safeTime, reason });
}

function setTimelinePlayhead(sec) {
  timelineState.playheadSec = Math.max(0, Math.min(Number(timelineState.durationSec || 0), Number(sec || 0)));
  const playhead = document.getElementById("timelinePlayhead");
  playhead.style.left = `${timelinePercent(timelineState.playheadSec)}%`;
  updateTimelinePlaybackText();
}

function setupTimelineMediaPreview() {
  const video = document.getElementById("timelineVideoPlayer");
  const audio = document.getElementById("timelineAudioPlayer");
  const empty = document.getElementById("timelinePlayerEmpty");
  const meta = document.getElementById("timelinePlayerMeta");

  video.pause();
  audio.pause();
  video.classList.add("hidden");
  audio.classList.add("hidden");

  if (!timelineState.mediaUrl) {
    empty.classList.remove("hidden");
    meta.textContent = "目前沒有可播放的媒體。";
    setTimelinePlayhead(0);
    return;
  }

  if (timelineState.mediaKind === "video") {
    empty.classList.add("hidden");
    video.classList.remove("hidden");
    if (video.dataset.src !== timelineState.mediaUrl) {
      video.src = timelineState.mediaUrl;
      video.dataset.src = timelineState.mediaUrl;
      video.load();
    }
    meta.textContent = "可直接播放影片，配合時間軸拖拉調整。";
  } else if (timelineState.mediaKind === "audio") {
    empty.classList.add("hidden");
    audio.classList.remove("hidden");
    if (audio.dataset.src !== timelineState.mediaUrl) {
      audio.src = timelineState.mediaUrl;
      audio.dataset.src = timelineState.mediaUrl;
      audio.load();
    }
    meta.textContent = "可直接播放音訊，配合波形與時間軸調整。";
  } else {
    empty.classList.remove("hidden");
    meta.textContent = "這個來源目前沒有可播放的媒體。";
  }
  setTimelinePlayhead(timelineState.startSec);
  timelineState.lastPreviewFetchMs = 0;
  timelineState.lastPreviewTimeSec = -1;
}

function pauseTimelineMedia() {
  const media = currentTimelineMediaElement();
  if (!media) {
    return;
  }
  media.pause();
  timelineState.playUntilSec = null;
  updateTimelinePlaybackText();
}

function seekTimelineMedia(sec = timelineState.startSec) {
  const media = currentTimelineMediaElement();
  const clamped = Math.max(0, Math.min(Number(timelineState.durationSec || 0), Number(sec || 0)));
  setTimelinePlayhead(clamped);
  if (!media) {
    return;
  }
  if (Number.isFinite(media.duration) && media.duration > 0) {
    media.currentTime = clamped;
  } else {
    media.dataset.pendingSeek = String(clamped);
  }
}

async function playTimelineMedia({ fromStart = false, limitToSelection = false } = {}) {
  const media = currentTimelineMediaElement();
  if (!media) {
    throw new Error("目前沒有可播放的媒體。");
  }

  const playStart = fromStart ? timelineState.startSec : (media.currentTime || timelineState.startSec);
  if (fromStart) {
    seekTimelineMedia(playStart);
  }
  timelineState.playUntilSec = limitToSelection && timelineState.mode === "range" ? timelineState.endSec : null;
  await media.play();
  updateTimelinePlaybackText();
}

async function toggleTimelinePlayback() {
  const media = currentTimelineMediaElement();
  if (!media) {
    throw new Error("目前沒有可播放的媒體。");
  }
  if (media.paused) {
    await playTimelineMedia({ fromStart: false, limitToSelection: false });
  } else {
    pauseTimelineMedia();
  }
}

function openTimelineModalShell() {
  document.getElementById("timelineModal").classList.remove("hidden");
}

function closeTimelineModal() {
  timelineState.open = false;
  timelineState.drag = null;
  timelineState.playUntilSec = null;
  timelineState.lastPreviewFetchMs = 0;
  timelineState.lastPreviewTimeSec = -1;
  pauseTimelineMedia();
  document.getElementById("timelineModal").classList.add("hidden");
}

function timelinePercent(sec) {
  if (!timelineState.durationSec || !Number.isFinite(timelineState.durationSec)) {
    return 0;
  }
  return Math.max(0, Math.min(100, (sec / timelineState.durationSec) * 100));
}

function setTimelinePreview(src, metaText) {
  const image = document.getElementById("timelinePreviewImage");
  const empty = document.getElementById("timelinePreviewEmpty");
  const meta = document.getElementById("timelinePreviewMeta");
  image.src = src;
  image.classList.remove("hidden");
  empty.classList.add("hidden");
  meta.textContent = metaText;
}

function resetTimelinePreview(message, metaText = "拖拉時間軸後會更新目前位置。") {
  const image = document.getElementById("timelinePreviewImage");
  const empty = document.getElementById("timelinePreviewEmpty");
  const meta = document.getElementById("timelinePreviewMeta");
  image.src = "";
  image.classList.add("hidden");
  empty.textContent = message;
  empty.classList.remove("hidden");
  meta.textContent = metaText;
}

function renderTimelineFilmstrip() {
  const host = document.getElementById("timelineFilmstrip");
  if (timelineState.mediaKind !== "video" || !timelineState.durationSec) {
    host.innerHTML = "";
    host.classList.add("waveform-mode");
    return;
  }

  host.classList.remove("waveform-mode");
  const frameCount = 6;
  const profileQuery = timelineState.profileName ? `&profile=${encodeURIComponent(timelineState.profileName)}` : "";
  host.innerHTML = Array.from({ length: frameCount }, (_, index) => {
    const ratio = frameCount === 1 ? 0 : index / (frameCount - 1);
    const timeSec = timelineState.durationSec * ratio;
    return `
      <div class="timeline-thumb">
        <img src="/api/preview/frame?time=${encodeURIComponent(timeSec.toFixed(3))}${profileQuery}" alt="timeline thumb ${index + 1}">
        <span>${escapeHtml(formatSecondsToken(timeSec))}</span>
      </div>
    `;
  }).join("");
}

function renderTimelinePreview({ previewTimeSec = null, reason = "目前位置" } = {}) {
  if (!timelineState.open) {
    return;
  }

  if (timelineState.mediaKind === "audio") {
    const query = new URLSearchParams({
      path: timelineState.sourcePath,
      _: String(Date.now()),
    });
    setTimelinePreview(`/api/preview/waveform?${query.toString()}`, `${timelineState.sourceValuePath} | 波形預覽`);
    document.getElementById("timelinePreviewTitle").textContent = "波形預覽";
    return;
  }

  document.getElementById("timelinePreviewTitle").textContent = "目前位置預覽";
  const media = currentTimelineMediaElement();
  const defaultTime = media && !media.paused
    ? Number(media.currentTime || timelineState.startSec)
    : Number(timelineState.startSec || 0);
  const previewTime = Number.isFinite(Number(previewTimeSec)) ? Number(previewTimeSec) : defaultTime;
  const query = new URLSearchParams({
    time: String(previewTime),
    _: String(Date.now()),
  });
  if (timelineState.profileName) {
    query.set("profile", timelineState.profileName);
  }
  setTimelinePreview(`/api/preview/frame?${query.toString()}`, `${reason}｜${formatSecondsToken(previewTime)} | ${timelineState.sourceValuePath}`);
}

function renderTimelineOverlay() {
  const overlay = document.getElementById("timelineEntryOverlay");
  const entries = getTimeEditorEntries(timelineState.targetId).filter((entry) => entry.kind !== "raw");
  if (!timelineState.durationSec || !entries.length) {
    overlay.innerHTML = "";
    return;
  }

  overlay.innerHTML = entries.map((entry, index) => {
    if (entry.kind === "range") {
      const left = timelinePercent(entry.startSec);
      const width = Math.max(0.8, timelinePercent(entry.endSec) - left);
      return `
        <button
          class="timeline-entry-range"
          type="button"
          data-index="${index}"
          style="left:${left}%; width:${width}%;"
          title="${escapeHtml(serializeTimeEntry(entry))}"
        ></button>
      `;
    }
    const left = timelinePercent(entry.startSec);
    return `
      <button
        class="timeline-entry-dot"
        type="button"
        data-index="${index}"
        style="left:${left}%;"
        title="${escapeHtml(serializeTimeEntry(entry))}"
      ></button>
    `;
  }).join("");
  bindInteractiveButtons(overlay);
}

function syncTimelineInputs() {
  document.getElementById("timelineStartInput").value = formatSecondsToken(timelineState.startSec);
  const endInput = document.getElementById("timelineEndInput");
  const endField = document.getElementById("timelineEndField");
  const applyButton = document.getElementById("timelineApplyButton");
  if (timelineState.mode === "range") {
    endField.classList.remove("hidden");
    endInput.value = formatSecondsToken(timelineState.endSec);
    applyButton.textContent = "套用時間段";
  } else {
    endField.classList.add("hidden");
    endInput.value = "";
    applyButton.textContent = "套用時間點";
  }
}

function renderTimelineTrack() {
  const selection = document.getElementById("timelineSelection");
  const startHandle = document.getElementById("timelineStartHandle");
  const endHandle = document.getElementById("timelineEndHandle");
  const startPercent = timelinePercent(timelineState.startSec);
  const endPercent = timelinePercent(timelineState.mode === "range" ? timelineState.endSec : timelineState.startSec);

  startHandle.style.left = `${startPercent}%`;
  endHandle.style.left = `${endPercent}%`;
  document.getElementById("timelineAxisStart").textContent = "00:00";
  document.getElementById("timelineAxisMid").textContent = formatSecondsToken((timelineState.durationSec || 0) / 2);
  document.getElementById("timelineAxisEnd").textContent = formatSecondsToken(timelineState.durationSec || 0);

  if (timelineState.mode === "range") {
    endHandle.classList.remove("hidden");
    selection.classList.remove("point-mode");
    const left = Math.min(startPercent, endPercent);
    const width = Math.max(0.6, Math.abs(endPercent - startPercent));
    selection.style.left = `${left}%`;
    selection.style.width = `${width}%`;
  } else {
    endHandle.classList.add("hidden");
    selection.classList.add("point-mode");
    selection.style.left = `${startPercent}%`;
    selection.style.width = "0.8%";
  }

  syncTimelineInputs();
  renderTimelineOverlay();
}

function setTimelineRange(startSec, endSec = startSec, { keepDuration = false } = {}) {
  const duration = Math.max(0, Number(timelineState.durationSec) || 0);
  if (timelineState.mode === "time") {
    const clamped = Math.max(0, Math.min(duration, Number(startSec) || 0));
    timelineState.startSec = clamped;
    timelineState.endSec = clamped;
    renderTimelineTrack();
    return;
  }

  let nextStart = Math.max(0, Math.min(duration, Number(startSec) || 0));
  let nextEnd = Math.max(0, Math.min(duration, Number(endSec) || 0));
  if (keepDuration) {
    const span = Math.max(0, timelineState.endSec - timelineState.startSec);
    nextEnd = Math.min(duration, nextStart + span);
    if (nextEnd - nextStart < span) {
      nextStart = Math.max(0, nextEnd - span);
    }
  }
  if (nextStart > nextEnd) {
    [nextStart, nextEnd] = [nextEnd, nextStart];
  }
  timelineState.startSec = nextStart;
  timelineState.endSec = nextEnd;
  renderTimelineTrack();
}

function timelineTimeFromClientX(clientX) {
  const track = document.getElementById("timelineTrack");
  const rect = track.getBoundingClientRect();
  const ratio = rect.width ? Math.max(0, Math.min(1, (clientX - rect.left) / rect.width)) : 0;
  return ratio * (timelineState.durationSec || 0);
}

function selectTimelineEntry(index) {
  selectTimeEditorEntry(timelineState.targetId, index);
  const active = activeEntryForTarget(timelineState.targetId);
  if (!active) {
    return;
  }
  if (active.entry.kind === "range") {
    timelineState.mode = "range";
    setTimelineRange(active.entry.startSec, active.entry.endSec);
  } else {
    timelineState.mode = "time";
    setTimelineRange(active.entry.startSec, active.entry.startSec);
  }
  renderTimelinePreview();
}

function loadSelectedIntoTimeline() {
  const active = activeEntryForTarget(timelineState.targetId);
  if (!active) {
    throw new Error("目前欄位沒有已選取的時間項目。");
  }
  if (active.entry.kind === "range") {
    timelineState.mode = "range";
    setTimelineRange(active.entry.startSec, active.entry.endSec);
  } else {
    timelineState.mode = "time";
    setTimelineRange(active.entry.startSec, active.entry.startSec);
  }
  renderTimelinePreview();
}

function applyTimelineToField() {
  const editor = getTimeEditor(timelineState.targetId);
  if (!editor) {
    throw new Error("找不到對應欄位。");
  }
  const entry = timelineState.mode === "range"
    ? { kind: "range", startSec: timelineState.startSec, endSec: timelineState.endSec }
    : { kind: "time", startSec: timelineState.startSec };

  const selectedIndex = Number.parseInt(editor.dataset.selectedIndex || "", 10);
  const entries = getTimeEditorEntries(timelineState.targetId);
  if (Number.isInteger(selectedIndex) && selectedIndex >= 0 && selectedIndex < entries.length && entries[selectedIndex].kind !== "raw") {
    entries[selectedIndex] = entry;
    writeTimeEntries(timelineState.targetId, entries, selectedIndex);
  } else {
    const nextToken = serializeTimeEntry(entry);
    const exists = entries.findIndex((item) => serializeTimeEntry(item) === nextToken);
    if (exists >= 0) {
      writeTimeEntries(timelineState.targetId, entries, exists);
    } else {
      entries.push(entry);
      writeTimeEntries(timelineState.targetId, entries, entries.length - 1);
    }
  }
  renderTimelineOverlay();
}

function renderTimelineMeta() {
  document.getElementById("timelineTitle").textContent = `時間軸調整｜${timelineState.fieldLabel || "時間欄位"}`;
  document.getElementById("timelineMeta").textContent = timelineState.profileName
    ? `${timelineState.profileName}｜${timelineState.sourceValuePath}`
    : timelineState.sourceValuePath;
  document.getElementById("timelineSourceChip").textContent = `來源：${timelineState.sourceValuePath || timelineState.sourceKey || "-"}`;
  document.getElementById("timelineDurationChip").textContent = `長度：${formatSecondsToken(timelineState.durationSec || 0)}`;
}

async function openTimelineModal(targetId) {
  const editor = getTimeEditor(targetId);
  const textarea = document.getElementById(targetId);
  if (!editor || !textarea) {
    throw new Error("找不到要編輯的時間欄位。");
  }

  const fieldKey = editor.dataset.fieldKey || "";
  const fieldLabel = editor.dataset.fieldLabel || "時間欄位";
  const profileName = profileNameForTargetId(targetId);
  const sourceKey = resolveTimeSourceKey(fieldKey);
  const mode = fieldKey.endsWith("_ranges") || fieldKey.endsWith("_source_ranges") ? "range" : "time";
  const mediaInfo = await fetchMediaInfo({ sourceKey, profileName });

  timelineState = {
    open: true,
    targetId,
    fieldKey,
    fieldLabel,
    profileName,
    sourceKey,
    sourcePath: mediaInfo.path,
    sourceValuePath: mediaInfo.value_path || mediaInfo.path,
    durationSec: Number(mediaInfo.duration_sec || 0),
    videoFps: Number(mediaInfo.video_fps || 0),
    mediaKind: mediaInfo.media_kind || "unknown",
    mode,
    startSec: 0,
    endSec: 0,
    playheadSec: 0,
    playUntilSec: null,
    mediaUrl: `/api/media/file?${timelineMediaQuery({ sourceKey, profileName })}`,
    lastPreviewFetchMs: 0,
    lastPreviewTimeSec: -1,
    drag: null,
  };

  const active = activeEntryForTarget(targetId);
  if (active) {
    if (active.entry.kind === "range") {
      timelineState.mode = "range";
      timelineState.startSec = active.entry.startSec;
      timelineState.endSec = active.entry.endSec;
    } else {
      timelineState.mode = "time";
      timelineState.startSec = active.entry.startSec;
      timelineState.endSec = active.entry.startSec;
    }
  } else {
    const initialEntries = getTimeEditorEntries(targetId).filter((entry) => entry.kind !== "raw");
    const firstEntry = initialEntries[0] || null;
    if (firstEntry?.kind === "range") {
      timelineState.mode = "range";
      timelineState.startSec = firstEntry.startSec;
      timelineState.endSec = firstEntry.endSec;
    } else if (firstEntry?.kind === "time") {
      timelineState.mode = "time";
      timelineState.startSec = firstEntry.startSec;
      timelineState.endSec = firstEntry.startSec;
    } else {
      timelineState.startSec = 0;
      timelineState.endSec = Math.min(timelineState.durationSec || 0, 1.0);
    }
  }

  renderTimelineMeta();
  setupTimelineMediaPreview();
  renderTimelineFilmstrip();
  renderTimelineTrack();
  seekTimelineMedia(timelineState.startSec);
  renderTimelinePreview({ previewTimeSec: timelineState.startSec, reason: "起點" });
  openTimelineModalShell();
}

function timelineShortcutIntent(event) {
  if (!timelineState.open) {
    return null;
  }
  const active = document.activeElement;
  if (active && active.closest && !active.closest("#timelineModal")) {
    return null;
  }
  if (active && active.matches("input, textarea, select, button, summary, [contenteditable='true']")) {
    return null;
  }
  if (event.code === "Space") {
    return event.repeat ? null : { type: "toggle" };
  }
  if (event.code === "ArrowLeft" || event.code === "ArrowRight") {
    return {
      type: "nudge",
      deltaSec: (event.code === "ArrowLeft" ? -1 : 1) * (event.shiftKey ? 1.0 : 0.1),
      label: event.shiftKey ? "大步移動" : "微調",
    };
  }
  if (event.code === "Comma" || event.code === "Period") {
    return {
      type: "fine_nudge",
      deltaSec: (event.code === "Comma" ? -1 : 1) * timelineFineStepSec(),
      label: timelineState.mediaKind === "video" ? "逐格微調" : "細步微調",
    };
  }
  if (event.code === "Home") {
    return { type: "jump", edge: "start" };
  }
  if (event.code === "End") {
    return { type: "jump", edge: "end" };
  }
  return null;
}

function nudgeTimelineSelection(deltaSec) {
  const amount = Number(deltaSec || 0);
  if (!amount) {
    return;
  }
  pauseTimelineMedia();
  if (timelineState.mode === "range") {
    setTimelineRange(timelineState.startSec + amount, timelineState.endSec + amount, { keepDuration: true });
  } else {
    const nextTime = timelineState.startSec + amount;
    setTimelineRange(nextTime, nextTime);
  }
  seekTimelineMedia(timelineState.startSec);
  renderTimelinePreview({ previewTimeSec: timelineState.startSec, reason: "快捷微調" });
}

function timelineFineStepSec() {
  if (timelineState.mediaKind === "video") {
    const fps = Number(timelineState.videoFps || 0);
    return fps > 0 ? 1 / fps : (1 / 30);
  }
  return 0.02;
}

function jumpTimelineSelection(edge = "start") {
  pauseTimelineMedia();
  const targetSec = edge === "end" && timelineState.mode === "range"
    ? timelineState.endSec
    : timelineState.startSec;
  seekTimelineMedia(targetSec);
  renderTimelinePreview({ previewTimeSec: targetSec, reason: edge === "end" ? "終點" : "起點" });
}

function beginTimelineDrag(mode, clientX) {
  timelineState.drag = {
    mode,
    anchorTime: timelineTimeFromClientX(clientX),
    originStart: timelineState.startSec,
    originEnd: timelineState.endSec,
  };
}

function handleTimelinePointerMove(clientX) {
  if (!timelineState.drag) {
    return;
  }

  const pointerTime = timelineTimeFromClientX(clientX);
  if (timelineState.drag.mode === "point") {
    setTimelineRange(pointerTime, pointerTime);
    return;
  }
  if (timelineState.drag.mode === "start") {
    setTimelineRange(Math.min(pointerTime, timelineState.endSec), timelineState.endSec);
    return;
  }
  if (timelineState.drag.mode === "end") {
    setTimelineRange(timelineState.startSec, Math.max(pointerTime, timelineState.startSec));
    return;
  }
  if (timelineState.drag.mode === "selection") {
    const span = Math.max(0, timelineState.drag.originEnd - timelineState.drag.originStart);
    let nextStart = timelineState.drag.originStart + (pointerTime - timelineState.drag.anchorTime);
    if (nextStart < 0) {
      nextStart = 0;
    }
    if (nextStart + span > timelineState.durationSec) {
      nextStart = Math.max(0, timelineState.durationSec - span);
    }
    setTimelineRange(nextStart, nextStart + span);
  }
}

function endTimelineDrag() {
  timelineState.drag = null;
}

function updateTimelineFromInputs() {
  const startValue = document.getElementById("timelineStartInput").value.trim();
  const endValue = document.getElementById("timelineEndInput").value.trim();
  const startSec = parseTimeTextToSeconds(startValue);
  if (startSec === null) {
    throw new Error(`起點格式不正確：${startValue || "(空白)"}`);
  }

  if (timelineState.mode === "range") {
    const endSec = parseTimeTextToSeconds(endValue);
    if (endSec === null) {
      throw new Error(`終點格式不正確：${endValue || "(空白)"}`);
    }
    setTimelineRange(startSec, endSec);
  } else {
    setTimelineRange(startSec, startSec);
  }
}

function actionButtonMarkup(action) {
  const attrs = Object.entries(action.dataset || {})
    .map(([key, value]) => `data-${escapeHtml(key)}="${escapeHtml(value)}"`)
    .join(" ");
  return `
    <button
      class="${escapeHtml(action.className || "action-button")}"
      type="button"
      ${attrs}
    >${escapeHtml(action.label)}</button>
  `;
}

function rowMarkup(values, actions = []) {
  if (!actions.length) {
    return `<div class="table-row">${values.map((value) => `<div>${escapeHtml(value)}</div>`).join("")}</div>`;
  }

  return `
    <div class="table-row actions">
      <div class="table-values">${values.map((value) => `<div>${escapeHtml(value)}</div>`).join("")}</div>
      <div class="row-actions">${actions.map((action) => actionButtonMarkup(action)).join("")}</div>
    </div>
  `;
}

function emptyMarkup(text) {
  return `<div class="table-row empty">${escapeHtml(text)}</div>`;
}

function currentAnalysisProfile() {
  const select = document.getElementById("analysisTargetSelect");
  return select ? select.value.trim() : "";
}

function resolveTargetElement(targetKey) {
  const profileName = currentAnalysisProfile();
  const profileAware = panelMeta.profileFields.some((field) => field.key === targetKey);
  if (profileName && profileAware) {
    const profileIndex = panelState.profiles.findIndex((profile) => profile.name === profileName);
    if (profileIndex >= 0) {
      return document.getElementById(profileFieldId(profileIndex, targetKey));
    }
  }

  const [section, key] = targetKey.split(".", 2);
  if (!section || !key) {
    return null;
  }
  return document.getElementById(fieldId(section, key));
}

function textControlMarkup(id, value, browseMode) {
  const input = `<input id="${id}" type="text" value="${escapeHtml(value ?? "")}">`;
  if (!browseMode) {
    return input;
  }

  return `
    <div class="field-control">
      ${input}
      <button
        class="browse-trigger browse-button"
        type="button"
        data-target="${escapeHtml(id)}"
        data-mode="${escapeHtml(browseMode)}"
      >瀏覽</button>
    </div>
  `;
}

function inputMarkup(section, field, value) {
  const id = fieldId(section, field.key);
  const safeValue = value ?? "";
  const help = field.help ? `<div class="field-help">${field.help}</div>` : "";

  if (field.type === "checkbox") {
    const checked = String(safeValue).toLowerCase() === "true" ? "checked" : "";
    return `
      <div class="field">
        <label>${escapeHtml(field.label)}</label>
        <label class="checkbox-field" for="${id}">
          <input id="${id}" type="checkbox" ${checked}>
          <span>${escapeHtml(field.label)}</span>
        </label>
        ${help}
      </div>
    `;
  }

  if (field.type === "select") {
    const options = (field.options || []).map((option) => {
      const selected = String(safeValue) === option ? "selected" : "";
      return `<option value="${escapeHtml(option)}" ${selected}>${escapeHtml(option || "(留空)")}</option>`;
    }).join("");
    return `
      <div class="field">
        <label for="${id}">${escapeHtml(field.label)}</label>
        <select id="${id}">${options}</select>
        ${help}
      </div>
    `;
  }

  if (field.type === "textarea") {
    if (isTimeLikeKey(field.key)) {
      return `
        <div class="field full time-field">
          <label>${escapeHtml(field.label)}</label>
          ${timeEditorMarkup(id, `${section}.${field.key}`, field.label)}
          <details class="time-raw-toggle">
            <summary>原始文字（可直接貼上 / 手動編輯）</summary>
            <textarea id="${id}" data-time-editor="true">${escapeHtml(safeValue)}</textarea>
          </details>
          ${help}
        </div>
      `;
    }
    return `
      <div class="field full">
        <label for="${id}">${escapeHtml(field.label)}</label>
        <textarea id="${id}">${escapeHtml(safeValue)}</textarea>
        ${help}
      </div>
    `;
  }

  return `
    <div class="field">
      <label for="${id}">${escapeHtml(field.label)}</label>
      ${textControlMarkup(id, safeValue, field.browse)}
      ${help}
    </div>
  `;
}

function profileFieldMarkup(index, field, value) {
  const id = profileFieldId(index, field.key);
  const safeValue = value ?? "";

  if (field.type === "select") {
    const options = (field.options || []).map((option) => {
      const selected = String(safeValue) === option ? "selected" : "";
      return `<option value="${escapeHtml(option)}" ${selected}>${escapeHtml(option || "(沿用全域)")}</option>`;
    }).join("");
    return `
      <div class="field">
        <label for="${id}">${escapeHtml(field.label)}</label>
        <select id="${id}">${options}</select>
      </div>
    `;
  }

  if (field.type === "textarea") {
    if (isTimeLikeKey(field.key)) {
      return `
        <div class="field full time-field">
          <label>${escapeHtml(field.label)}</label>
          ${timeEditorMarkup(id, field.key, field.label)}
          <details class="time-raw-toggle">
            <summary>原始文字（可直接貼上 / 手動編輯）</summary>
            <textarea id="${id}" data-time-editor="true">${escapeHtml(safeValue)}</textarea>
          </details>
        </div>
      `;
    }
    return `
      <div class="field full">
        <label for="${id}">${escapeHtml(field.label)}</label>
        <textarea id="${id}">${escapeHtml(safeValue)}</textarea>
      </div>
    `;
  }

  return `
    <div class="field">
      <label for="${id}">${escapeHtml(field.label)}</label>
      ${textControlMarkup(id, safeValue, field.browse)}
    </div>
  `;
}

function renderBaseSections() {
  const host = document.getElementById("baseSections");
  host.innerHTML = panelMeta.sectionOrder.map((section) => {
    const fields = panelMeta.baseFields[section] || [];
    const values = panelState.base[section] || {};
    const inputs = fields.map((field) => inputMarkup(section, field, values[field.key])).join("");
    return `
      <div class="section-card">
        <h3>${escapeHtml(panelMeta.sectionTitles[section] || section)}</h3>
        <div class="fields-grid">${inputs}</div>
      </div>
    `;
  }).join("");
  syncAllTimeEditors();
  bindInteractiveButtons(host);
}

function renderProfiles() {
  const host = document.getElementById("profilesContainer");
  if (!panelState.profiles.length) {
    host.innerHTML = `<div class="table-row empty">目前沒有 profile，可以先按「快速建立 main1/main2/main3」。</div>`;
    refreshSelectors();
    return;
  }

  host.innerHTML = panelState.profiles.map((profile, index) => {
    const fields = panelMeta.profileFields.map((field) => profileFieldMarkup(index, field, profile.values[field.key])).join("");
    return `
      <article class="profile-card" data-profile-index="${index}">
        <div class="profile-head">
          <div class="profile-name">
            <label for="profile-name-${index}">Profile 名稱</label>
            <input id="profile-name-${index}" type="text" value="${escapeHtml(profile.name || "")}">
          </div>
          <button class="danger remove-profile-button" data-index="${index}" type="button">刪除</button>
        </div>
        <div class="fields-grid">${fields}</div>
      </article>
    `;
  }).join("");

  host.querySelectorAll(".remove-profile-button").forEach((button) => {
    button.addEventListener("click", () => {
      captureStateFromDom();
      const index = Number(button.dataset.index);
      panelState.profiles.splice(index, 1);
      renderProfiles();
    });
  });

  refreshSelectors();
  syncAllTimeEditors();
  bindInteractiveButtons(host);
}

function readFieldValue(field, element) {
  if (field.type === "checkbox") {
    return element.checked ? "true" : "false";
  }
  return element.value.trim();
}

function captureStateFromDom() {
  if (!panelState) {
    return;
  }

  panelMeta.sectionOrder.forEach((section) => {
    const target = panelState.base[section] || {};
    (panelMeta.baseFields[section] || []).forEach((field) => {
      const element = document.getElementById(fieldId(section, field.key));
      if (element) {
        target[field.key] = readFieldValue(field, element);
      }
    });
    panelState.base[section] = target;
  });

  panelState.profiles = panelState.profiles.map((profile, index) => {
    const nameElement = document.getElementById(`profile-name-${index}`);
    const values = {};
    panelMeta.profileFields.forEach((field) => {
      const element = document.getElementById(profileFieldId(index, field.key));
      values[field.key] = element ? readFieldValue(field, element) : "";
    });
    return {
      name: nameElement ? nameElement.value.trim() : profile.name,
      values,
    };
  }).filter((profile) => profile.name);
}

function refreshSelectors() {
  const profileSelect = document.getElementById("runProfileSelect");
  const analysisSelect = document.getElementById("analysisTargetSelect");
  const clipProfileSelect = document.getElementById("clipProfileSelect");
  const currentProfile = profileSelect.value;
  const currentAnalysisTarget = analysisSelect.value;
  const currentClipProfile = clipProfileSelect ? clipProfileSelect.value : "";

  const profileOptions = [`<option value="">請選擇 Profile</option>`].concat(
    panelState.profiles.map((profile) => `<option value="${escapeHtml(profile.name)}">${escapeHtml(profile.name)}</option>`)
  );
  profileSelect.innerHTML = profileOptions.join("");
  profileSelect.value = panelState.profiles.some((profile) => profile.name === currentProfile) ? currentProfile : "";

  const targets = panelState.analysisTargets || [{ value: "", label: "目前設定" }];
  analysisSelect.innerHTML = targets.map((target) => {
    const selected = target.value === currentAnalysisTarget || (!currentAnalysisTarget && target.value === "") ? "selected" : "";
    return `<option value="${escapeHtml(target.value)}" ${selected}>${escapeHtml(target.label)}</option>`;
  }).join("");

  if (clipProfileSelect) {
    const clipOptions = [`<option value="">目前設定</option>`].concat(
      panelState.profiles.map((profile) => `<option value="${escapeHtml(profile.name)}">${escapeHtml(profile.name)}</option>`)
    );
    clipProfileSelect.innerHTML = clipOptions.join("");
    clipProfileSelect.value = panelState.profiles.some((profile) => profile.name === currentClipProfile) ? currentClipProfile : "";
  }
}

function resolveConfigFileValue(fileKey, profileName = "") {
  if (!panelState) {
    return "";
  }
  const baseFiles = panelState.base.files || {};
  if (profileName) {
    const profile = panelState.profiles.find((item) => item.name === profileName);
    const overrideKey = `files.${fileKey}`;
    if (profile && profile.values && profile.values[overrideKey]) {
      return profile.values[overrideKey];
    }
  }
  return baseFiles[fileKey] || "";
}

function syncClipSourcePath(force = false) {
  const presetSelect = document.getElementById("clipSourcePreset");
  const profileSelect = document.getElementById("clipProfileSelect");
  const sourceInput = document.getElementById("clipSourcePath");
  if (!presetSelect || !sourceInput) {
    return;
  }

  const preset = presetSelect.value;
  if (preset === "custom") {
    return;
  }

  if (!force && sourceInput.dataset.locked === "custom") {
    return;
  }

  sourceInput.value = resolveConfigFileValue(preset, profileSelect ? profileSelect.value : "");
  sourceInput.dataset.locked = "";
}

function defaultClipOutputName() {
  const preset = document.getElementById("clipSourcePreset")?.value || "clip";
  const start = document.getElementById("clipStartTime")?.value.trim() || "start";
  const end = document.getElementById("clipEndTime")?.value.trim() || "end";
  const clean = `${preset}_${start}_${end}`
    .replaceAll(":", "-")
    .replaceAll(".", "_")
    .replaceAll("/", "-")
    .replaceAll("\\", "-")
    .replaceAll(" ", "");
  return clean;
}

function setClipRange(startValue, endValue, sourcePreset = null, profileName = null) {
  const startInput = document.getElementById("clipStartTime");
  const endInput = document.getElementById("clipEndTime");
  const presetSelect = document.getElementById("clipSourcePreset");
  const profileSelect = document.getElementById("clipProfileSelect");

  if (startInput) {
    startInput.value = startValue;
    flashField(startInput);
  }
  if (endInput) {
    endInput.value = endValue;
  }
  if (profileSelect && profileName !== null) {
    profileSelect.value = profileName;
  }
  if (presetSelect && sourcePreset) {
    presetSelect.value = sourcePreset;
    syncClipSourcePath(true);
  }

  const outputName = document.getElementById("clipOutputName");
  if (outputName && !outputName.value.trim()) {
    outputName.value = defaultClipOutputName();
  }
}

function renderClipExportResult(result = null) {
  const host = document.getElementById("clipExportResult");
  if (!host) {
    return;
  }
  if (!result) {
    host.innerHTML = emptyMarkup("尚未輸出片段。");
    return;
  }
  host.innerHTML = rowMarkup([
    result.output_kind === "audio" ? "音訊" : "影片",
    `${formatSecondsToken(result.start_sec)} - ${formatSecondsToken(result.end_sec)}`,
    result.output_value_path || result.output_path,
  ]);
}

function renderClipExportList(data = null) {
  const host = document.getElementById("clipExportList");
  if (!host) {
    return;
  }

  if (!data || !(data.items || []).length) {
    host.innerHTML = emptyMarkup("目前輸出資料夾沒有片段。");
    return;
  }

  host.innerHTML = data.items.map((item) => rowMarkup(
    [
      item.name,
      `${Math.max(1, Math.round(item.size_bytes / 1024))} KB`,
      item.modified_at,
      item.value_path,
    ]
  )).join("");
}

async function exportClipSegment() {
  const sourcePath = document.getElementById("clipSourcePath").value.trim();
  const outputDir = document.getElementById("clipOutputDir").value.trim() || "output/clips";
  const outputNameInput = document.getElementById("clipOutputName");
  const outputName = outputNameInput.value.trim() || defaultClipOutputName();
  const outputKind = document.getElementById("clipOutputKind").value;
  const startTime = document.getElementById("clipStartTime").value.trim();
  const endTime = document.getElementById("clipEndTime").value.trim();

  if (!sourcePath || !startTime || !endTime) {
    throw new Error("請先填好來源、開始時間、結束時間。");
  }

  outputNameInput.value = outputName;

  const result = await fetchJson("/api/export/segment", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      source_path: sourcePath,
      output_dir: outputDir,
      output_name: outputName,
      output_kind: outputKind,
      start_time: startTime,
      end_time: endTime,
    }),
  });
  renderClipExportResult(result);
  await refreshClipExportList();
  setNotice(`已輸出到 ${result.output_value_path || result.output_path}`, "success");
}

async function refreshClipExportList() {
  const outputDir = document.getElementById("clipOutputDir").value.trim() || "output/clips";
  const query = new URLSearchParams({ dir: outputDir });
  const data = await fetchJson(`/api/export/list?${query.toString()}`);
  renderClipExportList(data);
}

async function openClipOutputFolder() {
  const outputDir = document.getElementById("clipOutputDir").value.trim() || "output/clips";
  await fetchJson("/api/open-folder", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ path: outputDir }),
  });
  setNotice(`已開啟資料夾 ${outputDir}`, "success");
}

function renderStatus(status) {
  const chip = document.getElementById("runStateChip");
  const logView = document.getElementById("logView");

  if (status.running) {
    chip.textContent = "執行中";
    chip.style.background = "rgba(15, 118, 110, 0.14)";
    chip.style.color = "#115e59";
  } else if (status.exit_code === 0) {
    chip.textContent = "完成";
    chip.style.background = "rgba(15, 118, 110, 0.14)";
    chip.style.color = "#115e59";
  } else if (status.exit_code !== null && status.exit_code !== undefined) {
    chip.textContent = `失敗 (${status.exit_code})`;
    chip.style.background = "rgba(180, 35, 24, 0.12)";
    chip.style.color = "#b42318";
  } else {
    chip.textContent = "等待中";
    chip.style.background = "";
    chip.style.color = "";
  }

  logView.textContent = status.log || "";
  logView.scrollTop = logView.scrollHeight;
}

function renderAnalysis(analysis) {
  analysisState = analysis;
  resetPreviewState("frame", "尚未選擇縮圖預覽。");
  resetPreviewState("wave", "尚未選擇波形預覽。");

  document.getElementById("waterCount").textContent = analysis.water_events.length;
  document.getElementById("flashHoldCount").textContent = analysis.flash_holds.length;
  document.getElementById("shutterCount").textContent = analysis.shutter_candidates.length;
  document.getElementById("mechanicalWaterCount").textContent = analysis.mechanical_water.length;

  document.getElementById("waterEventsTable").innerHTML = analysis.water_events.length
    ? analysis.water_events.map((item) => rowMarkup(
        [
          `start ${formatSecondsToken(item.start_sec)}`,
          `end ${formatSecondsToken(item.end_sec)}`,
          `peak ${formatSecondsToken(item.peak_time_sec)}`,
          `score ${item.peak_score}`,
        ],
        [
          {
            label: "看縮圖",
            className: "preview-frame-button",
            dataset: {
              time: String(item.peak_time_sec),
            label: `Motion/SFX Event @ ${formatSecondsToken(item.peak_time_sec)}`,
            },
          },
          {
            label: "加到水聲時間點",
            className: "time-insert-button",
            dataset: { target: "insert.water_times", value: formatSecondsToken(item.peak_time_sec) },
          },
          {
            label: "加到水聲時間段",
            className: "time-insert-button",
            dataset: { target: "insert.water_ranges", value: formatRangeToken(item.start_sec, item.end_sec) },
          },
          {
            label: "設為擷取段",
            className: "set-clip-range-button",
            dataset: {
              start: formatSecondsToken(item.start_sec),
              end: formatSecondsToken(item.end_sec),
              source: "main_video",
            },
          },
        ]
      )).join("")
    : emptyMarkup("目前沒有 motion / sfx events。");

  document.getElementById("flashHoldsTable").innerHTML = analysis.flash_holds.length
    ? analysis.flash_holds.map((item) => rowMarkup(
        [
          `start ${formatSecondsToken(item.start_sec)}`,
          `end ${formatSecondsToken(item.end_sec)}`,
          `dur ${item.duration_sec}`,
          `white ${item.max_white_ratio}`,
        ],
        [
          {
            label: "看縮圖",
            className: "preview-frame-button",
            dataset: {
              time: String(item.start_sec),
              label: `Flash Hold @ ${formatSecondsToken(item.start_sec)}`,
            },
          },
          {
            label: "加到閃光時間段",
            className: "time-insert-button",
            dataset: { target: "insert.shutter_ranges", value: formatRangeToken(item.start_sec, item.end_sec) },
          },
          {
            label: "設為擷取段",
            className: "set-clip-range-button",
            dataset: {
              start: formatSecondsToken(item.start_sec),
              end: formatSecondsToken(item.end_sec),
              source: "main_video",
            },
          },
        ]
      )).join("")
    : emptyMarkup("目前沒有長白閃。");

  document.getElementById("shutterCandidatesTable").innerHTML = analysis.shutter_candidates.length
    ? analysis.shutter_candidates.map((item) => {
        const actions = [
          {
            label: "看縮圖",
            className: "preview-frame-button",
            dataset: {
              time: String(item.start_sec),
              label: `Shutter Candidate @ ${formatSecondsToken(item.start_sec)}`,
            },
          },
          {
            label: "加到閃光時間點",
            className: "time-insert-button",
            dataset: { target: "insert.shutter_times", value: formatSecondsToken(item.start_sec) },
          },
          {
            label: "設為擷取段",
            className: "set-clip-range-button",
            dataset: {
              start: formatSecondsToken(item.start_sec),
              end: formatSecondsToken(item.end_sec),
              source: "main_video",
            },
          },
        ];
        if (Number(item.end_sec) > Number(item.start_sec)) {
          actions.push({
            label: "加到閃光時間段",
            className: "time-insert-button",
            dataset: { target: "insert.shutter_ranges", value: formatRangeToken(item.start_sec, item.end_sec) },
          });
        }
        return rowMarkup(
          [
            `style ${item.shutter_style || "-"}`,
            `start ${formatSecondsToken(item.start_sec)}`,
            `end ${formatSecondsToken(item.end_sec)}`,
            `count ${item.count ?? 0}`,
          ],
          actions,
        );
      }).join("")
    : emptyMarkup("目前沒有快門候選。");

  document.getElementById("mechanicalWaterTable").innerHTML = analysis.mechanical_water.length
    ? analysis.mechanical_water.map((item) => rowMarkup(
        [
          item.path.split("\\").pop(),
          `src ${formatSecondsToken(item.src_start_sec)}-${formatSecondsToken(item.src_end_sec)}`,
          `dur ${item.duration_sec}`,
        ],
        [
          {
            label: "看波形",
            className: "preview-wave-button",
            dataset: {
              path: item.path,
              label: `${item.path.split("\\").pop()} | ${formatSecondsToken(item.src_start_sec)}-${formatSecondsToken(item.src_end_sec)}`,
            },
          },
          {
            label: "加到機械 / 循環音切割",
            className: "time-insert-button",
            dataset: {
              target: "mechanical.water_source_ranges",
              value: formatRangeToken(item.src_start_sec, item.src_end_sec),
            },
          },
          {
            label: "設為擷取段",
            className: "set-clip-range-button",
            dataset: {
              start: formatSecondsToken(item.src_start_sec),
              end: formatSecondsToken(item.src_end_sec),
              source: "mechanical_audio",
            },
          },
        ]
      )).join("")
    : emptyMarkup("目前沒有切好的機械 / 循環音片段。");

  const trackEntries = Object.entries(analysis.track_counts || {});
  document.getElementById("trackCountsTable").innerHTML = trackEntries.length
    ? trackEntries.map(([name, count]) => rowMarkup([name, String(count)])).join("")
    : emptyMarkup("尚未產生 timeline。");

  bindInteractiveButtons();
}

function flashField(targetOrElement) {
  const element = typeof targetOrElement === "string" ? document.getElementById(targetOrElement) : targetOrElement;
  if (!element) {
    return;
  }

  const wrapper = element.closest(".field");
  if (wrapper) {
    wrapper.classList.remove("flash-target");
    void wrapper.offsetWidth;
    wrapper.classList.add("flash-target");
  }
  element.focus();
  element.scrollIntoView({ behavior: "smooth", block: "center" });
}

function appendTokenToField(targetKey, token) {
  const element = resolveTargetElement(targetKey);
  if (!element) {
    setNotice("找不到要寫入的欄位。", "error");
    return;
  }

  const nextToken = String(token ?? "").trim();
  if (!nextToken) {
    return;
  }

  const current = element.value.trim();
  const parts = current ? current.split(",").map((item) => item.trim()).filter(Boolean) : [];
  if (!parts.includes(nextToken)) {
    parts.push(nextToken);
  }
  element.value = parts.join(", ");
  syncTimeEditorForTextarea(element);
  flashField(element);
}

function setPreviewState(type, src, metaText) {
  const image = document.getElementById(type === "frame" ? "framePreviewImage" : "wavePreviewImage");
  const empty = document.getElementById(type === "frame" ? "framePreviewEmpty" : "wavePreviewEmpty");
  const meta = document.getElementById(type === "frame" ? "framePreviewMeta" : "wavePreviewMeta");

  image.src = src;
  image.classList.remove("hidden");
  empty.classList.add("hidden");
  meta.textContent = metaText;
}

function previewFrame(timeSec, label) {
  const query = new URLSearchParams({
    time: String(timeSec),
    _: String(Date.now()),
  });
  const profile = currentAnalysisProfile();
  if (profile) {
    query.set("profile", profile);
  }
  setPreviewState("frame", `/api/preview/frame?${query.toString()}`, label);
}

function previewWaveform(pathValue, label) {
  const query = new URLSearchParams({
    path: pathValue,
    _: String(Date.now()),
  });
  setPreviewState("wave", `/api/preview/waveform?${query.toString()}`, label);
}

function resetPreviewState(type, message) {
  const image = document.getElementById(type === "frame" ? "framePreviewImage" : "wavePreviewImage");
  const empty = document.getElementById(type === "frame" ? "framePreviewEmpty" : "wavePreviewEmpty");
  const meta = document.getElementById(type === "frame" ? "framePreviewMeta" : "wavePreviewMeta");
  image.src = "";
  image.classList.add("hidden");
  empty.textContent = message;
  empty.classList.remove("hidden");
  meta.textContent = type === "frame"
    ? "選擇 motion / flash / shutter 項目後可查看主影片畫面。"
    : "選擇 mechanical segment 項目後可查看音訊波形。";
}

async function fetchJson(url, options = {}) {
  const response = await fetch(url, options);
  const data = await response.json();
  if (!response.ok) {
    throw new Error(data.message || "Request failed");
  }
  return data;
}

function openBrowserModal() {
  document.getElementById("browserModal").classList.remove("hidden");
}

function closeBrowserModal() {
  document.getElementById("browserModal").classList.add("hidden");
}

async function handleBrowseTrigger(button, event = null) {
  if (event) {
    event.preventDefault();
    event.stopPropagation();
  }
  await openBrowser(button.dataset.target, button.dataset.mode || "file");
}

function bindBrowseTriggers(root = document) {
  root.querySelectorAll(".browse-trigger").forEach((button) => {
    if (button.dataset.browseBound === "1") {
      return;
    }
    button.dataset.browseBound = "1";
    button.addEventListener("click", async (event) => {
      try {
        await handleBrowseTrigger(button, event);
      } catch (error) {
        setNotice(error.message, "error");
      }
    });
  });
}

function bindBrowserEntryActions(root = document) {
  root.querySelectorAll(".browser-open-button").forEach((button) => {
    if (button.dataset.browserBound === "1") {
      return;
    }
    button.dataset.browserBound = "1";
    button.addEventListener("click", async (event) => {
      event.preventDefault();
      event.stopPropagation();
      try {
        await loadBrowser(button.dataset.path);
      } catch (error) {
        setNotice(error.message, "error");
      }
    });
  });

  root.querySelectorAll(".browser-choose-button").forEach((button) => {
    if (button.dataset.browserBound === "1") {
      return;
    }
    button.dataset.browserBound = "1";
    button.addEventListener("click", (event) => {
      event.preventDefault();
      event.stopPropagation();
      applyBrowserSelection(button.dataset.valuePath);
    });
  });

  root.querySelectorAll(".browser-shortcut-button").forEach((button) => {
    if (button.dataset.browserBound === "1") {
      return;
    }
    button.dataset.browserBound = "1";
    button.addEventListener("click", async (event) => {
      event.preventDefault();
      event.stopPropagation();
      try {
        await loadBrowser(button.dataset.path);
      } catch (error) {
        setNotice(error.message, "error");
      }
    });
  });
}

function bindInteractiveButtons(root = document) {
  bindBrowseTriggers(root);
  bindBrowserEntryActions(root);

  root.querySelectorAll(".preview-frame-button").forEach((button) => {
    if (button.dataset.previewFrameBound === "1") {
      return;
    }
    button.dataset.previewFrameBound = "1";
    button.addEventListener("click", (event) => {
      event.preventDefault();
      event.stopPropagation();
      previewFrame(button.dataset.time, button.dataset.label || "縮圖預覽");
    });
  });

  root.querySelectorAll(".preview-wave-button").forEach((button) => {
    if (button.dataset.previewWaveBound === "1") {
      return;
    }
    button.dataset.previewWaveBound = "1";
    button.addEventListener("click", (event) => {
      event.preventDefault();
      event.stopPropagation();
      previewWaveform(button.dataset.path, button.dataset.label || "波形預覽");
    });
  });

  root.querySelectorAll(".set-clip-range-button").forEach((button) => {
    if (button.dataset.clipRangeBound === "1") {
      return;
    }
    button.dataset.clipRangeBound = "1";
    button.addEventListener("click", (event) => {
      event.preventDefault();
      event.stopPropagation();
      setClipRange(
        button.dataset.start,
        button.dataset.end,
        button.dataset.source || null,
        currentAnalysisProfile(),
      );
      setNotice(`已設定擷取區間 ${button.dataset.start} - ${button.dataset.end}`, "success");
    });
  });

  root.querySelectorAll(".time-insert-button").forEach((button) => {
    if (button.dataset.timeInsertBound === "1") {
      return;
    }
    button.dataset.timeInsertBound = "1";
    button.addEventListener("click", (event) => {
      event.preventDefault();
      event.stopPropagation();
      appendTokenToField(button.dataset.target, button.dataset.value);
      const profile = currentAnalysisProfile();
      const profileAware = panelMeta.profileFields.some((field) => field.key === button.dataset.target);
      const scope = profile && profileAware ? `到 ${profile}` : "到全域設定";
      setNotice(`已帶入 ${button.dataset.value} ${scope}`, "success");
    });
  });

  root.querySelectorAll(".time-chip").forEach((button) => {
    if (button.dataset.timeChipBound === "1") {
      return;
    }
    button.dataset.timeChipBound = "1";
    button.addEventListener("click", (event) => {
      if (button.classList.contains("empty")) {
        return;
      }
      event.preventDefault();
      event.stopPropagation();
      selectTimeEditorEntry(button.dataset.target, Number(button.dataset.index));
      setNotice(`已選取 ${button.textContent}，可以直接微調。`, "success");
    });
  });

  root.querySelectorAll(
    ".time-editor-add-point, .time-editor-add-range, .time-editor-update, .time-editor-delete, .time-editor-nudge, .time-editor-open-timeline, .time-editor-sort, .time-editor-clear",
  ).forEach((button) => {
    if (button.dataset.timeActionBound === "1") {
      return;
    }
    button.dataset.timeActionBound = "1";
    button.addEventListener("click", async (event) => {
      event.preventDefault();
      event.stopPropagation();
      const targetId = button.dataset.target;
      try {
        if (button.classList.contains("time-editor-add-point")) {
          addTimeEditorEntry(targetId, "point");
          setNotice("已加入時間點。", "success");
        } else if (button.classList.contains("time-editor-add-range")) {
          addTimeEditorEntry(targetId, "range");
          setNotice("已加入時間段。", "success");
        } else if (button.classList.contains("time-editor-update")) {
          updateTimeEditorEntry(targetId);
          setNotice("已覆蓋所選時間。", "success");
        } else if (button.classList.contains("time-editor-delete")) {
          deleteTimeEditorEntry(targetId);
          setNotice("已刪除所選時間。", "success");
        } else if (button.classList.contains("time-editor-nudge")) {
          nudgeTimeEditor(targetId, Number(button.dataset.delta || 0));
          setNotice(`已微調 ${button.dataset.delta}s。`, "success");
        } else if (button.classList.contains("time-editor-open-timeline")) {
          await openTimelineModal(targetId);
          setNotice("已開啟時間軸調整。", "success");
        } else if (button.classList.contains("time-editor-sort")) {
          sortTimeEditorEntries(targetId);
          setNotice("已依時間排序。", "success");
        } else if (button.classList.contains("time-editor-clear")) {
          clearTimeEditorEntries(targetId);
          setNotice("已清空這個欄位的時間項目。", "success");
        }
      } catch (error) {
        setNotice(error.message, "error");
      }
    });
  });

  root.querySelectorAll(".timeline-entry-dot, .timeline-entry-range").forEach((button) => {
    if (button.dataset.timelineEntryBound === "1") {
      return;
    }
    button.dataset.timelineEntryBound = "1";
    button.addEventListener("click", (event) => {
      event.preventDefault();
      event.stopPropagation();
      selectTimelineEntry(Number(button.dataset.index));
      seekTimelineMedia(timelineState.startSec);
      renderTimelinePreview({ previewTimeSec: timelineState.startSec, reason: "起點" });
      setNotice("已載入時間軸上的既有項目。", "success");
    });
  });
}

async function loadBrowser(pathValue = "") {
  const query = new URLSearchParams({
    mode: browserState.mode,
  });
  if (pathValue) {
    query.set("path", pathValue);
  }

  const data = await fetchJson(`/api/fs?${query.toString()}`);
  browserState.currentPath = data.currentPath;

  document.getElementById("browserTitle").textContent = browserState.mode === "dir" ? "選擇資料夾" : "選擇檔案";
  document.getElementById("browserPath").textContent = data.currentValuePath || data.currentPath;

  const parentButton = document.getElementById("browserParentButton");
  parentButton.disabled = !data.parentPath;
  parentButton.dataset.path = data.parentPath || "";

  const chooseCurrentButton = document.getElementById("browserChooseCurrentButton");
  chooseCurrentButton.dataset.path = data.currentValuePath || data.currentPath;
  chooseCurrentButton.classList.toggle("hidden", browserState.mode !== "dir");

  document.getElementById("browserShortcuts").innerHTML = (data.shortcuts || []).map((shortcut) => `
    <button
      class="browser-shortcut-button"
      type="button"
      data-path="${escapeHtml(shortcut.path)}"
    >${escapeHtml(shortcut.label)}</button>
  `).join("");

  const entries = data.entries || [];
  document.getElementById("browserEntries").innerHTML = entries.length
    ? entries.map((entry) => {
        const openButton = entry.isDir ? `
          <button
            class="browser-open-button"
            type="button"
            data-path="${escapeHtml(entry.path)}"
          >打開</button>
        ` : "";
        const chooseButton = (!entry.isDir && browserState.mode === "file") || (entry.isDir && browserState.mode === "dir")
          ? `
            <button
              class="browser-choose-button"
              type="button"
              data-value-path="${escapeHtml(entry.valuePath)}"
            >選用</button>
          `
          : "";
        return `
          <div class="browser-row">
            <div class="browser-meta">
              <div class="browser-name">${escapeHtml(entry.name)}${entry.isDir ? " /" : ""}</div>
              <div class="browser-path">${escapeHtml(entry.valuePath)}</div>
            </div>
            <div class="browser-actions">
              ${openButton}
              ${chooseButton}
            </div>
          </div>
        `;
      }).join("")
    : emptyMarkup("這個資料夾沒有可選項目。");

  bindBrowserEntryActions();
}

async function openBrowser(targetId, mode) {
  browserState = {
    targetId,
    mode,
    currentPath: "",
  };
  const target = document.getElementById(targetId);
  const currentValue = target ? target.value.trim() : "";
  openBrowserModal();
  await loadBrowser(currentValue);
}

function applyBrowserSelection(valuePath) {
  const target = document.getElementById(browserState.targetId);
  if (!target) {
    setNotice("找不到要寫入路徑的欄位。", "error");
    return;
  }
  if (browserState.targetId === "clipSourcePath") {
    document.getElementById("clipSourcePreset").value = "custom";
    target.dataset.locked = "custom";
  }
  target.value = valuePath;
  flashField(browserState.targetId);
  closeBrowserModal();
  setNotice(`已選擇：${valuePath}`, "success");
}

async function loadState() {
  const data = await fetchJson("/api/state");
  panelState = data.config;
  panelState.analysisTargets = data.analysisTargets;
  renderBaseSections();
  renderProfiles();
  renderClipExportResult(null);
  renderStatus(data.status);
  syncClipSourcePath(true);
  await refreshClipExportList();
  await refreshAnalysis();
}

async function saveConfig(silent = false) {
  captureStateFromDom();
  const data = await fetchJson("/api/config", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(panelState),
  });
  panelState = data.config;
  panelState.analysisTargets = data.analysisTargets;
  renderBaseSections();
  renderProfiles();
  if (!silent) {
    setNotice(data.message, "success");
  }
}

async function runPipeline(mode) {
  await saveConfig(true);

  let payload = { mode };
  if (mode === "profile") {
    const profileName = document.getElementById("runProfileSelect").value;
    payload = { mode, profiles: profileName ? [profileName] : [] };
  }

  const data = await fetchJson("/api/run", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  renderStatus(data.status);
  setNotice(data.message, "success");
}

async function refreshStatus() {
  try {
    const data = await fetchJson("/api/status");
    renderStatus(data);
  } catch (error) {
    setNotice(error.message, "error");
  }
}

async function refreshAnalysis() {
  try {
    const target = document.getElementById("analysisTargetSelect").value;
    const profile = target ? `?profile=${encodeURIComponent(target)}` : "";
    const data = await fetchJson(`/api/analysis${profile}`);
    renderAnalysis(data);
  } catch (error) {
    setNotice(error.message, "error");
  }
}

function addProfile(name = "") {
  captureStateFromDom();
  panelState.profiles.push({ name, values: {} });
  renderProfiles();
}

function seedProfiles() {
  captureStateFromDom();
  const existing = new Set(panelState.profiles.map((profile) => profile.name));
  ["main1", "main2", "main3"].forEach((name, index) => {
    if (existing.has(name)) {
      return;
    }
    const values = {
      "files.final_video": `output/${name}.mp4`,
      "select.voice_source": index < 2 ? "moan" : "ref",
      "select.moan_variant": index === 0 ? "1" : index === 1 ? "2" : "",
    };
    panelState.profiles.push({ name, values });
  });
  renderProfiles();
  setNotice("已幫你補上 main1 / main2 / main3 範本。", "success");
}

function bindActions() {
  bindInteractiveButtons();

  document.getElementById("saveButton").addEventListener("click", async () => {
    try {
      await saveConfig(false);
    } catch (error) {
      setNotice(error.message, "error");
    }
  });

  document.getElementById("runCurrentButton").addEventListener("click", async () => {
    try {
      await runPipeline("current");
    } catch (error) {
      setNotice(error.message, "error");
    }
  });

  document.getElementById("runProfileButton").addEventListener("click", async () => {
    try {
      await runPipeline("profile");
    } catch (error) {
      setNotice(error.message, "error");
    }
  });

  document.getElementById("runScheduleButton").addEventListener("click", async () => {
    try {
      await runPipeline("schedule");
    } catch (error) {
      setNotice(error.message, "error");
    }
  });

  document.getElementById("refreshAnalysisButton").addEventListener("click", async () => {
    await refreshAnalysis();
  });

  document.getElementById("addProfileButton").addEventListener("click", () => addProfile(""));
  document.getElementById("seedProfilesButton").addEventListener("click", seedProfiles);
  document.getElementById("exportClipButton").addEventListener("click", async () => {
    try {
      await exportClipSegment();
    } catch (error) {
      setNotice(error.message, "error");
    }
  });
  document.getElementById("refreshClipListButton").addEventListener("click", async () => {
    try {
      await refreshClipExportList();
      setNotice("已更新片段清單。", "success");
    } catch (error) {
      setNotice(error.message, "error");
    }
  });
  document.getElementById("openClipFolderButton").addEventListener("click", async () => {
    try {
      await openClipOutputFolder();
    } catch (error) {
      setNotice(error.message, "error");
    }
  });
  document.getElementById("clipSourcePreset").addEventListener("change", () => {
    syncClipSourcePath(true);
  });
  document.getElementById("clipProfileSelect").addEventListener("change", () => {
    syncClipSourcePath(true);
  });
  document.getElementById("clipOutputDir").addEventListener("change", async () => {
    try {
      await refreshClipExportList();
    } catch (error) {
      setNotice(error.message, "error");
    }
  });
  document.getElementById("clipSourcePath").addEventListener("input", () => {
    const preset = document.getElementById("clipSourcePreset").value;
    if (preset === "custom") {
      document.getElementById("clipSourcePath").dataset.locked = "custom";
    }
  });
  document.addEventListener("input", (event) => {
    if (event.target.matches('textarea[data-time-editor="true"]')) {
      syncTimeEditorForTextarea(event.target);
    }
  });

  document.getElementById("closeBrowserButton").addEventListener("click", closeBrowserModal);
  document.getElementById("closeTimelineButton").addEventListener("click", closeTimelineModal);
  document.getElementById("browserParentButton").addEventListener("click", async (event) => {
    const path = event.currentTarget.dataset.path;
    if (!path) {
      return;
    }
    await loadBrowser(path);
  });
  document.getElementById("browserChooseCurrentButton").addEventListener("click", (event) => {
    const valuePath = event.currentTarget.dataset.path;
    if (valuePath) {
      applyBrowserSelection(valuePath);
    }
  });

  document.getElementById("browserModal").addEventListener("click", (event) => {
    const target = eventElement(event);
    if (target && target.id === "browserModal") {
      closeBrowserModal();
    }
  });
  document.getElementById("timelineModal").addEventListener("click", (event) => {
    const target = eventElement(event);
    if (target && target.id === "timelineModal") {
      closeTimelineModal();
    }
  });

  document.getElementById("framePreviewImage").addEventListener("error", () => {
    resetPreviewState("frame", "這個時間點目前無法讀取縮圖。");
  });
  document.getElementById("wavePreviewImage").addEventListener("error", () => {
    resetPreviewState("wave", "這段音訊目前無法讀取波形。");
  });
  document.getElementById("timelinePreviewImage").addEventListener("error", () => {
    resetTimelinePreview("目前無法載入這個時間點的預覽。");
  });
  document.getElementById("timelinePlayPauseButton").addEventListener("click", async () => {
    try {
      await toggleTimelinePlayback();
    } catch (error) {
      setNotice(error.message, "error");
    }
  });
  document.getElementById("timelinePlaySelectionButton").addEventListener("click", async () => {
    try {
      await playTimelineMedia({ fromStart: true, limitToSelection: timelineState.mode === "range" });
    } catch (error) {
      setNotice(error.message, "error");
    }
  });
  document.getElementById("timelineSeekStartButton").addEventListener("click", () => {
    seekTimelineMedia(timelineState.startSec);
    setNotice("已跳到起點。", "success");
  });
  document.getElementById("timelineApplyButton").addEventListener("click", () => {
    try {
      applyTimelineToField();
      setNotice(`已把 ${timelineState.mode === "range" ? "時間段" : "時間點"} 套回欄位。`, "success");
    } catch (error) {
      setNotice(error.message, "error");
    }
  });
  document.getElementById("timelineLoadSelectedButton").addEventListener("click", () => {
    try {
      loadSelectedIntoTimeline();
      setNotice("已把目前選取項目載入時間軸。", "success");
    } catch (error) {
      setNotice(error.message, "error");
    }
  });
  document.getElementById("timelinePreviewButton").addEventListener("click", () => {
    renderTimelinePreview({ previewTimeSec: timelineState.playheadSec, reason: "目前位置" });
  });
  document.getElementById("timelineStartInput").addEventListener("change", () => {
    try {
      updateTimelineFromInputs();
      seekTimelineMedia(timelineState.startSec);
      renderTimelinePreview({ previewTimeSec: timelineState.startSec, reason: "起點" });
    } catch (error) {
      setNotice(error.message, "error");
    }
  });
  document.getElementById("timelineEndInput").addEventListener("change", () => {
    try {
      updateTimelineFromInputs();
      seekTimelineMedia(timelineState.startSec);
      renderTimelinePreview({ previewTimeSec: timelineState.startSec, reason: "起點" });
    } catch (error) {
      setNotice(error.message, "error");
    }
  });
  document.getElementById("timelineTrack").addEventListener("pointerdown", (event) => {
    if (!timelineState.open) {
      return;
    }
    const target = eventElement(event);
    if (!target) {
      return;
    }
    const handle = target.closest(".timeline-handle");
    const segment = target.closest(".timeline-selection");
    const marker = target.closest(".timeline-entry-dot, .timeline-entry-range");
    if (marker) {
      return;
    }
    if (handle) {
      beginTimelineDrag(handle.id === "timelineStartHandle" ? (timelineState.mode === "range" ? "start" : "point") : "end", event.clientX);
      return;
    }
    if (segment && timelineState.mode === "range") {
      beginTimelineDrag("selection", event.clientX);
      return;
    }
    const clickedTime = timelineTimeFromClientX(event.clientX);
    if (timelineState.mode === "range") {
      const distanceToStart = Math.abs(clickedTime - timelineState.startSec);
      const distanceToEnd = Math.abs(clickedTime - timelineState.endSec);
      if (distanceToStart <= distanceToEnd) {
        setTimelineRange(clickedTime, timelineState.endSec);
        beginTimelineDrag("start", event.clientX);
      } else {
        setTimelineRange(timelineState.startSec, clickedTime);
        beginTimelineDrag("end", event.clientX);
      }
    } else {
      setTimelineRange(clickedTime, clickedTime);
      beginTimelineDrag("point", event.clientX);
    }
    renderTimelinePreview({ previewTimeSec: timelineState.startSec, reason: "起點" });
  });
  document.addEventListener("pointermove", (event) => {
    if (!timelineState.drag) {
      return;
    }
    handleTimelinePointerMove(event.clientX);
  });
  document.addEventListener("pointerup", () => {
    if (timelineState.drag) {
      seekTimelineMedia(timelineState.startSec);
      renderTimelinePreview({ previewTimeSec: timelineState.startSec, reason: "起點" });
    }
    endTimelineDrag();
  });
  document.addEventListener("keydown", async (event) => {
    const intent = timelineShortcutIntent(event);
    if (!intent) {
      return;
    }
    event.preventDefault();
    if (intent.type === "toggle") {
      try {
        await toggleTimelinePlayback();
      } catch (error) {
        setNotice(error.message, "error");
      }
      return;
    }
    if (intent.type === "nudge" || intent.type === "fine_nudge") {
      try {
        nudgeTimelineSelection(intent.deltaSec);
      } catch (error) {
        setNotice(error.message, "error");
      }
      return;
    }
    if (intent.type === "jump") {
      try {
        jumpTimelineSelection(intent.edge);
        setNotice(intent.edge === "end" ? "已跳到終點。" : "已跳到起點。", "success");
      } catch (error) {
        setNotice(error.message, "error");
      }
    }
  });

  [document.getElementById("timelineVideoPlayer"), document.getElementById("timelineAudioPlayer")].forEach((media) => {
    media.addEventListener("loadedmetadata", () => {
      const pendingSeek = Number(media.dataset.pendingSeek || timelineState.startSec || 0);
      if (Number.isFinite(pendingSeek)) {
        media.currentTime = Math.max(0, Math.min(Number(media.duration || timelineState.durationSec || 0), pendingSeek));
        media.dataset.pendingSeek = "";
      }
      setTimelinePlayhead(media.currentTime || timelineState.startSec || 0);
      updateTimelinePlaybackText();
      if (media.id === "timelineVideoPlayer") {
        maybeRefreshTimelinePreview(media.currentTime || timelineState.startSec || 0, { force: true, reason: "目前位置" });
      }
    });
    media.addEventListener("timeupdate", () => {
      setTimelinePlayhead(media.currentTime || 0);
      if (timelineState.playUntilSec !== null && media.currentTime >= timelineState.playUntilSec - 0.03) {
        media.pause();
        media.currentTime = timelineState.playUntilSec;
        setTimelinePlayhead(timelineState.playUntilSec);
        timelineState.playUntilSec = null;
      }
      if (media.id === "timelineVideoPlayer") {
        maybeRefreshTimelinePreview(media.currentTime || 0, { reason: media.paused ? "目前位置" : "播放中" });
      }
    });
    media.addEventListener("seeking", () => {
      setTimelinePlayhead(media.currentTime || 0);
      if (media.id === "timelineVideoPlayer") {
        maybeRefreshTimelinePreview(media.currentTime || 0, { force: true, reason: "定位到" });
      }
    });
    media.addEventListener("play", () => {
      updateTimelinePlaybackText();
      if (media.id === "timelineVideoPlayer") {
        maybeRefreshTimelinePreview(media.currentTime || 0, { force: true, reason: "播放中" });
      }
    });
    media.addEventListener("pause", () => {
      updateTimelinePlaybackText();
      if (media.id === "timelineVideoPlayer") {
        maybeRefreshTimelinePreview(media.currentTime || 0, { force: true, reason: "停在" });
      }
    });
    media.addEventListener("ended", () => {
      timelineState.playUntilSec = null;
      updateTimelinePlaybackText();
      if (media.id === "timelineVideoPlayer") {
        maybeRefreshTimelinePreview(media.currentTime || timelineState.playheadSec || 0, { force: true, reason: "播放結束" });
      }
    });
  });

  document.addEventListener("click", async (event) => {
    const target = eventElement(event);
    if (!target) {
      return;
    }

    const browseTrigger = target.closest(".browse-trigger");
    if (browseTrigger) {
      try {
        await openBrowser(browseTrigger.dataset.target, browseTrigger.dataset.mode || "file");
      } catch (error) {
        setNotice(error.message, "error");
      }
      return;
    }

    const insertButton = target.closest(".time-insert-button");
    if (insertButton) {
      appendTokenToField(insertButton.dataset.target, insertButton.dataset.value);
      const profile = currentAnalysisProfile();
      const profileAware = panelMeta.profileFields.some((field) => field.key === insertButton.dataset.target);
      const scope = profile && profileAware ? `到 ${profile}` : "到全域設定";
      setNotice(`已帶入 ${insertButton.dataset.value} ${scope}`, "success");
      return;
    }

    const timeChip = target.closest(".time-chip");
    if (timeChip && !timeChip.classList.contains("empty")) {
      selectTimeEditorEntry(timeChip.dataset.target, Number(timeChip.dataset.index));
      setNotice(`已選取 ${timeChip.textContent}，可以直接微調。`, "success");
      return;
    }

    const timeAction = target.closest(
      ".time-editor-add-point, .time-editor-add-range, .time-editor-update, .time-editor-delete, .time-editor-nudge, .time-editor-open-timeline, .time-editor-sort, .time-editor-clear",
    );
    if (timeAction) {
      try {
        const targetId = timeAction.dataset.target;
        if (timeAction.classList.contains("time-editor-add-point")) {
          addTimeEditorEntry(targetId, "point");
          setNotice("已加入時間點。", "success");
        } else if (timeAction.classList.contains("time-editor-add-range")) {
          addTimeEditorEntry(targetId, "range");
          setNotice("已加入時間段。", "success");
        } else if (timeAction.classList.contains("time-editor-update")) {
          updateTimeEditorEntry(targetId);
          setNotice("已覆蓋所選時間。", "success");
        } else if (timeAction.classList.contains("time-editor-delete")) {
          deleteTimeEditorEntry(targetId);
          setNotice("已刪除所選時間。", "success");
        } else if (timeAction.classList.contains("time-editor-nudge")) {
          nudgeTimeEditor(targetId, Number(timeAction.dataset.delta || 0));
          setNotice(`已微調 ${timeAction.dataset.delta}s。`, "success");
        } else if (timeAction.classList.contains("time-editor-open-timeline")) {
          await openTimelineModal(targetId);
          setNotice("已開啟時間軸調整。", "success");
        } else if (timeAction.classList.contains("time-editor-sort")) {
          sortTimeEditorEntries(targetId);
          setNotice("已依時間排序。", "success");
        } else if (timeAction.classList.contains("time-editor-clear")) {
          clearTimeEditorEntries(targetId);
          setNotice("已清空這個欄位的時間項目。", "success");
        }
      } catch (error) {
        setNotice(error.message, "error");
      }
      return;
    }

    const timelineMarker = target.closest(".timeline-entry-dot, .timeline-entry-range");
    if (timelineMarker) {
      selectTimelineEntry(Number(timelineMarker.dataset.index));
      seekTimelineMedia(timelineState.startSec);
      renderTimelinePreview({ previewTimeSec: timelineState.startSec, reason: "起點" });
      setNotice("已載入時間軸上的既有項目。", "success");
      return;
    }

    const clipRangeButton = target.closest(".set-clip-range-button");
    if (clipRangeButton) {
      setClipRange(
        clipRangeButton.dataset.start,
        clipRangeButton.dataset.end,
        clipRangeButton.dataset.source || null,
        currentAnalysisProfile(),
      );
      setNotice(`已設定擷取區間 ${clipRangeButton.dataset.start} - ${clipRangeButton.dataset.end}`, "success");
      return;
    }

    const previewFrameButton = target.closest(".preview-frame-button");
    if (previewFrameButton) {
      previewFrame(previewFrameButton.dataset.time, previewFrameButton.dataset.label || "縮圖預覽");
      return;
    }

    const previewWaveButton = target.closest(".preview-wave-button");
    if (previewWaveButton) {
      previewWaveform(previewWaveButton.dataset.path, previewWaveButton.dataset.label || "波形預覽");
      return;
    }

    const openButton = target.closest(".browser-open-button");
    if (openButton) {
      try {
        await loadBrowser(openButton.dataset.path);
      } catch (error) {
        setNotice(error.message, "error");
      }
      return;
    }

    const chooseButton = target.closest(".browser-choose-button");
    if (chooseButton) {
      applyBrowserSelection(chooseButton.dataset.valuePath);
      return;
    }

    const shortcutButton = target.closest(".browser-shortcut-button");
    if (shortcutButton) {
      try {
        await loadBrowser(shortcutButton.dataset.path);
      } catch (error) {
        setNotice(error.message, "error");
      }
    }
  });
}

async function bootstrap() {
  bindActions();
  try {
    await loadState();
    setNotice("面板已就緒，可以直接修改設定。", "success");
  } catch (error) {
    setNotice(error.message, "error");
  }
  window.setInterval(refreshStatus, 2000);
}

bootstrap();
