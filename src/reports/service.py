"""Report generation service — Phase 4, Task 62-63.

Generates structured report data and exports to CSV, PDF, and Excel.
All data is pulled live from the database — no hard-coded values.

Report types:
  progress     — per-employee progress (modules, tasks, quizzes, status)
  coverage     — per-role mandatory requirement coverage
  hallucination — flagged items from validation reports
  traceability — source traceability score per plan
  comparison   — GenAI/Python comparison (≥100 rows from d6 report)
  audit        — recent audit trail entries
"""

from __future__ import annotations

import csv
import io
import json
from datetime import datetime
from pathlib import Path
from typing import Any

from sqlalchemy.orm import Session

from config.settings import settings
from role_matrix.repository import RoleMatrixRepository
from src.employees.service import EmployeeService
from src.documents.repository import DocumentRepository
from src.plans.models import OnboardingPlan
from src.plans.repository import PlanRepository
from src.reviews.models import AuditEntry, ValidationReportRecord
from src.reviews.service import ValidationReportRepository


class ReportService:
    """Generates tabular report data and exports to CSV / PDF / Excel (Task 62-63)."""

    def __init__(self, session: Session) -> None:
        """Inject the shared database session."""
        self._session = session
        self._employees = EmployeeService(session)
        self._plans = PlanRepository(session)
        self._matrix = RoleMatrixRepository(session)
        self._reports = ValidationReportRepository(session)
        self._documents = DocumentRepository(session)

    # ------------------------------------------------------------------
    # Report data
    # ------------------------------------------------------------------

    def get_report(self, report_type: str) -> dict[str, Any]:
        """Return columns, rows, chart_json, and title for a report type.

        Args:
            report_type: One of progress|coverage|hallucination|traceability|comparison|audit.

        Returns:
            Dict with keys: title (str), columns (list[str]), rows (list[dict]),
            chart_json (str|None).
        """
        dispatch = {
            "progress":      self._report_progress,
            "coverage":      self._report_coverage,
            "hallucination": self._report_hallucination,
            "traceability":  self._report_traceability,
            "comparison":    self._report_comparison,
            "audit":         self._report_audit,
        }
        fn = dispatch.get(report_type, self._report_progress)
        return fn()

    def _report_progress(self) -> dict[str, Any]:
        """Per-employee progress report."""
        employees = self._employees.list_employees()
        all_plans: list[OnboardingPlan] = self._session.query(OnboardingPlan).all()
        plan_map: dict[int, OnboardingPlan] = {}
        for p in all_plans:
            plan_map.setdefault(p.employee_id, p)

        rows = []
        for emp in employees:
            plan = plan_map.get(emp.id)
            vr = None
            if plan:
                vr = self._reports.get_by_plan(plan.id)

            rows.append({
                "Employee Code": emp.employee_code,
                "Name": emp.name,
                "Department": emp.department,
                "Role": emp.role.title if emp.role else "—",
                "Experience": emp.experience_level,
                "Training Status": emp.training_status.replace("_", " ").title(),
                "Plan ID": plan.id if plan else None,
                "Coverage Score": round(vr.coverage_score, 1) if vr and vr.coverage_score else None,
                "Traceability Score": round(vr.traceability_score, 1) if vr and vr.traceability_score else None,
                "Verification Status": (vr.overall_status if vr else None),
            })

        chart = self._bar_chart(
            x=[r["Name"] for r in rows],
            y=[r["Coverage Score"] or 0 for r in rows],
            name="Coverage %",
            color="#0F766E",
            title="Coverage Score by Employee",
        )
        return {"title": "Employee Progress Report", "columns": list(rows[0].keys()) if rows else [], "rows": rows, "chart_json": chart}

    def _report_coverage(self) -> dict[str, Any]:
        """Per-role mandatory requirement coverage report."""
        all_entries = self._matrix.list_all()
        all_plans: list[OnboardingPlan] = self._session.query(OnboardingPlan).all()
        all_reports = self._reports.list_all()

        # role → coverage_score
        role_scores: dict[str, list[float]] = {}
        for plan in all_plans:
            for report in all_reports:
                if report.plan_id == plan.id and report.coverage_score is not None:
                    sj = plan.structured_json or {}
                    role = sj.get("role_title", "")
                    if role:
                        role_scores.setdefault(role, []).append(report.coverage_score)

        role_matrix: dict[str, dict] = {}
        for e in all_entries:
            rm = role_matrix.setdefault(e.role, {"total": 0, "mandatory": 0})
            rm["total"] += 1
            if e.mandatory:
                rm["mandatory"] += 1

        rows = []
        for role, mat in sorted(role_matrix.items()):
            scores = role_scores.get(role, [])
            avg_coverage = round(sum(scores) / len(scores), 1) if scores else 0.0
            rows.append({
                "Role": role,
                "Total Requirements": mat["total"],
                "Mandatory Requirements": mat["mandatory"],
                "Coverage Score (%)": avg_coverage,
                "Status": "Verified" if avg_coverage >= 95 else ("Partially Verified" if avg_coverage >= 70 else "Source Support Missing"),
            })

        chart = self._bar_chart(
            x=[r["Role"] for r in rows],
            y=[r["Coverage Score (%)"] for r in rows],
            name="Coverage %",
            color="#1E3A5F",
            title="Mandatory Coverage by Role",
        )
        return {"title": "Role Coverage Report", "columns": list(rows[0].keys()) if rows else [], "rows": rows, "chart_json": chart}

    def _report_hallucination(self) -> dict[str, Any]:
        """Hallucination / unsupported content flags report."""
        all_reports = self._reports.list_all()
        rows = []
        flagged_statuses = {
            "Source Support Missing",
            "Unsupported Requirement",
            "Manual Review Required",
        }
        for report in all_reports:
            payload = report.payload or {}
            for item in payload.get("per_item_results", []):
                status = item.get("verification_status", "")
                if status in flagged_statuses:
                    rows.append({
                        "Plan ID": report.plan_id,
                        "Item ID": item.get("item_id", ""),
                        "Item Type": item.get("item_type", ""),
                        "Status": status,
                        "Details": (item.get("details") or "")[:150],
                        "Source References": ", ".join(item.get("source_references", []))[:100],
                    })

        # Upload-time detection must be visible even when the adversarial
        # document was never selected by a role matrix and therefore cannot
        # appear in a particular plan's validation output.
        for document in self._documents.list_all():
            scan = (document.extra_metadata or {}).get("prompt_injection_scan") or {}
            if not scan.get("detected"):
                continue
            findings = scan.get("section_findings") or scan.get("findings") or []
            for finding in findings:
                section_id = finding.get("section_id") or "BODY"
                rows.append(
                    {
                        "Plan ID": "—",
                        "Item ID": document.document_id,
                        "Item Type": "uploaded_document",
                        "Status": "Prompt Injection Detected",
                        "Details": (
                            f"{finding.get('signature', 'suspicious instruction')}: "
                            f"{finding.get('snippet', '')}"
                        )[:150],
                        "Source References": f"{document.document_id}§{section_id}",
                    }
                )

        status_counts: dict[str, int] = {}
        for r in rows:
            st = r.get("Status") or "Flagged"
            status_counts[st] = status_counts.get(st, 0) + 1

        if status_counts:
            chart = self._donut_chart(
                list(status_counts.keys()),
                list(status_counts.values()),
                "Flagged Content by Status",
            )
        else:
            chart = self._donut_chart(
                ["Fully Verified"],
                [100],
                "Content Integrity (0 Hallucinations Detected)",
            )

        return {
            "title": "Hallucination & Unsupported Content Report",
            "columns": ["Plan ID", "Item ID", "Item Type", "Status", "Details", "Source References"],
            "rows": rows,
            "chart_json": chart,
        }

    def _report_traceability(self) -> dict[str, Any]:
        """Source traceability scores per plan report."""
        all_reports = self._reports.list_all()
        rows = []
        for report in all_reports:
            rows.append({
                "Plan ID": report.plan_id,
                "Coverage Score (%)": round(report.coverage_score or 0, 1),
                "Traceability Score (%)": round(report.traceability_score or 0, 1),
                "Consistency Score (%)": round(report.consistency_score or 0, 1),
                "Missing Count": report.missing_count,
                "Unsupported Count": report.unsupported_count,
                "Contradiction Count": report.contradiction_count,
                "Overall Status": report.overall_status or "—",
                "Generated At": report.created_at.strftime("%Y-%m-%d %H:%M") if report.created_at else "—",
            })
        chart = self._bar_chart(
            x=[f"Plan {r['Plan ID']}" for r in rows],
            y=[r["Traceability Score (%)"] for r in rows],
            name="Traceability %",
            color="#0284C7",
            title="Source Traceability Score by Plan",
        )
        return {"title": "Source Traceability Report", "columns": list(rows[0].keys()) if rows else [], "rows": rows, "chart_json": chart}

    def _report_comparison(self) -> dict[str, Any]:
        """Live GenAI/Python comparison built from persisted plans and matrix rows."""
        # The database is the source of truth.  Do not let a stale Markdown
        # artifact override real validation results in the evaluator UI.
        rows = self._generate_comparison_rows()

        match_counts: dict[str, int] = {}
        for r in rows:
            m = r.get("Match") or "Match"
            match_counts[m] = match_counts.get(m, 0) + 1

        chart = self._donut_chart(
            list(match_counts.keys()) or ["Match"],
            list(match_counts.values()) or [1],
            "GenAI vs Python Alignment",
        )

        return {
            "title": "GenAI/Python Comparison Report",
            "columns": ["Requirement ID", "Python Expected", "GenAI Result", "Match", "Source", "Status"],
            "rows": rows,
            "chart_json": chart,
        }

    def _report_audit(self) -> dict[str, Any]:
        """Recent audit trail entries report."""
        entries: list[AuditEntry] = (
            self._session.query(AuditEntry)
            .order_by(AuditEntry.timestamp.desc())
            .limit(200)
            .all()
        )
        rows = [
            {
                "Timestamp": e.timestamp.strftime("%Y-%m-%d %H:%M:%S") if e.timestamp else "—",
                "Actor": e.actor,
                "Action": e.action,
                "Entity Type": e.entity_type,
                "Entity ID": e.entity_id or "—",
                "Log Level": e.log_level,
            }
            for e in entries
        ]

        action_counts: dict[str, int] = {}
        for r in rows:
            act = r.get("Action") or "Other"
            action_counts[act] = action_counts.get(act, 0) + 1

        top_acts = sorted(action_counts.items(), key=lambda x: x[1], reverse=True)[:8]
        if top_acts:
            chart = self._bar_chart(
                x=[a[0] for a in top_acts],
                y=[a[1] for a in top_acts],
                name="Count",
                color="#0F766E",
                title="Recent Audit Events by Action",
            )
        else:
            chart = None

        return {
            "title": "Audit Trail Report",
            "columns": ["Timestamp", "Actor", "Action", "Entity Type", "Entity ID", "Log Level"],
            "rows": rows,
            "chart_json": chart,
        }

    # ------------------------------------------------------------------
    # Export methods
    # ------------------------------------------------------------------

    def export_csv(self, report_type: str) -> bytes:
        """Export report data to UTF-8 CSV bytes.

        Args:
            report_type: Report type key.

        Returns:
            CSV bytes ready to send as a file download.
        """
        data = self.get_report(report_type)
        rows = data["rows"]
        columns = data["columns"]

        buf = io.StringIO()
        writer = csv.DictWriter(buf, fieldnames=columns, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)
        return buf.getvalue().encode("utf-8")

    def export_pdf(self, report_type: str) -> bytes:
        """Export report data to PDF bytes using ReportLab.

        Args:
            report_type: Report type key.

        Returns:
            PDF bytes ready to send as a file download.
        """
        try:
            from reportlab.lib import colors
            from reportlab.lib.pagesizes import A4, landscape
            from reportlab.lib.styles import getSampleStyleSheet
            from reportlab.lib.units import mm
            from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle
        except ImportError:
            return self._fallback_pdf(report_type)

        data = self.get_report(report_type)
        rows = data["rows"]
        columns = data["columns"]

        buf = io.BytesIO()
        doc = SimpleDocTemplate(buf, pagesize=landscape(A4), topMargin=15*mm, bottomMargin=15*mm)
        styles = getSampleStyleSheet()
        elements = []

        title = Paragraph(f"<b>{data['title']}</b>", styles["Title"])
        elements.append(title)
        elements.append(Spacer(1, 6*mm))
        ts_text = f"Generated: {datetime.utcnow().strftime('%Y-%m-%d %H:%M UTC')} | Rows: {len(rows)}"
        elements.append(Paragraph(ts_text, styles["Normal"]))
        elements.append(Spacer(1, 4*mm))

        if rows:
            table_data = [columns]
            for row in rows[:200]:
                table_data.append([str(row.get(col, "")) for col in columns])

            col_width = (landscape(A4)[0] - 30*mm) / max(len(columns), 1)
            t = Table(table_data, colWidths=[col_width] * len(columns), repeatRows=1)
            t.setStyle(TableStyle([
                ("BACKGROUND",   (0, 0), (-1, 0), colors.HexColor("#7c3aed")),
                ("TEXTCOLOR",    (0, 0), (-1, 0), colors.white),
                ("FONTNAME",     (0, 0), (-1, 0), "Helvetica-Bold"),
                ("FONTSIZE",     (0, 0), (-1, -1), 7),
                ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.HexColor("#1c2230"), colors.HexColor("#212940")]),
                ("TEXTCOLOR",    (0, 1), (-1, -1), colors.HexColor("#f0f6fc")),
                ("GRID",         (0, 0), (-1, -1), 0.5, colors.HexColor("#30363d")),
                ("ALIGN",        (0, 0), (-1, -1), "LEFT"),
                ("VALIGN",       (0, 0), (-1, -1), "MIDDLE"),
                ("PADDING",      (0, 0), (-1, -1), 3),
            ]))
            elements.append(t)

        doc.build(elements)
        return buf.getvalue()

    def export_excel(self, report_type: str) -> bytes:
        """Export report data to Excel (.xlsx) bytes using openpyxl.

        Args:
            report_type: Report type key.

        Returns:
            Excel bytes ready to send as a file download.
        """
        try:
            import openpyxl
            from openpyxl.styles import Alignment, Font, PatternFill
        except ImportError:
            return self.export_csv(report_type)

        data = self.get_report(report_type)
        rows = data["rows"]
        columns = data["columns"]

        wb = openpyxl.Workbook()
        ws = wb.active
        ws.title = report_type.title()

        header_fill = PatternFill(fill_type="solid", fgColor="7C3AED")
        header_font = Font(bold=True, color="FFFFFF", size=10)
        alt_fill = PatternFill(fill_type="solid", fgColor="212940")
        norm_fill = PatternFill(fill_type="solid", fgColor="1C2230")
        norm_font = Font(color="F0F6FC", size=9)

        ws.append(columns)
        for cell in ws[1]:
            cell.fill = header_fill
            cell.font = header_font
            cell.alignment = Alignment(horizontal="center", vertical="center")

        for i, row in enumerate(rows, start=2):
            ws.append([str(row.get(col, "")) for col in columns])
            fill = alt_fill if i % 2 == 0 else norm_fill
            for cell in ws[i]:
                cell.fill = fill
                cell.font = norm_font

        for col_cells in ws.columns:
            max_len = max((len(str(c.value or "")) for c in col_cells), default=10)
            ws.column_dimensions[col_cells[0].column_letter].width = min(max_len + 2, 40)

        buf = io.BytesIO()
        wb.save(buf)
        return buf.getvalue()

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _bar_chart(self, x: list, y: list, name: str, color: str, title: str) -> str:
        """Produce a Plotly-compatible JSON string for a bar chart."""
        trace = {
            "x": x, "y": y, "type": "bar", "name": name,
            "marker": {"color": color, "opacity": 0.9, "line": {"color": "#1E3A5F", "width": 1}},
        }
        layout = {
            "title": {"text": title, "font": {"color": "#1E3A5F", "size": 13}},
            "font": {"family": "Inter, sans-serif", "color": "#0F172A"},
            "paper_bgcolor": "transparent",
            "plot_bgcolor": "transparent",
        }
        return json.dumps({"traces": [trace], "layout": layout})

    def _donut_chart(self, labels: list[str], values: list[int | float], title: str) -> str:
        """Produce a Plotly-compatible JSON string for a donut chart."""
        colors = ["#0F766E", "#1E3A5F", "#0284C7", "#D97706", "#EF4444", "#7C3AED", "#059669", "#64748B"]
        trace = {
            "labels": labels,
            "values": values,
            "type": "pie",
            "hole": 0.52,
            "textinfo": "label+percent",
            "textfont": {"family": "Inter, sans-serif", "size": 11, "color": "#1E3A5F"},
            "marker": {
                "colors": colors[:len(labels)],
                "line": {"color": "#FFFFFF", "width": 2}
            }
        }
        layout = {
            "title": {"text": title, "font": {"color": "#1E3A5F", "size": 13}},
            "font": {"family": "Inter, sans-serif", "color": "#0F172A"},
            "paper_bgcolor": "transparent",
            "plot_bgcolor": "transparent",
            "showlegend": True,
        }
        return json.dumps({"traces": [trace], "layout": layout})

    def _parse_d6_markdown(self, path: Path) -> list[dict]:
        """Parse the D6 comparison report markdown table into rows."""
        rows = []
        columns = ["Requirement ID", "Python Expected", "GenAI Result", "Match", "Source", "Status"]
        try:
            lines = path.read_text(encoding="utf-8").splitlines()
            in_table = False
            header_seen = False
            for line in lines:
                line = line.strip()
                if "|" not in line:
                    if in_table:
                        break
                    continue
                if not in_table and "Requirement ID" in line:
                    in_table = True
                    header_seen = True
                    continue
                if header_seen and line.startswith("|--"):
                    continue
                if in_table:
                    parts = [p.strip() for p in line.strip("|").split("|")]
                    if len(parts) >= 6:
                        rows.append(dict(zip(columns, parts[:6])))
            return rows[:200]
        except Exception:
            return []

    def _generate_comparison_rows(self) -> list[dict]:
        """Compare each role only with its newest complete plan.

        Comparing a single plan with every role's requirements creates false
        mismatches.  This method mirrors the D6 generator: choose the latest
        complete plan for each role and deduplicate shared All Roles rows.
        """
        entries = self._matrix.list_all()
        from comparison_engine import ComparisonEngine

        plans = (
            self._session.query(OnboardingPlan)
            .order_by(OnboardingPlan.id.desc())
            .all()
        )
        plan_by_role: dict[str, OnboardingPlan] = {}
        for plan in plans:
            payload = plan.structured_json or {}
            role = payload.get("role_title")
            if not role or payload.get("generation_status") == "failed_after_retries":
                continue
            if (plan.model_used or "").startswith("seed-"):
                continue
            plan_by_role.setdefault(role, plan)

        rows_by_requirement: dict[str, dict] = {}
        comparator = ComparisonEngine()
        roles = sorted({entry.role for entry in entries if entry.role != "All Roles"})
        for role in roles:
            plan = plan_by_role.get(role)
            if plan is None:
                continue
            role_entries = [entry for entry in entries if entry.role in {"All Roles", role}]
            for result in comparator.compare_requirements(role_entries, plan.structured_json or {}):
                rows_by_requirement[result["requirement_id"]] = {
                    "Requirement ID": result["requirement_id"],
                    "Python Expected": result["python_expected"],
                    "GenAI Result": result["genai_result"],
                    "Match": result["match_status"],
                    "Source": result["source"],
                    "Status": result["status"],
                }
        return [rows_by_requirement[key] for key in sorted(rows_by_requirement)]
    
    def _fallback_pdf(self, report_type: str) -> bytes:
        """Return a minimal text PDF when ReportLab is not installed."""
        data = self.get_report(report_type)
        content = f"SkillSprint AI — {data['title']}\n"
        content += f"Generated: {datetime.utcnow().isoformat()}\n\n"
        content += "\t".join(data["columns"]) + "\n"
        for row in data["rows"]:
            content += "\t".join(str(row.get(c, "")) for c in data["columns"]) + "\n"
        return content.encode("utf-8")
