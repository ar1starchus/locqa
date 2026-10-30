from __future__ import annotations

import html
import json
import os
from collections import Counter
from typing import Any, Dict, List

from locqa.models import Finding, IssueType, Severity


class Reporter:
    """Generates report.json and self-contained interactive HTML dashboards."""

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
    ) -> None:
        os.makedirs(os.path.dirname(os.path.abspath(output_path)), exist_ok=True)

        # Calculate statistics
        total = len(findings)
        by_sev = Counter(
            f.severity.value if isinstance(f.severity, Severity) else str(f.severity)
            for f in findings
        )
        by_type = Counter(
            f.issue_type.value if isinstance(f.issue_type, IssueType) else str(f.issue_type)
            for f in findings
        )

        rows_html: List[str] = []
        for idx, f in enumerate(findings, 1):
            sev = f.severity.value if isinstance(f.severity, Severity) else str(f.severity)
            itype = f.issue_type.value if isinstance(f.issue_type, IssueType) else str(f.issue_type)

            badge_color = {
                "high": "#ef4444",
                "medium": "#f59e0b",
                "low": "#3b82f6",
            }.get(sev.lower(), "#6b7280")

            k_esc = html.escape(f.key)
            s_esc = html.escape(f.source or "")
            t_esc = html.escape(f.target or "")
            e_esc = html.escape(f.evidence or "")
            sug_esc = html.escape(f.suggestion or "—")
            rev_badge = (
                '<span style="color:#10b981;font-weight:600;">✓ Да</span>'
                if f.reviewed_by_human
                else '<span style="color:#9ca3af;">—</span>'
            )

            row = f"""
            <tr data-sev="{sev}" data-type="{itype}">
              <td style="text-align:center;color:#6b7280;">{idx}</td>
              <td><code>{k_esc}</code></td>
              <td><span class="badge" style="background:#e0e7ff;color:#3730a3;">{itype}</span></td>
              <td><span class="badge" style="background:{badge_color}22;color:{badge_color};font-weight:bold;">{sev.upper()}</span></td>
              <td class="text-cell">{s_esc}</td>
              <td class="text-cell">{t_esc}</td>
              <td class="evidence-cell">{e_esc}</td>
              <td class="sug-cell">{sug_esc}</td>
              <td style="text-align:center;">{f.confidence:.2f}</td>
              <td style="text-align:center;">{rev_badge}</td>
            </tr>
            """
            rows_html.append(row)

        type_options = "".join(f'<option value="{t}">{t} ({c})</option>' for t, c in by_type.most_common())

        html_template = f"""<!DOCTYPE html>
<html lang="ru">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>Qazaq Loc QA — Отчет контроля качества локализации</title>
  <style>
    * {{ box-sizing: border-box; margin: 0; padding: 0; }}
    body {{ font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif; background: #f8fafc; color: #1e293b; padding: 24px; }}
    .header {{ margin-bottom: 24px; }}
    .header h1 {{ font-size: 26px; font-weight: 700; color: #0f172a; margin-bottom: 8px; }}
    .header p {{ color: #64748b; font-size: 14px; }}
    .stats-grid {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(180px, 1fr)); gap: 16px; margin-bottom: 24px; }}
    .card {{ background: #fff; padding: 18px; border-radius: 12px; border: 1px solid #e2e8f0; box-shadow: 0 1px 3px rgba(0,0,0,0.05); }}
    .card-title {{ font-size: 12px; text-transform: uppercase; color: #64748b; font-weight: 600; margin-bottom: 6px; }}
    .card-val {{ font-size: 28px; font-weight: 800; color: #0f172a; }}
    .controls {{ display: flex; flex-wrap: wrap; gap: 12px; margin-bottom: 18px; background: #fff; padding: 14px; border-radius: 10px; border: 1px solid #e2e8f0; }}
    .search-input {{ flex: 1; min-width: 240px; padding: 8px 12px; border: 1px solid #cbd5e1; border-radius: 6px; font-size: 14px; outline: none; }}
    .filter-select {{ padding: 8px 12px; border: 1px solid #cbd5e1; border-radius: 6px; font-size: 14px; background: #fff; }}
    .table-container {{ overflow-x: auto; background: #fff; border-radius: 12px; border: 1px solid #e2e8f0; box-shadow: 0 1px 3px rgba(0,0,0,0.05); }}
    table {{ width: 100%; border-collapse: collapse; font-size: 13px; text-align: left; }}
    th {{ background: #f1f5f9; padding: 12px 14px; font-weight: 600; color: #475569; border-bottom: 1px solid #e2e8f0; position: sticky; top: 0; }}
    td {{ padding: 10px 14px; border-bottom: 1px solid #f1f5f9; vertical-align: top; }}
    tr:hover td {{ background: #f8fafc; }}
    code {{ font-family: ui-monospace, SFMono-Regular, Menlo, monospace; font-size: 12px; color: #0284c7; word-break: break-all; }}
    .badge {{ display: inline-block; padding: 3px 8px; border-radius: 6px; font-size: 11px; font-weight: 600; white-space: nowrap; }}
    .text-cell {{ max-width: 220px; word-break: break-word; }}
    .evidence-cell {{ max-width: 260px; color: #475569; font-size: 12px; }}
    .sug-cell {{ max-width: 200px; color: #059669; font-weight: 500; word-break: break-word; }}
  </style>
</head>
<body>
  <div class="header">
    <h1>Qazaq Loc QA — Отчет контроля качества локализации</h1>
    <p>Анализ: <strong>{html.escape(source_name)}</strong> → <strong>{html.escape(target_name)}</strong> | Найдено замечаний: <strong>{total}</strong></p>
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
    <input type="text" id="searchInput" class="search-input" placeholder="Поиск по ключу, тексту или evidence...">
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
          <th>Перевод</th>
          <th>Обоснование (Evidence)</th>
          <th>Рекомендация</th>
          <th>Conf.</th>
          <th>Review</th>
        </tr>
      </thead>
      <tbody>
        {"".join(rows_html)}
      </tbody>
    </table>
  </div>

  <script>
    const searchInput = document.getElementById('searchInput');
    const severityFilter = document.getElementById('severityFilter');
    const typeFilter = document.getElementById('typeFilter');
    const table = document.getElementById('qaTable');
    const rows = table.querySelectorAll('tbody tr');

    function applyFilters() {{
      const q = searchInput.value.toLowerCase();
      const sev = severityFilter.value.toLowerCase();
      const type = typeFilter.value.toLowerCase();

      rows.forEach(r => {{
        const rSev = (r.getAttribute('data-sev') || '').toLowerCase();
        const rType = (r.getAttribute('data-type') || '').toLowerCase();
        const text = r.innerText.toLowerCase();

        const matchesQuery = !q || text.includes(q);
        const matchesSev = !sev || rSev === sev;
        const matchesType = !type || rType === type;

        if (matchesQuery && matchesSev && matchesType) {{
          r.style.display = '';
        }} else {{
          r.style.display = 'none';
        }}
      }});
    }}

    searchInput.addEventListener('input', applyFilters);
    severityFilter.addEventListener('change', applyFilters);
    typeFilter.addEventListener('change', applyFilters);
  </script>
</body>
</html>
"""
        with open(output_path, "w", encoding="utf-8") as f:
            f.write(html_template)
