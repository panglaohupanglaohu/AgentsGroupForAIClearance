/**
 * Open-Weights Models — AI 60s Intelligence & Clearance Controller.
 * Depends on: api.js
 */
(function () {
  'use strict';

  var state = {
    models: [],
    briefs: null,
    selectedModel: null,
  };

  // Fallback data in case of network or auth delay
  var BUILTIN_MODELS = [
    {
      model_id: "meta-llama/Llama-3.1-8B-Instruct",
      display_name: "Llama 3.1 8B Instruct",
      vendor: "Meta",
      vendor_country: "US",
      params_b: 8,
      license_id: "llama-3.1-community",
      license_url: "https://llama.meta.com/llama3_1/license/",
      license_class: "conditional",
      license_conditions: ["MAU 上限 7 亿需单独授权", "发布衍生品需保留 Meta 命名归属"],
      weights_url: "https://huggingface.co/meta-llama/Llama-3.1-8B-Instruct",
      weights_format: "safetensors",
      open_weights_signatory: true,
      latest_version: "3.1"
    },
    {
      model_id: "meta-llama/Llama-3.1-70B-Instruct",
      display_name: "Llama 3.1 70B Instruct",
      vendor: "Meta",
      vendor_country: "US",
      params_b: 70,
      license_id: "llama-3.1-community",
      license_url: "https://llama.meta.com/llama3_1/license/",
      license_class: "conditional",
      license_conditions: ["MAU 上限 7 亿需单独授权", "发布衍生品需保留 Meta 命名归属"],
      weights_url: "https://huggingface.co/meta-llama/Llama-3.1-70B-Instruct",
      weights_format: "safetensors",
      open_weights_signatory: true,
      latest_version: "3.1"
    },
    {
      model_id: "Qwen/Qwen2.5-7B-Instruct",
      display_name: "Qwen 2.5 7B Instruct",
      vendor: "Alibaba",
      vendor_country: "CN",
      params_b: 7,
      license_id: "apache-2.0",
      license_url: "https://www.apache.org/licenses/LICENSE-2.0",
      license_class: "commercial_ok",
      license_conditions: ["保留版权声明与许可证", "修改文件需作说明"],
      weights_url: "https://huggingface.co/Qwen/Qwen2.5-7B-Instruct",
      weights_format: "safetensors",
      open_weights_signatory: null,
      latest_version: "2.5"
    },
    {
      model_id: "Qwen/Qwen2.5-72B-Instruct",
      display_name: "Qwen 2.5 72B Instruct",
      vendor: "Alibaba",
      vendor_country: "CN",
      params_b: 72,
      license_id: "qwen-license",
      license_url: "https://github.com/QwenLM/Qwen2.5/blob/main/LICENSE",
      license_class: "conditional",
      license_conditions: ["MAU 上限 1 亿需商用授权申请"],
      weights_url: "https://huggingface.co/Qwen/Qwen2.5-72B-Instruct",
      weights_format: "safetensors",
      open_weights_signatory: null,
      latest_version: "2.5"
    },
    {
      model_id: "Qwen/Qwen2.5-Coder-32B-Instruct",
      display_name: "Qwen 2.5 Coder 32B Instruct",
      vendor: "Alibaba",
      vendor_country: "CN",
      params_b: 32,
      license_id: "apache-2.0",
      license_url: "https://www.apache.org/licenses/LICENSE-2.0",
      license_class: "commercial_ok",
      license_conditions: ["保留版权声明与许可证"],
      weights_url: "https://huggingface.co/Qwen/Qwen2.5-Coder-32B-Instruct",
      weights_format: "safetensors",
      open_weights_signatory: null,
      latest_version: "2.5"
    },
    {
      model_id: "deepseek-ai/DeepSeek-V3",
      display_name: "DeepSeek V3",
      vendor: "DeepSeek",
      vendor_country: "CN",
      params_b: 671,
      license_id: "deepseek-license",
      license_url: "https://github.com/deepseek-ai/DeepSeek-V3/blob/main/LICENSE-MODEL",
      license_class: "commercial_ok",
      license_conditions: ["免费商用，禁止用于违法场景"],
      weights_url: "https://huggingface.co/deepseek-ai/DeepSeek-V3",
      weights_format: "safetensors",
      open_weights_signatory: null,
      latest_version: "v3"
    },
    {
      model_id: "deepseek-ai/DeepSeek-R1",
      display_name: "DeepSeek R1",
      vendor: "DeepSeek",
      vendor_country: "CN",
      params_b: 671,
      license_id: "mit",
      license_url: "https://opensource.org/licenses/MIT",
      license_class: "commercial_ok",
      license_conditions: ["保留 MIT 许可文本及版权声明"],
      weights_url: "https://huggingface.co/deepseek-ai/DeepSeek-R1",
      weights_format: "safetensors",
      open_weights_signatory: null,
      latest_version: "r1"
    },
    {
      model_id: "mistralai/Mistral-7B-Instruct-v0.3",
      display_name: "Mistral 7B Instruct v0.3",
      vendor: "Mistral AI",
      vendor_country: "FR",
      params_b: 7,
      license_id: "apache-2.0",
      license_url: "https://www.apache.org/licenses/LICENSE-2.0",
      license_class: "commercial_ok",
      license_conditions: ["保留 Apache 2.0 版权声明"],
      weights_url: "https://huggingface.co/mistralai/Mistral-7B-Instruct-v0.3",
      weights_format: "safetensors",
      open_weights_signatory: true,
      latest_version: "v0.3"
    },
    {
      model_id: "mistralai/Mistral-Large-Instruct-2407",
      display_name: "Mistral Large Instruct 2407",
      vendor: "Mistral AI",
      vendor_country: "FR",
      params_b: 123,
      license_id: "mnr-license",
      license_url: "https://mistral.ai/terms/",
      license_class: "restricted",
      license_conditions: ["仅限研究和非商业用途，商业服务需官方授权"],
      weights_url: "https://huggingface.co/mistralai/Mistral-Large-Instruct-2407",
      weights_format: "safetensors",
      open_weights_signatory: true,
      latest_version: "2407"
    },
    {
      model_id: "google/gemma-2-9b-it",
      display_name: "Gemma 2 9B IT",
      vendor: "Google",
      vendor_country: "US",
      params_b: 9,
      license_id: "gemma-terms",
      license_url: "https://ai.google.dev/gemma/terms",
      license_class: "conditional",
      license_conditions: ["遵循 Gemma 禁止用途政策，商用需保留 Google 归属"],
      weights_url: "https://huggingface.co/google/gemma-2-9b-it",
      weights_format: "safetensors",
      open_weights_signatory: null,
      latest_version: "2.0"
    },
    {
      model_id: "microsoft/Phi-3.5-mini-instruct",
      display_name: "Phi 3.5 Mini Instruct",
      vendor: "Microsoft",
      vendor_country: "US",
      params_b: 3.8,
      license_id: "mit",
      license_url: "https://opensource.org/licenses/MIT",
      license_class: "commercial_ok",
      license_conditions: ["保留 MIT 许可与版权声明"],
      weights_url: "https://huggingface.co/microsoft/Phi-3.5-mini-instruct",
      weights_format: "safetensors",
      open_weights_signatory: null,
      latest_version: "3.5"
    },
    {
      model_id: "THUDM/glm-4-9b-chat",
      display_name: "GLM 4 9B Chat",
      vendor: "Zhipu AI",
      vendor_country: "CN",
      params_b: 9,
      license_id: "glm-4-license",
      license_url: "https://github.com/THUDM/GLM-4/blob/main/LICENSE",
      license_class: "conditional",
      license_conditions: ["商业用途需遵循智谱开放协议并完成备案登记"],
      weights_url: "https://huggingface.co/THUDM/glm-4-9b-chat",
      weights_format: "safetensors",
      open_weights_signatory: null,
      latest_version: "4.0"
    }
  ];

  function api() { return window.api; }
  function $(id) { return document.getElementById(id); }
  function esc(s) { return String(s == null ? '' : s).replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;').replace(/'/g, '&#39;'); }

  function estimateHardware(paramsB) {
    var p = Number(paramsB) || 8;
    if (p > 200) {
      return { vram: '300GB+ (MoE/量化)', hw: '8卡 H100 / 多节点集群', tier: 'large' };
    }
    if (p >= 65) {
      return { vram: '140GB+ (FP16) / 40GB (INT4)', hw: '双卡 A100/H100 或 4卡 4090', tier: 'large' };
    }
    if (p >= 25) {
      return { vram: '64GB (FP16) / 20GB (INT4)', hw: '单卡 A100(80G) 或双卡 3090', tier: 'medium' };
    }
    if (p >= 12) {
      return { vram: '32GB (FP16) / 10GB (INT4)', hw: '单卡 A10G / RTX 4090', tier: 'medium' };
    }
    return { vram: '16GB (FP16) / 6GB (INT4)', hw: '单卡 3090 / 4090 或 Mac M系列', tier: 'small' };
  }

  function getAi60Take(model) {
    var id = (model.model_id || '').toLowerCase();
    var p = model.params_b || 8;
    if (id.indexOf('deepseek') >= 0) {
      return '代码与多步推理前沿突破；开源开放度高，全尺寸性能比肩闭源顶尖。';
    }
    if (id.indexOf('qwen') >= 0) {
      return '中文与多语言全能基座；2.5 版本在编码、数学与结构化输出表现卓越。';
    }
    if (id.indexOf('llama') >= 0) {
      return '全球社区生态最完备的开源标杆；需注意商用 MAU 授权与名称衍生合规义务。';
    }
    if (id.indexOf('mistral') >= 0) {
      return '高密度架构与欧系模型标杆；小模型高性价比，大模型注意非商用限制。';
    }
    if (id.indexOf('gemma') >= 0) {
      return 'Google 轻量级优质端侧架构；严格受控于 Gemma 规范条款。';
    }
    if (id.indexOf('phi') >= 0) {
      return '高质量合成数据驱动的小钢炮；超高参数效率，极适合端侧与低延迟推理。';
    }
    if (id.indexOf('glm') >= 0) {
      return '清华/智谱自研架构；长文本处理能力突出，中文工具调用生态成熟。';
    }
    return '主流开放权重模型；参数规模 ' + p + 'B，适合构建垂直 Agent 团队与端侧任务。';
  }

  async function loadModels() {
    var root = $('model-matrix-grid');
    if (root) root.innerHTML = '<div class="muted" style="padding:40px;grid-column:1/-1;text-align:center">正在加载开放权重模型知识库…</div>';

    try {
      var res = await api().request('/api/v1/model-clearance/licenses');
      if (res && Array.isArray(res.models) && res.models.length) {
        state.models = res.models;
      } else {
        state.models = BUILTIN_MODELS;
      }
    } catch (e) {
      state.models = BUILTIN_MODELS;
    }

    populateFilters();
    renderMatrix();
    updateKPIs();
  }

  function updateKPIs() {
    var all = state.models;
    var total = all.length;
    var commercial = all.filter(function (m) { return m.license_class === 'commercial_ok'; }).length;
    var conditional = all.filter(function (m) { return m.license_class === 'conditional'; }).length;
    var restricted = all.filter(function (m) { return m.license_class === 'restricted'; }).length;

    if ($('kpi-total-models')) $('kpi-total-models').textContent = total || '—';
    if ($('kpi-commercial-models')) $('kpi-commercial-models').textContent = commercial;
    if ($('kpi-conditional-models')) $('kpi-conditional-models').textContent = conditional;
    if ($('kpi-restricted-models')) $('kpi-restricted-models').textContent = restricted;
  }

  function populateFilters() {
    var vendorSel = $('filter-vendor');
    if (!vendorSel) return;
    var vendors = {};
    state.models.forEach(function (m) {
      if (m.vendor) vendors[m.vendor] = true;
    });
    var current = vendorSel.value;
    var list = Object.keys(vendors).sort();
    vendorSel.innerHTML = '<option value="">全部厂商/机构</option>' + list.map(function (v) {
      return '<option value="' + esc(v) + '"' + (v === current ? ' selected' : '') + '>' + esc(v) + '</option>';
    }).join('');
  }

  function renderMatrix() {
    var root = $('model-matrix-grid');
    if (!root) return;

    var search = ($('model-search') ? $('model-search').value : '').trim().toLowerCase();
    var vendor = $('filter-vendor') ? $('filter-vendor').value : '';
    var license = $('filter-license') ? $('filter-license').value : '';
    var scale = $('filter-scale') ? $('filter-scale').value : '';

    var filtered = state.models.filter(function (m) {
      if (vendor && m.vendor !== vendor) return false;
      if (license && m.license_class !== license) return false;

      var p = Number(m.params_b) || 8;
      if (scale === 'small' && p >= 10) return false;
      if (scale === 'medium' && (p < 10 || p > 50)) return false;
      if (scale === 'large' && p <= 50) return false;
      if (scale === 'moe' && p < 100 && (m.model_id || '').toLowerCase().indexOf('moe') === -1) return false;

      if (search) {
        var blob = ((m.display_name || '') + ' ' + (m.model_id || '') + ' ' + (m.vendor || '') + ' ' + (m.license_id || '')).toLowerCase();
        if (blob.indexOf(search) === -1) return false;
      }
      return true;
    });

    if (!filtered.length) {
      root.innerHTML = '<div class="muted" style="padding:40px;grid-column:1/-1;text-align:center">未找到符合当前筛选条件的模型。可以尝试重置筛选或更改关键词。</div>';
      return;
    }

    root.innerHTML = filtered.map(function (m) {
      var licCls = m.license_class || 'conditional';
      var conditions = Array.isArray(m.license_conditions) ? m.license_conditions : [];
      var hw = estimateHardware(m.params_b);
      var paramsText = m.params_b ? m.params_b + 'B 参数' : 'MoE / 多模态';
      var take = getAi60Take(m);
      var clearanceHref = '/ai-model-entry-clearance.html?model_id=' + encodeURIComponent(m.model_id);

      return '<article class="model-card">' +
        '<div class="model-card-header">' +
          '<div>' +
            '<h3 class="model-card-title">' + esc(m.display_name || m.model_id) + '</h3>' +
            '<div class="model-card-meta">' + esc(m.vendor || '开源社区') + ' · ' + esc(m.vendor_country || 'Global') + ' · <code>' + esc(m.model_id) + '</code></div>' +
          '</div>' +
          '<span class="license-badge ' + licCls + '">' + esc(m.license_id || licCls) + '</span>' +
        '</div>' +

        '<div class="spec-badges">' +
          '<span class="spec-pill">规模: <b>' + esc(paramsText) + '</b></span>' +
          '<span class="spec-pill">显存预估: <b>' + esc(hw.vram) + '</b></span>' +
          '<span class="spec-pill">硬件: <b>' + esc(hw.hw) + '</b></span>' +
          (m.open_weights_signatory ? '<span class="spec-pill highlight">✓ Open Weights 签署方</span>' : '') +
        '</div>' +

        (conditions.length ? '<div class="conditions-list">' + conditions.map(function (c) { return '<span>' + esc(c) + '</span>'; }).join('') + '</div>' : '') +

        '<div class="ai60-take">' +
          '<b>AI 60秒速评:</b>' +
          esc(take) +
        '</div>' +

        '<div class="model-card-actions">' +
          '<a href="' + esc(clearanceHref) + '" class="btn-clearance">🛡️ 一键准入评审</a>' +
          '<button type="button" class="btn-ghost-sm btn-inspect" data-model-id="' + esc(m.model_id) + '">🔍 60秒规格详情</button>' +
          (m.license_url ? '<a href="' + esc(m.license_url) + '" target="_blank" rel="noopener noreferrer" class="btn-ghost-sm">📄 许可</a>' : '') +
          (m.weights_url ? '<a href="' + esc(m.weights_url) + '" target="_blank" rel="noopener noreferrer" class="btn-ghost-sm">📦 权重</a>' : '') +
        '</div>' +
      '</article>';
    }).join('');

    root.querySelectorAll('.btn-inspect').forEach(function (btn) {
      btn.addEventListener('click', function () {
        var mId = btn.getAttribute('data-model-id');
        var target = state.models.find(function (x) { return x.model_id === mId; });
        if (target) openModal(target);
      });
    });
  }

  function openModal(m) {
    state.selectedModel = m;
    var hw = estimateHardware(m.params_b);
    var p = Number(m.params_b) || 8;
    var wFp16 = (p * 2).toFixed(1);
    var wInt8 = (p * 1).toFixed(1);
    var wInt4 = (p * 0.5).toFixed(1);

    var kv4k = (0.5 * (p / 8)).toFixed(1);
    var kv32k = (4.0 * (p / 8)).toFixed(1);

    $('modal-model-title').textContent = (m.display_name || m.model_id) + ' · 60秒规格与 Lenovo 直管';
    $('modal-model-id').textContent = m.model_id + ' (' + (m.vendor || '开源社区') + ')';
    $('btn-modal-clearance-link').href = '/ai-model-entry-clearance.html?model_id=' + encodeURIComponent(m.model_id);

    var body = $('modal-model-body');
    body.innerHTML =
      '<div style="background:#f8fafc;padding:12px;border-radius:8px;border:1px solid #e2e8f0">' +
        '<div style="font-weight:700;color:#0f172a;margin-bottom:6px">一、硬件与显存需求 (3段式精确估算)</div>' +
        '<table style="width:100%;border-collapse:collapse;font-size:12px">' +
          '<thead><tr style="text-align:left;color:#64748b;border-bottom:1px solid #cbd5e1"><th style="padding:4px">量化档位</th><th>权重显存</th><th>KV-Cache (8K/32K)</th><th>激活余量</th><th>推荐部署形态</th></tr></thead>' +
          '<tbody>' +
            '<tr style="border-bottom:1px solid #f1f5f9"><td style="padding:6px 4px"><b>FP16 (原生)</b></td><td>' + wFp16 + ' GB</td><td>' + (kv4k*2).toFixed(1) + ' ~ ' + (kv32k*2).toFixed(1) + ' GB</td><td>20%</td><td>' + hw.hw + '</td></tr>' +
            '<tr style="border-bottom:1px solid #f1f5f9"><td style="padding:6px 4px"><b>INT8 / FP8</b></td><td>' + wInt8 + ' GB</td><td>' + kv4k + ' ~ ' + kv32k + ' GB</td><td>15%</td><td>单卡/多卡标准推理</td></tr>' +
            '<tr><td style="padding:6px 4px"><b>INT4 / AWQ / GGUF</b></td><td>' + wInt4 + ' GB</td><td>' + (kv4k*0.5).toFixed(1) + ' ~ ' + (kv32k*0.5).toFixed(1) + ' GB</td><td>10%</td><td>端侧/轻量单卡部署</td></tr>' +
          '</tbody>' +
        '</table>' +
      '</div>' +

      '<div style="background:#f0fdf4;padding:12px;border-radius:8px;border:1px solid #bbf7d0">' +
        '<div style="font-weight:700;color:#15803d;margin-bottom:4px">二、Lenovo 直管与控制矩阵预设</div>' +
        '<div style="font-size:12px;line-height:1.6;color:#166534">' +
          '• 建议运行时 Profile: <b>' + (m.license_class === 'commercial_ok' ? 'Standard (标准隔离)' : 'Restricted (强隔离受控)') + '</b><br>' +
          '• 责任人矩阵: 服务属主 <code>ai-platform-ops@lenovo.com</code> · 安全责任 <code>ai-sec-governance@lenovo.com</code><br>' +
          '• 控制不变量: SHA-256 Digest 启动强校验、只读根文件系统、禁止 Root、Deny-All 出站白名单<br>' +
          '• 应急处置准备: 支持 1 键 Kill-Switch 阻断与毫秒级基线回滚' +
        '</div>' +
      '</div>' +

      '<div style="background:#fffbeb;padding:12px;border-radius:8px;border:1px solid #fde047">' +
        '<div style="font-weight:700;color:#854d0e;margin-bottom:4px">三、许可证与商用合规条款</div>' +
        '<div style="font-size:12px;color:#78350f;line-height:1.5">' +
          '• 许可证类别: <b>' + esc(m.license_id || 'unknown') + '</b> (' + esc(m.license_class) + ')<br>' +
          '• 附加约束: ' + (m.license_conditions && m.license_conditions.length ? esc(m.license_conditions.join('；')) : '无额外特殊商用限制') +
        '</div>' +
      '</div>';

    $('spec-modal').classList.add('is-open');
  }

  function closeModal() {
    $('spec-modal').classList.remove('is-open');
  }

  async function loadBriefs() {
    try {
      var res = await api().request('/api/v1/information-documents/latest-summary');
      if (res && res.summaries && res.summaries.ai_news_60s) {
        var s = res.summaries.ai_news_60s;
        state.briefs = s;
        if (s.headline && $('ai60-headline')) {
          $('ai60-headline').textContent = s.headline;
        }
        if (s.as_of && $('ai60-as-of')) {
          $('ai60-as-of').textContent = '截止时间: ' + s.as_of;
        }
      }
    } catch (e) {
      /* ignore */
    }
  }

  async function triggerAi60Scan() {
    var btn = $('btn-run-ai60-scan');
    if (btn) btn.disabled = true;
    try {
      await api().request('/api/v1/information-runs', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ team_id: 'ai_news_60s', profile: 'ai60' })
      });
      alert('已启动 AI 60秒模型与开源生态情报采集流水线！');
      await loadBriefs();
    } catch (e) {
      alert('AI 60秒情报更新：' + (e.message || e));
    } finally {
      if (btn) btn.disabled = false;
    }
  }

  // Bind Events
  if ($('model-search')) $('model-search').addEventListener('input', renderMatrix);
  if ($('filter-vendor')) $('filter-vendor').addEventListener('change', renderMatrix);
  if ($('filter-license')) $('filter-license').addEventListener('change', renderMatrix);
  if ($('filter-scale')) $('filter-scale').addEventListener('change', renderMatrix);
  if ($('btn-reset-filters')) $('btn-reset-filters').addEventListener('click', function () {
    if ($('model-search')) $('model-search').value = '';
    if ($('filter-vendor')) $('filter-vendor').value = '';
    if ($('filter-license')) $('filter-license').value = '';
    if ($('filter-scale')) $('filter-scale').value = '';
    renderMatrix();
  });

  if ($('btn-modal-close')) $('btn-modal-close').addEventListener('click', closeModal);
  if ($('btn-modal-cancel')) $('btn-modal-cancel').addEventListener('click', closeModal);
  if ($('spec-modal')) $('spec-modal').addEventListener('click', function (e) {
    if (e.target === $('spec-modal')) closeModal();
  });

  if ($('btn-run-ai60-scan')) $('btn-run-ai60-scan').addEventListener('click', triggerAi60Scan);

  // Init
  loadModels();
  loadBriefs();
})();
