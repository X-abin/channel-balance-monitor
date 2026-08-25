const els = {
  summary: document.querySelector("#summary"),
  pill: document.querySelector("#status-pill"),
  refreshButton: document.querySelector("#refresh-button"),
  runButton: document.querySelector("#run-button"),
  tokenInput: document.querySelector("#github-token"),
  saveTokenButton: document.querySelector("#save-token-button"),
  clearTokenButton: document.querySelector("#clear-token-button"),
  tokenHint: document.querySelector("#token-hint"),
  total: document.querySelector("#total-count"),
  low: document.querySelector("#low-count"),
  threshold: document.querySelector("#threshold"),
  checkedAt: document.querySelector("#checked-at"),
  lowTable: document.querySelector("#low-table"),
  allTable: document.querySelector("#all-table"),
  alertNote: document.querySelector("#alert-note"),
};

const GITHUB_OWNER = "X-abin";
const GITHUB_REPO = "channel-balance-monitor";
const GITHUB_BRANCH = "main";
const GITHUB_WORKFLOW = "check-balance.yml";
const CURRENT_STATUS_URL = new URL("status.json", window.location.href).toString();
const REMOTE_STATUS_URL = `https://api.github.com/repos/${GITHUB_OWNER}/${GITHUB_REPO}/contents/docs/status.json?ref=${encodeURIComponent(GITHUB_BRANCH)}`;
const WORKFLOW_DISPATCH_URL = `https://api.github.com/repos/${GITHUB_OWNER}/${GITHUB_REPO}/actions/workflows/${GITHUB_WORKFLOW}/dispatches`;
const GITHUB_TOKEN_KEY = "channel_balance_github_token";
let lastCheckedAt = null;

function formatTime(value) {
  if (!value) return "-";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value;
  return date.toLocaleString("zh-CN", { hour12: false });
}

function formatMoney(value) {
  if (value === null || value === undefined || value === "") return "未知";
  const number = Number(value);
  if (!Number.isFinite(number)) return "未知";
  return number.toLocaleString("zh-CN", { maximumFractionDigits: 4 });
}

function escapeHtml(value) {
  return String(value ?? "").replace(/[&<>"]/g, (char) => ({
    "&": "&amp;",
    "<": "&lt;",
    ">": "&gt;",
    "\"": "&quot;",
  }[char]));
}

function channelName(channel) {
  return `<span class="channel-name">${escapeHtml(channel.name)}</span>`;
}

function starCell(channel) {
  return channel.isStarred ? '<span class="star-badge" title="后台已星标">星标</span>' : '<span class="muted">-</span>';
}

function sourceCell(channel) {
  if (channel.balanceSource === "upstream") {
    return '<span class="tag ok" title="已登录上游站点实时读取余额">上游实时</span>';
  }
  if (channel.balanceSource === "upstream_failed") {
    const reason = escapeHtml(channel.upstreamBalanceError || "上游实时读取失败");
    return `<span class="tag error" title="${reason}">读取失败</span>`;
  }
  return '<span class="tag neutral" title="旧配置兼容：使用监测后台同步余额">后台同步</span>';
}

function rowForLow(channel) {
  return `
    <tr>
      <td>${channelName(channel)}</td>
      <td>${starCell(channel)}</td>
      <td class="mono">${formatMoney(channel.balance)}</td>
      <td>${sourceCell(channel)}</td>
      <td class="mono">${formatMoney(channel.threshold)}</td>
      <td class="muted">${formatTime(channel.lastSyncedAt)}</td>
    </tr>
  `;
}

function rowForAll(channel) {
  const tagClass = channel.isLow ? "warn" : "ok";
  const tagText = channel.isLow ? "低余额" : "正常";
  return `
    <tr>
      <td>${channelName(channel)}</td>
      <td>${starCell(channel)}</td>
      <td class="mono">${formatMoney(channel.balance)}</td>
      <td>${sourceCell(channel)}</td>
      <td class="mono">${channel.tokenCount ?? "-"}</td>
      <td><span class="tag ${tagClass}">${tagText}</span></td>
    </tr>
  `;
}

function balanceValue(channel) {
  return channel.balance === null || channel.balance === undefined ? Number.NEGATIVE_INFINITY : Number(channel.balance);
}

function sortChannels(channels) {
  return [...channels].sort((a, b) => {
    const balanceDiff = balanceValue(a) - balanceValue(b);
    if (balanceDiff !== 0) return balanceDiff;
    const starred = Number(Boolean(b.isStarred)) - Number(Boolean(a.isStarred));
    if (starred !== 0) return starred;
    return String(a.name).localeCompare(String(b.name), "zh-CN");
  });
}

