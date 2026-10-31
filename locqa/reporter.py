from __future__ import annotations

import html
import json
import os
from collections import Counter
from typing import Any, Dict, List

from locqa.models import Finding, IssueType, Severity


class Reporter:
    """Generates report.json and self-contained interactive HTML dashboards
    with a complete human-in-the-loop review pipeline.
    """

    @classmethod
    def save_json(cls, findings: List[Finding], output_path: str) -> None:
        os.makedirs(os.path.dirname(os.path.abspath(output_path)), exist_ok=True)
        data = [f.to_dict() for f in findings]
        with open(output_path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)

    @classmethod
    def save_html(
        cls,
        findings: List[Finding],
        output_path: str,
        source_name: str = "intl_ru.arb",
        target_name: str = "intl_kk.arb",
        target_raw_content: str = "",
    ) -> None:
        os.makedirs(os.path.dirname(os.path.abspath(output_path)), exist_ok=True)

        total = len(findings)
        with_sug = sum(1 for f in findings if f.suggestion)
        by_sev = Counter(
            f.severity.value if isinstance(f.severity, Severity) else str(f.severity)
            for f in findings
        )
        by_type = Counter(
            f.issue_type.value if isinstance(f.issue_type, IssueType) else str(f.issue_type)
            for f in findings
        )

        rows_html: List[str] = []
        findings_json_list: List[Dict[str, Any]] = []

        for idx, f in enumerate(findings, 1):
            sev = f.severity.value if isinstance(f.severity, Severity) else str(f.severity)
            itype = f.issue_type.value if isinstance(f.issue_type, IssueType) else str(f.issue_type)
            findings_json_list.append(f.to_dict())

            badge_color = {
                "high": "#ef4444",
                "medium": "#f59e0b",
                "low": "#3b82f6",
            }.get(sev.lower(), "#6b7280")

            k_esc = html.escape(f.key)
            s_esc = html.escape(f.source or "")
            t_esc = html.escape(f.target or "")
            e_esc = html.escape(f.evidence or "")
            sug_val = f.suggestion or ""
            sug_esc = html.escape(sug_val)

            has_sug = bool(f.suggestion)
            btn_html = ""
            if has_sug:
                btn_html = f"""
                <button type="button" class="btn-approve" onclick="toggleApprove('{k_esc}')" id="btn-{k_esc}">
                  Одобрить
                </button>
                """
            else:
                btn_html = '<span style="color:#94a3b8;font-size:12px;">—</span>'

            sug_rows = max(1, min(6, sug_val.count("\n") + 1))
            sug_cell = (
                f'<textarea class="sug-input" id="sug-{k_esc}" rows="{sug_rows}" oninput="updateCustomSuggestion(\'{k_esc}\', this.value)" onchange="updateCustomSuggestion(\'{k_esc}\', this.value)">{sug_esc}</textarea>'
                if has_sug
                else '<span style="color:#94a3b8;">—</span>'
            )

            row = f"""
            <tr data-sev="{sev}" data-type="{itype}" id="row-{k_esc}" data-key="{k_esc}" data-has-sug="{str(has_sug).lower()}" data-conf="{f.confidence}">
              <td style="text-align:center;color:#6b7280;">{idx}</td>
              <td><code>{k_esc}</code></td>
              <td><span class="badge" style="background:#e0e7ff;color:#3730a3;">{itype}</span></td>
              <td><span class="badge" style="background:{badge_color}22;color:{badge_color};font-weight:bold;">{sev.upper()}</span></td>
              <td class="text-cell">{s_esc}</td>
              <td class="text-cell">{t_esc}</td>
              <td class="evidence-cell">{e_esc}</td>
              <td class="sug-cell">{sug_cell}</td>
              <td style="text-align:center;">{f.confidence:.2f}</td>
              <td style="text-align:center;" id="action-{k_esc}">{btn_html}</td>
            </tr>
            """
            rows_html.append(row)

        type_options = "".join(f'<option value="{t}">{t} ({c})</option>' for t, c in by_type.most_common())
        findings_json_str = json.dumps(findings_json_list, ensure_ascii=False)
        target_raw_escaped = json.dumps(target_raw_content, ensure_ascii=False)

        html_template = f"""<!DOCTYPE html>
<html lang="ru">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>Qazaq Loc QA — Отчет и конвейер верификации</title>
  <style>
    * {{ box-sizing: border-box; margin: 0; padding: 0; }}
    body {{ font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif; background: #f8fafc; color: #1e293b; padding: 24px; padding-bottom: 80px; }}
    .header {{ margin-bottom: 20px; }}
    .header h1 {{ font-size: 26px; font-weight: 700; color: #0f172a; margin-bottom: 6px; }}
    .header p {{ color: #64748b; font-size: 14px; }}
    
    .stats-grid {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(160px, 1fr)); gap: 14px; margin-bottom: 20px; }}
    .card {{ background: #fff; padding: 16px; border-radius: 10px; border: 1px solid #e2e8f0; box-shadow: 0 1px 3px rgba(0,0,0,0.04); }}
    .card-title {{ font-size: 12px; text-transform: uppercase; color: #64748b; font-weight: 600; margin-bottom: 4px; }}
    .card-val {{ font-size: 26px; font-weight: 800; color: #0f172a; }}
    
    .review-toolbar {{ background: #0f172a; color: #fff; padding: 16px 20px; border-radius: 12px; margin-bottom: 20px; display: flex; flex-wrap: wrap; align-items: center; justify-content: space-between; gap: 14px; box-shadow: 0 4px 12px rgba(15,23,42,0.15); }}
    .toolbar-info {{ display: flex; align-items: center; gap: 14px; }}
    .toolbar-info span.counter {{ background: #10b981; color: #fff; padding: 4px 12px; border-radius: 20px; font-weight: 700; font-size: 14px; }}
    .toolbar-actions {{ display: flex; flex-wrap: wrap; gap: 10px; }}
    .btn {{ padding: 8px 14px; border-radius: 8px; font-size: 13px; font-weight: 600; cursor: pointer; border: none; transition: all 0.15s ease; }}
    .btn-primary {{ background: #3b82f6; color: #fff; }}
    .btn-primary:hover {{ background: #2563eb; }}
    .btn-success {{ background: #10b981; color: #fff; }}
    .btn-success:hover {{ background: #059669; }}
    .btn-outline {{ background: transparent; color: #cbd5e1; border: 1px solid #475569; }}
    .btn-outline:hover {{ background: #1e293b; color: #fff; }}
    
    .controls {{ display: flex; flex-wrap: wrap; gap: 12px; margin-bottom: 16px; background: #fff; padding: 12px 16px; border-radius: 10px; border: 1px solid #e2e8f0; }}
    .search-input {{ flex: 1; min-width: 240px; padding: 8px 12px; border: 1px solid #cbd5e1; border-radius: 6px; font-size: 14px; outline: none; }}
    .filter-select {{ padding: 8px 12px; border: 1px solid #cbd5e1; border-radius: 6px; font-size: 14px; background: #fff; }}
    
    .table-container {{ overflow-x: auto; background: #fff; border-radius: 12px; border: 1px solid #e2e8f0; box-shadow: 0 1px 3px rgba(0,0,0,0.05); }}
    table {{ width: 100%; border-collapse: collapse; font-size: 13px; text-align: left; }}
    th {{ background: #f1f5f9; padding: 12px 14px; font-weight: 600; color: #475569; border-bottom: 1px solid #e2e8f0; position: sticky; top: 0; z-index: 10; }}
    td {{ padding: 10px 14px; border-bottom: 1px solid #f1f5f9; vertical-align: top; }}
    tr:hover td {{ background: #f8fafc; }}
    tr.row-approved {{ background: #ecfdf5 !important; }}
    tr.row-approved td {{ border-bottom-color: #d1fae5; }}
    
    code {{ font-family: ui-monospace, SFMono-Regular, Menlo, monospace; font-size: 12px; color: #0284c7; word-break: break-all; }}
    .badge {{ display: inline-block; padding: 3px 8px; border-radius: 6px; font-size: 11px; font-weight: 600; white-space: nowrap; }}
    .text-cell {{ max-width: 240px; word-break: break-word; white-space: pre-wrap; line-height: 1.4; }}
    .evidence-cell {{ max-width: 260px; color: #475569; font-size: 12px; line-height: 1.4; }}
    .sug-cell {{ min-width: 220px; }}
    .sug-input {{ width: 100%; min-width: 200px; padding: 6px 10px; border: 1px solid #a7f3d0; background: #f0fdf4; border-radius: 6px; font-size: 13px; font-family: inherit; color: #065f46; font-weight: 500; outline: none; resize: vertical; white-space: pre-wrap; line-height: 1.4; box-sizing: border-box; }}
    .sug-input:focus {{ border-color: #10b981; background: #fff; box-shadow: 0 0 0 2px rgba(16,185,129,0.2); }}
    
    .btn-approve {{ background: #fff; border: 1px solid #cbd5e1; color: #475569; padding: 6px 12px; border-radius: 6px; font-size: 12px; font-weight: 600; cursor: pointer; transition: all 0.15s; }}
    .btn-approve:hover {{ border-color: #10b981; color: #059669; }}
    .btn-approved {{ background: #10b981 !important; color: #fff !important; border-color: #10b981 !important; }}
  </style>
</head>
<body>
  <div class="header">
    <h1>Qazaq Loc QA — Конвейер верификации локализации</h1>
    <p>Анализ: <strong>{html.escape(source_name)}</strong> → <strong>{html.escape(target_name)}</strong> | Найдено замечаний: <strong>{total}</strong> (из них с готовыми предложениями: <strong>{with_sug}</strong>)</p>
  </div>

  <div class="review-toolbar">
    <div class="toolbar-info">
      <div>
        <div style="font-size:12px;color:#94a3b8;text-transform:uppercase;font-weight:600;">Верификация носителем языка:</div>
        <div style="font-size:16px;font-weight:700;">Одобрено правок: <span class="counter" id="approvedCounter">0</span> из {with_sug}</div>
      </div>
    </div>
    <div class="toolbar-actions">
      <button class="btn btn-outline" onclick="approveHighConfidence()">⚡ Одобрить надежные (Conf ≥ 0.95)</button>
      <button class="btn btn-outline" onclick="approveAllWithSuggestions()">⚡ Одобрить все</button>
      <button class="btn btn-outline" onclick="resetApprovals()">✕ Сбросить</button>
      <button class="btn btn-success" onclick="downloadFixedArb()">📥 Скачать intl_kk_fixed.arb</button>
      <button class="btn btn-primary" onclick="downloadReportJson()">📥 Скачать report.json</button>
    </div>
  </div>

  <div class="stats-grid">
    <div class="card">
      <div class="card-title">Всего находок</div>
      <div class="card-val">{total}</div>
    </div>
    <div class="card">
      <div class="card-title" style="color:#ef4444;">High Severity</div>
      <div class="card-val" style="color:#ef4444;">{by_sev.get("high", 0)}</div>
    </div>
    <div class="card">
      <div class="card-title" style="color:#f59e0b;">Medium Severity</div>
      <div class="card-val" style="color:#f59e0b;">{by_sev.get("medium", 0)}</div>
    </div>
    <div class="card">
      <div class="card-title" style="color:#3b82f6;">Low Severity</div>
      <div class="card-val" style="color:#3b82f6;">{by_sev.get("low", 0)}</div>
    </div>
  </div>

  <div class="controls">
    <input type="text" id="searchInput" class="search-input" placeholder="Поиск по ключу, тексту, evidence или предложению...">
    <select id="severityFilter" class="filter-select">
      <option value="">Все уровни важности</option>
      <option value="high">High ({by_sev.get("high", 0)})</option>
      <option value="medium">Medium ({by_sev.get("medium", 0)})</option>
      <option value="low">Low ({by_sev.get("low", 0)})</option>
    </select>
    <select id="typeFilter" class="filter-select">
      <option value="">Все типы ошибок</option>
      {type_options}
    </select>
    <select id="approvalFilter" class="filter-select">
      <option value="">Все статусы</option>
      <option value="approved">Только одобренные</option>
      <option value="pending">Требуют решения</option>
    </select>
  </div>

  <div class="table-container">
    <table id="qaTable">
      <thead>
        <tr>
          <th>#</th>
          <th>Ключ</th>
          <th>Тип ошибки</th>
          <th>Важность</th>
          <th>Исходник (RU)</th>
          <th>Текущий перевод</th>
          <th>Обоснование (Evidence)</th>
          <th>Предложение (Suggestion)</th>
          <th>Conf.</th>
          <th>Действие</th>
        </tr>
      </thead>
      <tbody>
        {"".join(rows_html)}
      </tbody>
    </table>
  </div>

  <script>
    const findingsData = {findings_json_str};
    const targetRawContent = {target_raw_escaped};

    // State of approved keys and custom suggestions
    let approvals = JSON.parse(localStorage.getItem('locqa_approvals') || '{{}}');
    let customSuggestions = JSON.parse(localStorage.getItem('locqa_custom_sug') || '{{}}');

    function updateCounter() {{
      const count = Object.values(approvals).filter(Boolean).length;
      document.getElementById('approvedCounter').innerText = count;
    }}

    function toggleApprove(key) {{
      const isApproved = !approvals[key];
      approvals[key] = isApproved;
      localStorage.setItem('locqa_approvals', JSON.stringify(approvals));

      const row = document.getElementById('row-' + key);
      const btn = document.getElementById('btn-' + key);
      if (isApproved) {{
        row.classList.add('row-approved');
        btn.classList.add('btn-approved');
        btn.innerText = '✓ Одобрено';
      }} else {{
        row.classList.remove('row-approved');
        btn.classList.remove('btn-approved');
        btn.innerText = 'Одобрить';
      }}
      updateCounter();
    }}

    function updateCustomSuggestion(key, value) {{
      customSuggestions[key] = value;
      localStorage.setItem('locqa_custom_sug', JSON.stringify(customSuggestions));
    }}

    function approveHighConfidence() {{
      findingsData.forEach(f => {{
        if (f.suggestion && f.confidence >= 0.95) {{
          approvals[f.key] = true;
          const row = document.getElementById('row-' + f.key);
          const btn = document.getElementById('btn-' + f.key);
          if (row && btn) {{
            row.classList.add('row-approved');
            btn.classList.add('btn-approved');
            btn.innerText = '✓ Одобрено';
          }}
        }}
      }});
      localStorage.setItem('locqa_approvals', JSON.stringify(approvals));
      updateCounter();
    }}

    function approveAllWithSuggestions() {{
      findingsData.forEach(f => {{
        if (f.suggestion) {{
          approvals[f.key] = true;
          const row = document.getElementById('row-' + f.key);
          const btn = document.getElementById('btn-' + f.key);
          if (row && btn) {{
            row.classList.add('row-approved');
            btn.classList.add('btn-approved');
            btn.innerText = '✓ Одобрено';
          }}
        }}
      }});
      localStorage.setItem('locqa_approvals', JSON.stringify(approvals));
      updateCounter();
    }}

    function resetApprovals() {{
      approvals = {{}};
      customSuggestions = {{}};
      localStorage.removeItem('locqa_approvals');
      localStorage.removeItem('locqa_custom_sug');
      document.querySelectorAll('tr.row-approved').forEach(r => r.classList.remove('row-approved'));
      document.querySelectorAll('.btn-approved').forEach(b => {{
        b.classList.remove('btn-approved');
        b.innerText = 'Одобрить';
      }});
      findingsData.forEach(f => {{
        if (f.suggestion) {{
          const inp = document.getElementById('sug-' + f.key);
          if (inp) inp.value = f.suggestion;
        }}
      }});
      updateCounter();
    }}

    // Export report.json with reviewed_by_human status
    function downloadReportJson() {{
      const updated = findingsData.map(f => {{
        const isApproved = Boolean(approvals[f.key]);
        const customSug = customSuggestions[f.key];
        return {{
          ...f,
          suggestion: customSug !== undefined ? customSug : f.suggestion,
          reviewed_by_human: isApproved
        }};
      }});

      const blob = new Blob([JSON.stringify(updated, null, 2)], {{ type: 'application/json' }});
      const url = URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url;
      a.download = 'report.json';
      a.click();
      URL.revokeObjectURL(url);
    }}

    // Export compliant intl_kk_fixed.arb with reviewed metadata
    function downloadFixedArb() {{
      let content = targetRawContent;
      // Parse JSON pairs
      let parsed;
      try {{
        parsed = JSON.parse(content);
      }} catch(e) {{
        alert('Не удалось распарсить исходный ARB: ' + e);
        return;
      }}

      // Build output with approved replacements and @key metadata
      const lines = ['{{'];
      const writtenKeys = new Set();
      const keys = Object.keys(parsed);

      keys.forEach((k, idx) => {{
        if (k.startsWith('@')) return; // handled with pairs
        const isApproved = Boolean(approvals[k]);
        let val = parsed[k];

        if (isApproved) {{
          const customSug = customSuggestions[k];
          const f = findingsData.find(item => item.key === k);
          const finalVal = customSug !== undefined ? customSug : (f ? f.suggestion : val);
          val = finalVal;
        }}

        lines.push('  ' + JSON.stringify(k) + ': ' + JSON.stringify(val) + ',');
        writtenKeys.add(k);

        // If approved by human, write metadata @key immediately following
        if (isApproved) {{
          const f = findingsData.find(item => item.key === k);
          const metaObj = {{
            reviewed_by_human: true,
            issue_type: f ? f.issue_type : 'manual_review',
            previous_value: parsed[k]
          }};
          lines.push('  ' + JSON.stringify('@' + k) + ': ' + JSON.stringify(metaObj, null, 2).replace(/\\n/g, '\\n  ') + ',');
        }} else if (parsed['@' + k]) {{
          lines.push('  ' + JSON.stringify('@' + k) + ': ' + JSON.stringify(parsed['@' + k], null, 2).replace(/\\n/g, '\\n  ') + ',');
        }}
      }});

      // Fix trailing comma
      for (let i = lines.length - 1; i >= 0; i--) {{
        if (lines[i].endsWith(',')) {{
          lines[i] = lines[i].slice(0, -1);
          break;
        }}
      }}
      lines.push('}}');

      const fullArbText = lines.join('\\n');
      const blob = new Blob([fullArbText], {{ type: 'application/json' }});
      const url = URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url;
      a.download = 'intl_kk_fixed.arb';
      a.click();
      URL.revokeObjectURL(url);
    }}

    // Filter logic
    function applyFilters() {{
      const q = document.getElementById('searchInput').value.toLowerCase();
      const sev = document.getElementById('severityFilter').value.toLowerCase();
      const type = document.getElementById('typeFilter').value.toLowerCase();
      const approval = document.getElementById('approvalFilter').value;

      document.querySelectorAll('#qaTable tbody tr').forEach(r => {{
        const k = r.getAttribute('data-key');
        const rSev = (r.getAttribute('data-sev') || '').toLowerCase();
        const rType = (r.getAttribute('data-type') || '').toLowerCase();
        const text = r.innerText.toLowerCase();
        const isApproved = Boolean(approvals[k]);

        const matchesQuery = !q || text.includes(q);
        const matchesSev = !sev || rSev === sev;
        const matchesType = !type || rType === type;
        const matchesApproval = !approval || (approval === 'approved' && isApproved) || (approval === 'pending' && !isApproved);

        if (matchesQuery && matchesSev && matchesType && matchesApproval) {{
          r.style.display = '';
        }} else {{
          r.style.display = 'none';
        }}
      }});
    }}

    document.getElementById('searchInput').addEventListener('input', applyFilters);
    document.getElementById('severityFilter').addEventListener('change', applyFilters);
    document.getElementById('typeFilter').addEventListener('change', applyFilters);
    document.getElementById('approvalFilter').addEventListener('change', applyFilters);

    // Initial state restore
    window.addEventListener('DOMContentLoaded', () => {{
      Object.keys(approvals).forEach(k => {{
        if (approvals[k]) {{
          const row = document.getElementById('row-' + k);
          const btn = document.getElementById('btn-' + k);
          if (row && btn) {{
            row.classList.add('row-approved');
            btn.classList.add('btn-approved');
            btn.innerText = '✓ Одобрено';
          }}
        }}
      }});
      Object.keys(customSuggestions).forEach(k => {{
        const inp = document.getElementById('sug-' + k);
        if (inp) inp.value = customSuggestions[k];
      }});
      updateCounter();
    }});
  </script>
</body>
</html>
"""
        with open(output_path, "w", encoding="utf-8") as f:
            f.write(html_template)
