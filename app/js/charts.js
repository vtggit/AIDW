'use strict';

const Charts = {
  _esc(str) {
    const s = String(str);
    return s.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;');
  },

  _fmt(n) {
    if (n === null || n === undefined || isNaN(Number(n))) return '0';
    const num = Number(n);
    if (Number.isInteger(num)) {
      return num.toLocaleString('en-US');
    }
    return Number(num.toFixed(2)).toLocaleString('en-US', { maximumFractionDigits: 2 });
  },

  _footer(meta) {
    const parts = [];
    if (meta.total_rows !== undefined && meta.total_rows !== null) {
      parts.push(`${this._fmt(meta.total_rows)} rows`);
    }
    if (meta.refreshed_at) {
      parts.push(`refreshed ${this._esc(String(meta.refreshed_at))}`);
    }
    return parts.join(' \u00b7 ');
  },

  renderBar(series, meta) {
    const W = 640;
    const H = 360;
    const padTop = 50;
    const padRight = 20;
    const padBottom = 80;
    const padLeft = 70;
    const chartW = W - padLeft - padRight;
    const chartH = H - padTop - padBottom;

    let maxVal = 0;
    for (let i = 0; i < series.length; i++) {
      if (series[i][1] > maxVal) maxVal = series[i][1];
    }
    if (maxVal === 0) maxVal = 1;

    const yTicks = [0, maxVal * 0.33, maxVal * 0.67, maxVal];

    let svg = `<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 ${W} ${H}" width="${W}" height="${H}">`;

    if (meta.title) {
      svg += `<text x="${W / 2}" y="25" text-anchor="middle" font-size="16" font-weight="bold">${this._esc(meta.title)}</text>`;
    }

    for (let i = 0; i < yTicks.length; i++) {
      const val = yTicks[i];
      const y = padTop + chartH - (val / maxVal) * chartH;
      svg += `<line x1="${padLeft}" y1="${y}" x2="${W - padRight}" y2="${y}" stroke="#e0e0e0" stroke-width="1"/>`;
      svg += `<text x="${padLeft - 8}" y="${y + 4}" text-anchor="end" font-size="11">${this._fmt(val)}</text>`;
    }

    const barCount = series.length || 1;
    const gap = 8;
    const barW = Math.max(2, (chartW - gap * (barCount + 1)) / barCount);

    for (let i = 0; i < series.length; i++) {
      const label = String(series[i][0]);
      const value = Number(series[i][1]) || 0;
      const x = padLeft + gap + i * (barW + gap);
      const barH = (value / maxVal) * chartH;
      const y = padTop + chartH - barH;

      let fill = '#4a90d9';
      if (label === 'Other') {
        fill = '#b0b0b0';
      }

      svg += `<rect x="${x}" y="${y}" width="${barW}" height="${barH}" fill="${fill}">`;
      svg += `<title>${this._esc(label)}: ${this._fmt(value)}</title>`;
      svg += `</rect>`;

      const valY = Math.max(y - 4, padTop + 2);
      svg += `<text x="${x + barW / 2}" y="${valY}" text-anchor="middle" font-size="10">${this._fmt(value)}</text>`;

      const truncated = label.length > 12 ? label.slice(0, 12) : label;
      svg += `<text x="${x + barW / 2}" y="${padTop + chartH + 16}" text-anchor="middle" font-size="11">${this._esc(truncated)}</text>`;
    }

    const footer = this._footer(meta);
    if (footer) {
      svg += `<text x="${W / 2}" y="${H - 10}" text-anchor="middle" font-size="11" fill="#666">${this._esc(footer)}</text>`;
    }

    svg += `</svg>`;
    return svg;
  },

  renderKpi(value, meta) {
    const W = 640;
    const H = 160;

    let svg = `<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 ${W} ${H}" width="${W}" height="${H}">`;

    svg += `<text x="${W / 2}" y="60" text-anchor="middle" font-size="48" font-weight="bold">${this._fmt(value)}</text>`;

    if (meta.measure_label) {
      svg += `<text x="${W / 2}" y="95" text-anchor="middle" font-size="16" fill="#666">${this._esc(meta.measure_label)}</text>`;
    }

    const footer = this._footer(meta);
    if (footer) {
      svg += `<text x="${W / 2}" y="${H - 15}" text-anchor="middle" font-size="11" fill="#888">${this._esc(footer)}</text>`;
    }

    svg += `</svg>`;
    return svg;
  },
};

if (typeof module !== 'undefined' && module.exports) {
  module.exports = { Charts };
}
