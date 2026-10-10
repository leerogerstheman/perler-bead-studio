'use strict';

/* 拼豆图纸生成器 · 网页版前端
 *
 * 分两类操作，因为服务端的分工不同：
 *   reconvert()      尺寸/色卡/填充/去背景变了 —— 要重跑转换（core.convert_file）
 *   refreshPreview() 画法/网格/坐标变了     —— 只重渲染图纸（painter.render_chart）
 *
 * 转换是 CPU 密集的，所以输入做 250ms 防抖；预览是纯渲染，直接刷新即可。
 */

const $ = (id) => document.getElementById(id);

const state = {
  meta: null,
  image: null,        // { name, w, h }
  folder: null,       // 上次导出目录
  busy: false,
  queued: false,
  timer: 0,
  previewSeq: 0,
};

/* ------------------------------------------------------------ 小工具 -- */

function toast(message, kind) {
  const el = document.createElement('div');
  el.className = 'toast ' + (kind || 'ok');
  el.textContent = message;
  $('toastHost').appendChild(el);
  setTimeout(() => el.remove(), kind === 'err' ? 7000 : 4000);
}

async function api(path, options) {
  const res = await fetch(path, options);
  let data = null;
  try { data = await res.json(); } catch (e) { data = null; }
  if (!res.ok || !data || data.ok === false) {
    throw new Error((data && data.error) || (res.status + ' ' + res.statusText));
  }
  return data;
}

function num(el, fallback, lo, hi) {
  let v = parseInt(el.value, 10);
  if (!isFinite(v)) v = fallback;
  return Math.max(lo, Math.min(hi, v));
}

function fill(select, items, valueKey, labelKey) {
  select.innerHTML = '';
  for (const it of items) {
    const o = document.createElement('option');
    o.value = typeof it === 'string' ? it : it[valueKey];
    o.textContent = typeof it === 'string' ? it : it[labelKey];
    select.appendChild(o);
  }
}

/* -------------------------------------------------------------- 选项 -- */

function currentOptions() {
  return {
    cols: num($('colsInput'), 32, 4, 1024),
    rows: num($('rowsInput'), 32, 4, 1024),
    palette: $('paletteSel').value,
    dither: $('ditherChk').checked,
    fit: $('fitSel').value,
    anchor: $('anchorSel').value,
    bgRemoval: $('bgChk').checked,
    tolerance: num($('tolRange'), 24, 0, 255),
  };
}

function previewQuery() {
  const q = new URLSearchParams();
  q.set('mode', $('modeSel').value);
  q.set('ruler', $('rulerChk').checked ? '1' : '0');
  q.set('grid', $('gridChk').checked ? '1' : '0');
  q.set('coords', $('rulerChk').checked ? '1' : '0');
  q.set('t', String(++state.previewSeq));
  return q.toString();
}

function syncVisibility() {
  // 只有「裁切填满」才需要问保留哪一块
  $('anchorField').hidden = $('fitSel').value !== 'fill';
  $('tolField').hidden = !$('bgChk').checked;
  $('tolVal').textContent = $('tolRange').value;
}

/* ------------------------------------------------------------ 转换 ---- */

function scheduleConvert() {
  clearTimeout(state.timer);
  state.timer = setTimeout(reconvert, 250);
}

async function reconvert() {
  if (!state.image) return;
  if (state.busy) { state.queued = true; return; }

  state.busy = true;
  state.queued = false;
  $('busy').hidden = false;

  try {
    const data = await api('/api/convert', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(currentOptions()),
    });
    applyPattern(data);
  } catch (err) {
    toast('转换失败：' + err.message, 'err');
  } finally {
    state.busy = false;
    $('busy').hidden = true;
    if (state.queued) reconvert();
  }
}

function applyPattern(data) {
  $('welcome').hidden = true;

  $('statTotal').textContent = data.total;
  $('statSize').textContent = data.cols + '×' + data.rows;
  $('statColors').textContent = data.colors;
  $('statSheets').textContent = data.sheets;
  $('statTime').textContent = data.elapsed + 's';
  $('stats').hidden = false;

  const counts = $('counts');
  counts.innerHTML = '';
  for (const c of data.counts) {
    const el = document.createElement('div');
    el.className = 'count';
    const sw = document.createElement('i');
    sw.style.background = c.hex;
    const nm = document.createElement('span');
    nm.className = 'nm';
    nm.textContent = c.name;
    nm.title = c.name + ' ' + c.hex;
    const n = document.createElement('span');
    n.className = 'n';
    n.textContent = c.count;
    el.append(sw, nm, n);
    counts.appendChild(el);
  }
  $('countsNote').textContent = data.counts.length + ' 种 · 共 ' + data.total + ' 颗';
  $('countsWrap').hidden = false;

  if (data.note) { $('note').textContent = data.note; $('note').hidden = false; }
  else { $('note').hidden = true; }

  refreshPreview();
}

function refreshPreview() {
  const img = $('preview');
  img.hidden = false;
  img.src = '/api/preview.png?' + previewQuery();
}

/* ------------------------------------------------------------ 图片 ---- */

async function sendImage(file) {
  const res = await fetch('/api/image', {
    method: 'POST',
    headers: { 'X-Filename': encodeURIComponent(file.name) },
    body: file,
  });
  const data = await res.json().catch(() => null);
  if (!res.ok || !data || data.ok === false) {
    throw new Error((data && data.error) || '上传失败');
  }
  return data;
}