function render(data) {
  const channels = Array.isArray(data.channels) ? data.channels : [];
  const lowChannels = Array.isArray(data.lowChannels) ? data.lowChannels : [];
  const failedChannels = Array.isArray(data.failedChannels) ? data.failedChannels : channels.filter((channel) => channel.balanceSource === "upstream_failed");
  const starredLowCount = lowChannels.filter((channel) => channel.isStarred).length;
  const skippedChannels = Number(data.skippedChannels || 0);
  const skipText = data.monitorStarredOnly && skippedChannels > 0 ? `，已跳过 ${skippedChannels} 个未星标渠道` : "";
  const failText = data.upstreamBalanceOnly && failedChannels.length > 0 ? `，${failedChannels.length} 个渠道实时读取失败` : "";

  els.total.textContent = channels.length;
  els.low.textContent = lowChannels.length;
  els.threshold.textContent = `${formatMoney(data.threshold)} 元`;
  els.checkedAt.textContent = formatTime(data.checkedAt);

  els.pill.className = "status-pill";
  if (!data.ok) {
    els.pill.classList.add("error");
    els.pill.textContent = "检查失败";
    els.summary.textContent = data.error || "还没有成功完成检查。请确认 GitHub Secrets 已配置。";
  } else if (lowChannels.length > 0) {
    els.pill.classList.add("warn");
    els.pill.textContent = "需要续费";
    els.summary.textContent = `发现 ${lowChannels.length} 个星标渠道实时余额低于阈值${skipText}${failText}，已按配置发送 Telegram 提醒。`;
  } else {
    els.pill.classList.add("ok");
    els.pill.textContent = "正常";
    els.summary.textContent = `当前已读取到实时余额的星标渠道都高于提醒阈值${skipText}${failText}。`;
  }

  els.alertNote.textContent = lowChannels.length > 0 ? "当前只监测后台已星标渠道，余额只使用上游实时数据" : "当前没有低余额星标渠道";
  els.lowTable.innerHTML = lowChannels.length ? sortChannels(lowChannels).map(rowForLow).join("") : '<tr><td colspan="6">当前没有低余额渠道。</td></tr>';
  els.allTable.innerHTML = channels.length ? sortChannels(channels).map(rowForAll).join("") : '<tr><td colspan="6">暂无渠道数据。</td></tr>';
  lastCheckedAt = data.checkedAt || lastCheckedAt;
}

function setLoadingState(isLoading) {
  if (!els.refreshButton) return;
  els.refreshButton.disabled = isLoading;
  els.refreshButton.textContent = isLoading ? "读取中" : "刷新结果";
}

function setRunState(isRunning) {
  if (!els.runButton) return;
  els.runButton.disabled = isRunning;
  els.runButton.textContent = isRunning ? "检测中" : "立即检测";
}

async function fetchStatusFromCurrentPage() {
  const response = await fetch(`${CURRENT_STATUS_URL}${CURRENT_STATUS_URL.includes("?") ? "&" : "?"}v=${Date.now()}`, { cache: "no-store" });
  if (!response.ok) throw new Error("还没有生成检查结果。请等待第一次自动检查完成。");
  return response.json();
}

async function fetchStatusFromGitHub() {
  const response = await fetch(`${REMOTE_STATUS_URL}&t=${Date.now()}`, {
    cache: "no-store",
    headers: { Accept: "application/vnd.github+json" },
  });
  if (!response.ok) {
    throw new Error("GitHub 状态读取失败。");
  }
  const payload = await response.json();
  if (!payload || typeof payload.content !== "string") {
    throw new Error("GitHub 状态格式不正确。");
  }
  const binary = atob(payload.content.replace(/\n/g, ""));
  const bytes = Uint8Array.from(binary, (char) => char.charCodeAt(0));
  const text = new TextDecoder("utf-8").decode(bytes);
  return JSON.parse(text);
}

async function fetchLatestStatus(preferRemote = false) {
  if (!preferRemote) {
    try {
      return await fetchStatusFromCurrentPage();
    } catch (err) {
      return fetchStatusFromGitHub();
    }
  }
  return fetchStatusFromGitHub();
}

async function loadStatus(preferRemote = false) {
  setLoadingState(true);
  try {
    const data = await fetchLatestStatus(preferRemote);
    render(data);
  } catch (err) {
    els.pill.className = "status-pill error";
    els.pill.textContent = "未配置";
    els.summary.textContent = err.message;
    els.total.textContent = "-";
    els.low.textContent = "-";
    els.threshold.textContent = "30 元";
    els.checkedAt.textContent = "-";
    els.lowTable.innerHTML = '<tr><td colspan="6">等待第一次检查结果。</td></tr>';
    els.allTable.innerHTML = '<tr><td colspan="6">等待第一次检查结果。</td></tr>';
  } finally {
    setLoadingState(false);
  }
}

