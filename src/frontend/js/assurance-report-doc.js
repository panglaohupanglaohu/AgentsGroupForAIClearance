/**
 * 独立保障记录文档 —— 把 §9 记录渲染成单文件、可离线打开、可打印的交付物。
 *
 * 设计取向（tasteskill design read）：
 *   受监管保障文档 / 评审与法务小组 / trust-first 语言 / 档案式排版。
 *   DESIGN_VARIANCE 3 · MOTION_INTENSITY 1 · VISUAL_DENSITY 5。
 * 已锁定的三条系统规则，改动时不得单点破例：
 *   1. 圆角一律为 0（法律文书形态，不用卡片圆角）。
 *   2. 强调色只有一个：archive navy，仅用于结构件（章节编号、分隔线、页眉规则线）。
 *      pass/fail/needs_info 是功能性状态令牌，只出现在判定标签与门禁条带，不作装饰。
 *   3. 字体走系统栈：交付物须在离线、邮件与归档环境中稳定呈现，不得外链字体。
 */
(function (global) {
  'use strict';

  var STATUS_ZH = { pass: '通过', fail: '未通过', needs_info: '待补证', not_assessed: '未评估' };
  var OUTCOME = {
    approved: 'Approved · 批准',
    approved_with_conditions: 'Approved with Conditions · 有条件批准',
    restricted: 'Restricted · 受限',
    not_approved: 'Not Approved · 不批准'
  };

  function esc(v) {
    if (v === null || v === undefined || v === '') return '—';
    return String(v)
      .replace(/&/g, '&amp;')
      .replace(/</g, '&lt;')
      .replace(/>/g, '&gt;')
      .replace(/"/g, '&quot;')
      .replace(/'/g, '&#39;');
  }

  function list(items, empty) {
    var arr = (items || []).filter(function (x) { return x !== null && x !== undefined && x !== ''; });
    if (!arr.length) return '<p class="void">' + esc(empty) + '</p>';
    return '<ul>' + arr.map(function (t) { return '<li>' + esc(t) + '</li>'; }).join('') + '</ul>';
  }

  function meta(pairs) {
    return '<dl class="meta">' + pairs.map(function (p) {
      return '<div><dt>' + esc(p[0]) + '</dt><dd>' + esc(p[1]) + '</dd></div>';
    }).join('') + '</dl>';
  }

  function section(num, title, en, body) {
    return (
      '<section class="sec"><div class="sec-num">' + esc(num) + '</div>' +
      '<div class="sec-body"><h2>' + esc(title) + '<span>' + esc(en) + '</span></h2>' + body + '</div></section>'
    );
  }

  function gateStrip(rows) {
    return '<div class="strip">' + rows.map(function (m) {
      return '<div class="strip-cell ' + esc(m.verdict) + '"><b>' + esc(m.gate) + '</b>' +
        '<span>§' + esc(m.section) + '</span>' +
        '<i>' + esc(STATUS_ZH[m.verdict] || m.verdict) + '</i></div>';
    }).join('') + '</div>';
  }

  function decisionBanner(rec) {
    var d = rec.decision;
    if (!d) {
      return '<div class="decision pending"><p class="verdict">尚未产生保障裁决</p>' +
        '<p class="reason">本申请尚未完成门禁评审，本文档不构成任何准入结论。</p></div>';
    }
    var c = rec.conditions_and_restrictions;
    return (
      '<div class="decision ' + esc(d.verdict) + '">' +
      '<p class="verdict">' + esc(OUTCOME[d.verdict] || d.verdict) + '</p>' +
      '<p class="reason">' + esc(d.reason) + '</p>' +
      (d.hard_block ? '<p class="hardblock">命中标准 §3 禁止部署形态，该结论不受其它门禁结果影响。</p>' : '') +
      meta([
        ['运行时档位', d.runtime_profile],
        ['适用范围', (d.scope || []).join(' / ')],
        ['有效期至', c.expires_at],
        ['裁决时间', d.decided_at]
      ]) + '</div>'
    );
  }

  function artifactSection(rec) {
    var a = rec.artifact_assessed;
    var body = meta([
      ['模型标识', a.model_id],
      ['版本 Revision', a.revision],
      ['根摘要 Digest', a.root_digest],
      ['权重来源', a.weights_uri],
      ['预期签名主体', a.expected_signer_identity]
    ]);
    if ((a.custody_chain || []).length) {
      body += '<table><thead><tr><th>步骤</th><th>输入摘要</th><th>输出摘要</th><th>执行方</th><th>时间</th></tr></thead><tbody>' +
        a.custody_chain.map(function (s) {
          return '<tr><td>' + esc(s.step_type) + '</td><td class="mono">' + esc(s.input_digest) +
            '</td><td class="mono">' + esc(s.output_digest) + '</td><td>' + esc(s.performed_by) +
            '</td><td class="mono">' + esc(s.performed_at) + '</td></tr>';
        }).join('') + '</tbody></table>';
    } else {
      body += '<p class="void">未登记保管链步骤；血缘以 §6.1 扫描器证据为准。</p>';
    }
    return section('01', '受评的模型制品与版本', 'Model Artifact and Version Assessed', body);
  }

  function evidenceSection(rec) {
    var e = rec.evidence_reviewed;
    var body = '<p class="lede">本次评审复核裁决性证据 ' + e.decisive_count +
      ' 份、参考情报 ' + e.advisory_count + ' 份。' + esc(e.note) + '</p>';
    body += e.decisive.length
      ? '<table><thead><tr><th>门禁</th><th>检查项</th><th>采集器</th><th>采集时间</th><th>证据摘要</th><th>状态</th></tr></thead><tbody>' +
        e.decisive.map(function (it) {
          return '<tr><td>' + esc(it.gate) + ' §' + esc(it.section) + '</td><td class="mono">' + esc(it.check_id) +
            '</td><td>' + esc(it.collector) + '<span class="ver"> v' + esc(it.collector_version) + '</span></td>' +
            '<td class="mono">' + esc(it.collected_at) + '</td><td class="mono">' + esc((it.digest || '').slice(0, 24)) +
            '</td><td>' + esc(it.status) + '</td></tr>';
        }).join('') + '</tbody></table>'
      : '<p class="void">尚无裁决性证据。</p>';
    return section('02', '已复核的证据', 'Evidence Reviewed', body);
  }

  function advisoryRow(adv) {
    if (!adv) return '';
    if (adv.error) {
      return '<tr class="adv-row"><td colspan="4"><div class="adv err">' +
        '分析未生成：' + esc(adv.error) + '</div></td></tr>';
    }
    if (!adv.analysis && !adv.recommendation) return '';
    return '<tr class="adv-row"><td colspan="4"><div class="adv">' +
      (adv.analysis ? '<p><b>分析</b><span>' + esc(adv.analysis) + '</span></p>' : '') +
      (adv.recommendation ? '<p><b>建议</b><span>' + esc(adv.recommendation) + '</span></p>' : '') +
      (adv.risk_if_ignored ? '<p><b>不处理的风险</b><span>' + esc(adv.risk_if_ignored) + '</span></p>' : '') +
      '<p class="sig">参考性分析 · 由 ' + esc(adv.generated_by) + ' 于 ' + esc(adv.generated_at) +
      ' 生成。依标准 §5，本栏不参与门禁规则求值，不构成判定依据。</p>' +
      '</div></td></tr>';
  }

  function methodologySection(rec) {
    var body = rec.methodology_and_results.map(function (m) {
      var checks = m.checks.map(function (c) {
        return '<tr><td class="mono">' + esc(c.check_id) + '</td>' +
          '<td>' + esc(c.requirement) + '</td>' +
          '<td>' + (c.blocker ? '<span class="tag blocker">Blocker</span>' : '<span class="tag">—</span>') + '</td>' +
          '<td><span class="tag ' + esc(c.result) + '">' + esc(STATUS_ZH[c.result] || c.result) + '</span></td></tr>' +
          advisoryRow(c.advisory);
      }).join('');
      return (
        '<article class="gate ' + esc(m.verdict) + '">' +
        '<header><h3>' + esc(m.gate) + ' · §' + esc(m.section) + ' ' + esc(m.name) + '</h3>' +
        '<p class="en">' + esc(m.name_en) + '</p>' +
        '<p class="tags"><span class="tag ' + esc(m.verdict) + '">' + esc(STATUS_ZH[m.verdict] || m.verdict) + '</span>' +
        (m.hard_block ? '<span class="tag blocker">硬红线</span>' : '') +
        '<span class="tag">' + (m.checks_total - m.checks_failed) + '/' + m.checks_total + ' 检查项通过</span>' +
        '<span class="tag">责任职能 ' + esc(m.owner_role) + '</span></p></header>' +
        '<h4>标准要求覆盖点</h4>' + list(m.standard_criteria, '标准未列举细项') +
        '<h4>测试方法</h4>' + list(m.collectors, '本门未运行采集器') +
        '<h4>检查项结果</h4>' +
        '<table><thead><tr><th>检查项</th><th>标准要求</th><th>阻断</th><th>结果</th></tr></thead><tbody>' +
        checks + '</tbody></table>' +
        '<p class="foot">判定方 ' + esc(m.decided_by) + ' · 判定时间 ' + esc(m.decided_at) +
        ' · 引用证据 ' + (m.evidence_refs || []).length + ' 份</p>' +
        '</article>'
      );
    }).join('');
    return section('03', '测试方法与结果', 'Testing Methodology and Results', body);
  }

  function comparativeSection(rec) {
    var adv = rec.evidence_reviewed.advisory;
    if (!adv.length) {
      return section('04', '对比测试与外部情报', 'Comparative Testing and External Intelligence',
        '<p class="void">本次评审未引入外部采集与分析情报。</p>');
    }
    var body = '<p class="lede">下列情报由信息采集与分析团队产出，按标准 §5 仅作风险信号，不参与门禁规则求值。</p>';
    body += adv.map(function (it) {
      var an = it.analysis || {};
      var steps = (an.reasoning_steps || []).map(function (s) {
        return (s.stage || '') + '（' + (s.status || '') + '）' + (s.detail ? '：' + s.detail : '');
      });
      return '<article class="gate"><header><h3>' + esc(it.label || it.check_id) + '</h3>' +
        '<p class="tags"><span class="tag">' + esc(it.gate) + ' §' + esc(it.section) + '</span>' +
        '<span class="tag">' + esc(it.kind) + '</span>' +
        '<span class="tag">状态 ' + esc(it.status) + '</span></p></header>' +
        meta([['证据分', an.evidence_score], ['信号强度', an.signal_strength]]) +
        '<h4>推理链摘要</h4>' + list(steps, '该来源未记录推理步骤') +
        '<h4>待解问题</h4>' + list(an.open_questions, '无') +
        '</article>';
    }).join('');
    return section('04', '对比测试与外部情报', 'Comparative Testing and External Intelligence', body);
  }

  function findingsSection(rec) {
    var f = rec.findings_and_mitigations;
    var body = f.length
      ? '<table><thead><tr><th>门禁</th><th>检查项</th><th>发现</th><th>严重性</th><th>来源</th><th>缓解措施</th></tr></thead><tbody>' +
        f.map(function (it) {
          return '<tr><td>' + esc(it.gate) + ' §' + esc(it.section) + '</td>' +
            '<td class="mono">' + esc(it.check_id) + (it.blocker ? ' <span class="tag blocker">Blocker</span>' : '') + '</td>' +
            '<td>' + esc(it.finding) + '</td><td>' + esc(it.severity) + '</td><td>' + esc(it.source) +
            '</td><td>' + esc(it.mitigation) + '</td></tr>';
        }).join('') + '</tbody></table>'
      : '<p class="void">未产生未通过项或复核发现。</p>';
    return section('05', '重大发现与缓解措施', 'Material Findings and Mitigations', body);
  }

  function permittedUseSection(rec) {
    var u = rec.permitted_use;
    var body = meta([
      ['申请用途', u.label_zh + '（§' + u.section + '）'],
      ['需附加评估', u.requires_additional_assessment ? '是' : '否'],
      ['附加评估已完成', u.additional_assessment_complete ? '是' : '否'],
      ['用途要求', u.satisfied ? '满足' : '未满足']
    ]) + '<p class="lede">' + esc(u.note) + '</p>';
    if (u.requires_additional_assessment) {
      body += '<h4>§' + esc(u.section) + ' 附加评估条目</h4>' + list(u.additional_criteria, '标准未列举');
    }
    return section('09', '许可用途', 'Permitted Use', body);
  }

  function governanceSection(rec) {
    var g = rec.governance;
    var body = '<p class="lede">标准 §11 要求为每个模型在其保障生命周期内建立明确的问责归属。</p>' +
      meta([['申请人', g.applicant], ['具名负责人 Own', g.own]]) +
      '<h4>Evaluate 职能分工</h4><table><thead><tr><th>门禁</th><th>章节</th><th>责任职能</th></tr></thead><tbody>' +
      g.evaluate.map(function (x) {
        return '<tr><td>' + esc(x.gate) + '</td><td>§' + esc(x.section) + '</td><td>' + esc(x.owner_role) + '</td></tr>';
      }).join('') + '</tbody></table>' +
      '<div class="signoff">' +
      ['Evaluate · 评估职能', 'Approve · AI 治理机构', 'Own · 具名负责人'].map(function (role) {
        return '<div><span class="rule"></span><b>' + esc(role) + '</b><i>签署 / 日期</i></div>';
      }).join('') + '</div>';
    return section('10', '角色与治理', 'Roles and Governance', body);
  }

  function styles() {
    return [
      ':root{--paper:#fff;--wash:#f5f6f8;--ink:#0e1116;--ink2:#4b535e;--ink3:#79828d;',
      '--rule:#dde1e6;--accent:#17356b;--pass:#166534;--fail:#9f1239;--info:#8a5200;--none:#79828d;',
      "--sans:-apple-system,BlinkMacSystemFont,'Segoe UI','Noto Sans SC','PingFang SC','Microsoft YaHei',sans-serif;",
      "--mono:ui-monospace,SFMono-Regular,'SF Mono',Menlo,Consolas,monospace}",
      '*{box-sizing:border-box;border-radius:0}',
      'body{margin:0;background:var(--wash);color:var(--ink);font-family:var(--sans);',
      'font-size:14px;line-height:1.6;-webkit-font-smoothing:antialiased}',
      '.sheet{max-width:1080px;margin:0 auto;background:var(--paper);padding:64px 72px 96px;',
      'border-left:1px solid var(--rule);border-right:1px solid var(--rule);min-height:100vh}',
      // masthead：左对齐文档报头，不做居中 hero
      '.masthead{border-top:3px solid var(--accent);padding-top:22px}',
      '.masthead .std{font-family:var(--mono);font-size:11px;letter-spacing:.14em;text-transform:uppercase;color:var(--accent)}',
      '.masthead h1{margin:14px 0 4px;font-size:38px;line-height:1.1;letter-spacing:-.02em;font-weight:700;max-width:22ch}',
      '.masthead .subject{margin:0;font-family:var(--mono);font-size:15px;color:var(--ink2)}',
      '.masthead .issued{margin:18px 0 0;font-size:12px;color:var(--ink3)}',
      // decision：合规文档先给结论
      '.decision{margin:34px 0 0;padding:22px 24px;background:var(--wash);border-left:4px solid var(--none)}',
      '.decision.approved{border-color:var(--pass)}.decision.approved_with_conditions{border-color:var(--accent)}',
      '.decision.restricted{border-color:var(--info)}.decision.not_approved{border-color:var(--fail)}',
      '.decision .verdict{margin:0;font-size:22px;font-weight:700;letter-spacing:-.01em}',
      '.decision.approved .verdict{color:var(--pass)}.decision.restricted .verdict{color:var(--info)}',
      '.decision.not_approved .verdict{color:var(--fail)}.decision.approved_with_conditions .verdict{color:var(--accent)}',
      '.decision .reason{margin:6px 0 0;color:var(--ink2)}',
      '.decision .hardblock{margin:8px 0 0;font-size:12px;color:var(--fail);font-weight:600}',
      // gate strip：真实数据条带，不是装饰图
      '.strip{display:grid;grid-template-columns:repeat(9,1fr);gap:1px;background:var(--rule);',
      'border:1px solid var(--rule);margin:26px 0 0}',
      '.strip-cell{background:var(--paper);padding:10px 6px;text-align:center;border-top:3px solid var(--none)}',
      '.strip-cell.pass{border-top-color:var(--pass)}.strip-cell.fail{border-top-color:var(--fail)}',
      '.strip-cell.needs_info{border-top-color:var(--info)}',
      '.strip-cell b{display:block;font-size:13px}.strip-cell span{display:block;font-family:var(--mono);font-size:10px;color:var(--ink3)}',
      '.strip-cell i{display:block;margin-top:3px;font-style:normal;font-size:10px;color:var(--ink2)}',
      // sections：左栏编号 + 内容列
      '.sec{display:grid;grid-template-columns:72px minmax(0,1fr);gap:24px;margin-top:52px;',
      'padding-top:20px;border-top:1px solid var(--rule)}',
      '.sec-num{font-family:var(--mono);font-size:13px;color:var(--accent);letter-spacing:.1em;padding-top:4px}',
      '.sec h2{margin:0 0 14px;font-size:20px;letter-spacing:-.01em}',
      '.sec h2 span{display:block;font-size:11px;font-weight:400;letter-spacing:.12em;',
      'text-transform:uppercase;color:var(--ink3);margin-top:4px}',
      '.sec h4{margin:16px 0 6px;font-size:12px;letter-spacing:.08em;text-transform:uppercase;color:var(--ink2)}',
      '.lede{margin:0 0 12px;color:var(--ink2);max-width:72ch}',
      '.void{margin:8px 0;color:var(--ink3);font-style:italic}',
      'ul{margin:6px 0 0;padding-left:18px}li{margin:2px 0;color:var(--ink2);max-width:72ch}',
      'table{width:100%;border-collapse:collapse;margin:10px 0 0;font-size:12px}',
      'th,td{padding:7px 9px;text-align:left;vertical-align:top;border-bottom:1px solid var(--rule)}',
      'th{background:var(--wash);font-size:11px;letter-spacing:.06em;text-transform:uppercase;color:var(--ink2)}',
      '.mono{font-family:var(--mono);font-size:11px;word-break:break-all}',
      '.ver{color:var(--ink3)}',
      '.meta{display:grid;grid-template-columns:repeat(auto-fit,minmax(190px,1fr));gap:12px 24px;margin:12px 0 0}',
      '.meta dt{font-size:11px;letter-spacing:.06em;text-transform:uppercase;color:var(--ink3)}',
      '.meta dd{margin:2px 0 0;font-family:var(--mono);font-size:12px;word-break:break-all}',
      '.gate{margin:18px 0 0;padding:16px 18px;border:1px solid var(--rule);border-left:3px solid var(--none)}',
      '.gate.pass{border-left-color:var(--pass)}.gate.fail{border-left-color:var(--fail)}',
      '.gate.needs_info{border-left-color:var(--info)}',
      '.gate h3{margin:0;font-size:15px}',
      '.gate .en{margin:2px 0 0;font-size:11px;letter-spacing:.08em;text-transform:uppercase;color:var(--ink3)}',
      '.gate .tags{margin:10px 0 0;display:flex;flex-wrap:wrap;gap:6px}',
      '.gate .foot{margin:12px 0 0;font-size:11px;color:var(--ink3)}',
      '.tag{display:inline-block;padding:2px 8px;font-size:11px;border:1px solid var(--rule);color:var(--ink2)}',
      '.tag.pass{border-color:var(--pass);color:var(--pass)}.tag.fail{border-color:var(--fail);color:var(--fail)}',
      '.tag.needs_info{border-color:var(--info);color:var(--info)}',
      '.tag.blocker{border-color:var(--fail);color:var(--fail);font-weight:600}',
      // 参考性分析：灰阶收窄，视觉上明确低于判定信息一级
      '.adv-row td{padding:0 9px 10px;border-bottom:1px solid var(--rule)}',
      '.adv{border-left:2px solid var(--ink3);background:var(--wash);padding:9px 12px}',
      '.adv.err{border-left-color:var(--info);color:var(--info)}',
      '.adv p{margin:0 0 4px;font-size:11px;line-height:1.55;display:flex;gap:8px}',
      '.adv p b{flex:0 0 76px;color:var(--accent);font-weight:600}',
      '.adv p span{color:var(--ink2)}',
      '.adv .sig{display:block;margin:6px 0 0;font-size:10px;color:var(--ink3)}',
      '.signoff{display:grid;grid-template-columns:repeat(3,1fr);gap:26px;margin:30px 0 0}',
      '.signoff .rule{display:block;border-bottom:1px solid var(--ink);height:44px}',
      '.signoff b{display:block;margin-top:8px;font-size:12px}',
      '.signoff i{display:block;font-style:normal;font-size:11px;color:var(--ink3)}',
      '.colophon{margin-top:56px;padding-top:18px;border-top:1px solid var(--rule);font-size:11px;color:var(--ink3);max-width:80ch}',
      '@media(max-width:820px){.sheet{padding:36px 22px 64px}.sec{grid-template-columns:1fr;gap:8px}',
      '.strip{grid-template-columns:repeat(3,1fr)}.signoff{grid-template-columns:1fr}',
      '.masthead h1{font-size:28px}table{font-size:11px}}',
      '@page{size:A4;margin:16mm 14mm}',
      '@media print{body{background:#fff}.sheet{max-width:none;border:0;padding:0}',
      '.gate,.sec,table,.signoff{break-inside:avoid}.sec{border-top-color:#000}',
      '.strip{break-inside:avoid}}'
    ].join('');
  }

  function build(rec) {
    if (!rec) throw new Error('assurance record is required');
    var a = rec.artifact_assessed;
    var app = rec.application;
    var title = '保障记录 · ' + (a.model_id || '未指定模型');

    var doc =
      '<!doctype html><html lang="zh-CN"><head><meta charset="utf-8">' +
      '<meta name="viewport" content="width=device-width,initial-scale=1">' +
      '<title>' + esc(title) + '</title>' +
      '<meta name="description" content="' + esc(rec.standard.name) + ' §9 保障记录">' +
      '<style>' + styles() + '</style></head><body><main class="sheet">' +
      '<header class="masthead">' +
      '<p class="std">' + esc(rec.standard.name) + ' · v' + esc(rec.standard.version) + ' · §9</p>' +
      '<h1>保障记录<br>Assurance Record</h1>' +
      '<p class="subject">' + esc(a.model_id) + ' @ ' + esc(a.revision) + '</p>' +
      '<p class="issued">申请单号 ' + esc(app.application_id) + ' · 申请人 ' + esc(app.applicant) +
      ' · 生成于 ' + esc(rec.generated_at) + ' · 流程状态 ' + esc(app.status) + '</p>' +
      '</header>' +
      decisionBanner(rec) +
      gateStrip(rec.methodology_and_results) +
      artifactSection(rec) +
      evidenceSection(rec) +
      methodologySection(rec) +
      comparativeSection(rec) +
      findingsSection(rec) +
      section('06', '残余风险', 'Residual Risks',
        '<p class="lede">标准 §5 要求显式记录无法完全控制或独立验证的风险。</p>' +
        list(rec.residual_risks, '未记录残余风险')) +
      section('07', '条件、限制与例外', 'Conditions, Restrictions and Exceptions',
        '<h4>条件</h4>' + list(rec.conditions_and_restrictions.conditions, '无附加条件') +
        '<h4>例外与偏离 §12</h4>' + list(rec.conditions_and_restrictions.exceptions,
          '未登记例外。任何例外须正式记录、由适当权限风险接受并定期复审。')) +
      section('08', '最终保障裁决', 'Final Assurance Decision', decisionBanner(rec)) +
      permittedUseSection(rec) +
      governanceSection(rec) +
      '<p class="colophon">本文档由 AI 模型准入控制台依据 ' + esc(rec.standard.name) + ' v' +
      esc(rec.standard.version) + ' §9 自动装配，内容取自该次评审的门禁裁决与证据记录。' +
      '列入已批准模型目录不构成对全部用途的无限制批准；许可用途仍受部署、数据、权限、地域、客户与用例要求约束。' +
      '仅供 Lenovo 内部治理使用。</p>' +
      '</main></body></html>';
    return doc;
  }

  global.AssuranceReportDoc = { build: build, escapeText: esc };
})(typeof window !== 'undefined' ? window : globalThis);