function afterImage(info) {
  state.image = info;
  $('fileChip').textContent = info.name + ' · ' + info.w + '×' + info.h;
  $('fileChip').classList.add('on');
  $('imageInfo').textContent = '已载入 ' + info.name + '（' + info.w + '×' + info.h + '）';
  $('exportInfo').textContent = '图纸 PNG、效果图、SVG、清单 TXT/CSV、网页图纸 HTML。';
  // 图片换了，按图片比例重算一遍行列，免得默认 32×32 把横图压扁
  applyImageRatio();
  reconvert();
}

function applyImageRatio() {
  if (!state.image || !$('linkChk').checked) return;
  const ratio = state.image.h / state.image.w;
  const cols = num($('colsInput'), 32, 4, 1024);
  const rows = Math.max(4, Math.min(1024, Math.round(cols * ratio)));
  $('rowsInput').value = rows;
}

/* ------------------------------------------------------------ 事件 ---- */

function wire() {
  $('pickBtn').onclick = () => $('fileInput').click();

  $('fileInput').onchange = async (e) => {
    const file = e.target.files && e.target.files[0];
    if (!file) return;
    try {
      afterImage(await sendImage(file));
      toast('已载入 ' + file.name);
    } catch (err) {
      toast('载入失败：' + err.message, 'err');
    }
    e.target.value = '';
  };

  $('sampleBtn').onclick = async () => {
    try {
      afterImage(await api('/api/sample', { method: 'POST' }));
      toast('已载入示例图');
    } catch (err) {
      toast('示例图不可用：' + err.message, 'err');
    }
  };

  // 尺寸：预设、列、行、锁定比例
  $('presetSel').onchange = () => {
    const p = state.meta.presets[parseInt($('presetSel').value, 10)];
    if (!p) return;
    $('colsInput').value = p.cols;
    $('rowsInput').value = p.rows;
    $('linkChk').checked = false;   // 显式选了预设，就别再按图片比例改回去
    scheduleConvert();
  };

  $('colsInput').oninput = () => {
    if ($('linkChk').checked && state.image) {
      $('rowsInput').value = Math.max(4, Math.min(1024,
        Math.round(num($('colsInput'), 32, 4, 1024) * (state.image.h / state.image.w))));
    }
    scheduleConvert();
  };
  $('rowsInput').oninput = () => {
    if ($('linkChk').checked && state.image) {
      $('colsInput').value = Math.max(4, Math.min(1024,
        Math.round(num($('rowsInput'), 32, 4, 1024) * (state.image.w / state.image.h))));
    }
    scheduleConvert();
  };
  $('linkChk').onchange = () => { if ($('linkChk').checked) { applyImageRatio(); scheduleConvert(); } };

  // 风格
  $('paletteSel').onchange = scheduleConvert;
  $('ditherChk').onchange = scheduleConvert;
  $('fitSel').onchange = () => { syncVisibility(); scheduleConvert(); };
  $('anchorSel').onchange = scheduleConvert;
  $('bgChk').onchange = () => { syncVisibility(); scheduleConvert(); };
  $('tolRange').oninput = () => { syncVisibility(); scheduleConvert(); };

  // 视图：只重渲染，不重算
  $('modeSel').onchange = refreshPreview;
  $('rulerChk').onchange = refreshPreview;
  $('gridChk').onchange = refreshPreview;

  // 导出
  $('exportBtn').onclick = async () => {
    const btn = $('exportBtn');
    btn.disabled = true;
    try {
      const data = await api('/api/export', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ baseName: $('baseInput').value, title: $('baseInput').value }),
      });
      state.folder = data.folder;
      $('revealBtn').disabled = false;
      $('exportInfo').textContent = '已导出 ' + data.files.length + ' 个文件到 ' + data.folder;
      toast('已导出 ' + data.files.length + ' 个文件');
    } catch (err) {
      toast('导出失败：' + err.message, 'err');
    } finally {
      btn.disabled = false;
    }
  };

  $('revealBtn').onclick = async () => {
    try {
      await api('/api/reveal', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ folder: state.folder }),
      });
    } catch (err) {
      toast('打不开目录：' + err.message, 'err');
    }
  };
}

/* ------------------------------------------------------------ 启动 ---- */

async function boot() {
  try {
    state.meta = await api('/api/meta');
  } catch (err) {
    toast('无法连接后端：' + err.message, 'err');
    return;
  }

  fill($('paletteSel'), state.meta.palettes);
  fill($('fitSel'), state.meta.fitModes, 'value', 'label');
  fill($('anchorSel'), state.meta.anchors, 'value', 'label');

  const presets = state.meta.presets;
  $('presetSel').innerHTML = '<option value="">自定义</option>';
  presets.forEach((p, i) => {
    const o = document.createElement('option');
    o.value = String(i);
    o.textContent = p.label;
    $('presetSel').appendChild(o);
  });

  const d = state.meta.defaults;
  $('colsInput').value = d.cols;
  $('rowsInput').value = d.rows;
  $('paletteSel').value = d.palette;
  $('fitSel').value = d.fit;
  $('anchorSel').value = d.anchor;
  $('tolRange').value = d.tolerance;
  $('exportInfo').textContent = '导出目录：' + state.meta.exportDir;

  syncVisibility();
  wire();
}

boot();