function getGithubToken() {
  try {
    return sessionStorage.getItem(GITHUB_TOKEN_KEY) || "";
  } catch {
    return "";
  }
}

function saveGithubToken(token) {
  try {
    sessionStorage.setItem(GITHUB_TOKEN_KEY, token);
  } catch {
    // ignore
  }
}

function clearGithubToken() {
  try {
    sessionStorage.removeItem(GITHUB_TOKEN_KEY);
  } catch {
    // ignore
  }
}

function syncTokenInput() {
  if (!els.tokenInput) return;
  els.tokenInput.value = getGithubToken();
  updateTokenHint();
}

function updateTokenHint(message) {
  if (!els.tokenHint) return;
  if (message) {
    els.tokenHint.textContent = message;
    return;
  }
  els.tokenHint.textContent = getGithubToken()
    ? "Token 已保存，点“保存 Token”会更新当前值。"
    : "未保存 Token 时，点“立即检测”会先询问你输入。";
}

function setTokenErrorState(message) {
  if (!els.tokenInput) return;
  els.tokenInput.classList.add("is-error");
  updateTokenHint(message);
  els.tokenInput.focus();
  els.tokenInput.select();
}

async function triggerWorkflow() {
  const typedToken = els.tokenInput ? els.tokenInput.value.trim() : "";
  let token = typedToken || getGithubToken();
  if (typedToken) {
    saveGithubToken(typedToken);
  }
  if (!token) {
    updateTokenHint("请先在上方填写 GitHub Token，再点“保存 Token”或“立即检测”。");
    setTokenErrorState("请先填写 GitHub Token。");
    return;
  }

  const currentCheckedAt = lastCheckedAt;
  setRunState(true);
  els.summary.textContent = "已请求重新检测，正在等待结果...";

  try {
    const response = await fetch(WORKFLOW_DISPATCH_URL, {
      method: "POST",
      headers: {
        Accept: "application/vnd.github+json",
        Authorization: `Bearer ${token}`,
        "Content-Type": "application/json",
        "X-GitHub-Api-Version": "2022-11-28",
      },
      body: JSON.stringify({ ref: GITHUB_BRANCH }),
    });
    if (!response.ok && response.status !== 204) {
      const text = await response.text();
      if (response.status === 401) {
        clearGithubToken();
        syncTokenInput();
        updateTokenHint("GitHub 拒绝了这个 Token，请重新填写一个有效的令牌。");
        throw new Error("Token 无效或权限不够，请重新填写新的 GitHub Token。");
      }
      throw new Error(text || "触发检测失败");
    }

    const deadline = Date.now() + 15 * 60 * 1000;
    while (Date.now() < deadline) {
      await new Promise((resolve) => setTimeout(resolve, 8000));
      try {
        const data = await fetchLatestStatus(true);
        if (data.checkedAt && data.checkedAt !== currentCheckedAt) {
          render(data);
          return;
        }
      } catch {
        // keep waiting
      }
    }
    throw new Error("已触发检测，但等待结果超时。");
  } catch (err) {
    els.pill.className = "status-pill error";
    els.pill.textContent = "失败";
    els.summary.textContent = err.message || "触发检测失败。";
  } finally {
    setRunState(false);
  }
}

if (els.refreshButton) {
  els.refreshButton.addEventListener("click", () => loadStatus(false));
}

if (els.runButton) {
  els.runButton.addEventListener("click", triggerWorkflow);
}

if (els.saveTokenButton) {
  els.saveTokenButton.addEventListener("click", () => {
    const token = els.tokenInput ? els.tokenInput.value.trim() : "";
    if (!token) {
      setTokenErrorState("请先粘贴 GitHub Token。");
      return;
    }
    saveGithubToken(token);
    updateTokenHint("Token 已保存，可以直接点“立即检测”。");
    if (els.tokenInput) {
      els.tokenInput.classList.remove("is-error");
    }
  });
}

if (els.clearTokenButton) {
  els.clearTokenButton.addEventListener("click", () => {
    clearGithubToken();
    if (els.tokenInput) {
      els.tokenInput.value = "";
      els.tokenInput.classList.remove("is-error");
      els.tokenInput.focus();
    }
    updateTokenHint("Token 已清除，请重新填写。");
  });
}

if (els.tokenInput) {
  els.tokenInput.addEventListener("input", () => {
    els.tokenInput.classList.remove("is-error");
    updateTokenHint();
  });
  els.tokenInput.addEventListener("keydown", (event) => {
    if (event.key === "Enter") {
      event.preventDefault();
      triggerWorkflow();
    }
  });
}

syncTokenInput();
loadStatus(false);
