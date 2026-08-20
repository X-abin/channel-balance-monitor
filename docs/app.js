const els = {
  summary: document.querySelector("#summary"),
  pill: document.querySelector("#status-pill"),
  total: document.querySelector("#total-count"),
  low: document.querySelector("#low-count"),
  threshold: document.querySelector("#threshold"),
  checkedAt: document.querySelector("#checked-at"),
  lowTable: document.querySelector("#low-table"),
  allTable: document.querySelector("#all-table"),
  alertNote: document.querySelector("#alert-note"),
};

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

function rowForLow(channel) {
  return `
    <tr>
      <td>${channelName(channel)}</td>
      <td>${starCell(channel)}</td>
      <td class="mono">${formatMoney(channel.balance)}</td>
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
      <td class="mono">${channel.tokenCount ?? "-"}</td>
      <td><span class="tag ${tagClass}">${tagText}</span></td>
    </tr>
  `;
}

function sortChannels(channels) {
  return [...channels].sort((a, b) => {
    const av = a.balance === null || a.balance === undefined ? Number.POSITIVE_INFINITY : Number(a.balance);
    const bv = b.balance === null || b.balance === undefined ? Number.POSITIVE_INFINITY : Number(b.balance);
    return av - bv || String(a.name).localeCompare(String(b.name), "zh-CN");
  });
}

function render(data) {
  const channels = Array.isArray(data.channels) ? data.channels : [];
  const lowChannels = Array.isArray(data.lowChannels) ? data.lowChannels : [];
  const starredLowCount = lowChannels.filter((channel) => channel.isStarred).length;

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
    els.summary.textContent = `发现 ${lowChannels.length} 个渠道余额低于阈值，其中 ${starredLowCount} 个是星标渠道，已按配置发送 Telegram 提醒。`;
  } else {
    els.pill.classList.add("ok");
    els.pill.textContent = "正常";
    els.summary.textContent = "所有可读取余额的渠道都高于提醒阈值。";
  }

  els.alertNote.textContent = lowChannels.length > 0 ? "这些渠道需要优先处理" : "当前没有低余额渠道";
  els.lowTable.innerHTML = lowChannels.length ? lowChannels.map(rowForLow).join("") : '<tr><td colspan="5">当前没有低余额渠道。</td></tr>';
  els.allTable.innerHTML = channels.length ? sortChannels(channels).map(rowForAll).join("") : '<tr><td colspan="5">暂无渠道数据。</td></tr>';
}

fetch("status.json", { cache: "no-store" })
  .then((response) => {
    if (!response.ok) throw new Error("还没有生成检查结果。请等待第一次自动检查完成。");
    return response.json();
  })
  .then(render)
  .catch((err) => {
    els.pill.className = "status-pill error";
    els.pill.textContent = "未配置";
    els.summary.textContent = err.message;
    els.total.textContent = "-";
    els.low.textContent = "-";
    els.threshold.textContent = "30 元";
    els.checkedAt.textContent = "-";
    els.lowTable.innerHTML = '<tr><td colspan="5">等待第一次检查结果。</td></tr>';
    els.allTable.innerHTML = '<tr><td colspan="5">等待第一次检查结果。</td></tr>';
  });
