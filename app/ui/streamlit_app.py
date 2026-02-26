from __future__ import annotations
import io
import pandas as pd
import streamlit as st
import matplotlib.pyplot as plt

from app.config import settings
from app.io.yaml_loader import load_demo_yaml

from app.rules.common import require_columns, unique_key
from app.rules.products import audit_products
from app.rules.orders import audit_orders
from app.reconcile.cross_checks import orders_reference_existing_skus
from app.reports.scoring import readiness_score, readiness_by_entity
from app.reports.exporter import export_findings
from app.semantic.search import search_kb
import numpy as np

st.set_page_config(page_title="Fulfil Migration Auditor Demo", layout="wide")
st.title("Migration Auditor Demo — Upload 1 YAML, Find Issues, Fix, Visualize, Export")

# -------------------------
# Helpers
# -------------------------
FINDINGS_COLS = ["severity","entity","code","row","field","value","message","fix"]

def findings_to_df(findings):
    rows = [{
        "severity": getattr(f, "severity", ""),
        "entity": getattr(f, "entity", ""),
        "code": getattr(f, "code", ""),
        "row": getattr(f, "row", None),
        "field": getattr(f, "field", ""),
        "value": getattr(f, "value", ""),
        "message": getattr(f, "message", ""),
        "fix": getattr(f, "fix", ""),
    } for f in (findings or [])]

    df = pd.DataFrame(rows)
    # Ensure stable schema even when empty
    for c in FINDINGS_COLS:
        if c not in df.columns:
            df[c] = []
    df = df[FINDINGS_COLS].copy()

    # Normalize severity to string (prevents NaN weirdness)
    df["severity"] = df["severity"].astype(str).replace({"nan": ""}).fillna("")
    df["code"] = df["code"].astype(str).replace({"nan": ""}).fillna("")
    return df

def safe_value_counts(series: pd.Series) -> pd.Series:
    if series is None:
        return pd.Series(dtype=int)
    s = series.astype(str).replace({"nan": ""}).fillna("").str.strip()
    s = s[s != ""]
    if s.empty:
        return pd.Series(dtype=int)
    return s.value_counts()

def safe_bar_from_counts(title: str, xlabel: str, ylabel: str, counts: pd.Series):
    if counts is None or len(counts) == 0:
        st.info(f"No data available for: **{title}**")
        return None

    fig = plt.figure()
    ax = fig.add_subplot(111)
    ax.bar(counts.index.astype(str), counts.values.astype(int))
    ax.set_title(title)
    ax.set_xlabel(xlabel)
    ax.set_ylabel(ylabel)
    plt.xticks(rotation=30, ha="right")
    st.pyplot(fig)
    return fig


def fig_to_png_bytes(fig) -> bytes:
    buf = io.BytesIO()
    fig.savefig(buf, format="png", bbox_inches="tight", dpi=160)
    buf.seek(0)
    return buf.read()

def simple_insight_text(findings_df: pd.DataFrame, dfp: pd.DataFrame, dfo: pd.DataFrame) -> str:
    if findings_df is None or findings_df.empty or "severity" not in findings_df.columns:
        # still give useful context even if there are no findings
        return (
            f"- Total products: {len(dfp):,}\n"
            f"- Total orders: {len(dfo):,}\n"
            "- No findings generated yet (run audit / check YAML structure).\n"
        )

    # A small rules-based analysis (no API required)
    e = findings_df[findings_df["severity"] == "ERROR"]
    w = findings_df[findings_df["severity"] == "WARN"]

    lines = []
    lines.append(f"- Total products: {len(dfp):,}")
    lines.append(f"- Total orders: {len(dfo):,}")
    lines.append(f"- Errors (go-live blockers): {len(e):,}")
    lines.append(f"- Warnings (risk): {len(w):,}")

    top_codes = findings_df["code"].value_counts().head(5)
    if len(top_codes):
        lines.append("\nTop issues by code:")
        for code, cnt in top_codes.items():
            lines.append(f"  - {code}: {cnt}")

    # Data health signals
    if "sku" in dfp.columns:
        blank_sku = (dfp["sku"].astype(str).str.strip() == "").sum()
        if blank_sku:
            lines.append(f"\nProducts with blank SKU: {blank_sku} (must be 0)")

    if "name" in dfp.columns:
        blank_name = (dfp["name"].astype(str).str.strip() == "").sum()
        if blank_name:
            lines.append(f"Products with blank name: {blank_name} (recommend 0)")

    if "order_date" in dfo.columns:
        bad_dates = pd.to_datetime(dfo["order_date"], errors="coerce").isna().sum()
        if bad_dates:
            lines.append(f"Orders with invalid date: {bad_dates} (should be 0)")

    lines.append("\nWhat to fix first (typical implementation priority):")
    lines.append("1) Duplicate/invalid product keys (SKU uniqueness, blank SKU)")
    lines.append("2) Orders referencing unknown SKUs")
    lines.append("3) Missing required product fields (name, UOM)")
    lines.append("4) Integration stability risks (whitespace SKUs, inconsistent status enums)")
    return "\n".join(lines)


# -------------------------
# Sidebar — ONLY YAML upload
# -------------------------
st.sidebar.header("Upload")
yaml_file = st.sidebar.file_uploader("Upload demo YAML (products + orders)", type=["yaml", "yml"])

apply_sku_map = st.sidebar.checkbox("Apply SKU mapping from YAML (recommended)", value=True)

if not yaml_file:
    st.info("Upload a YAML file to begin. Example: data/demo_10000.yaml")
    st.stop()

# Load YAML into tables
tables, sku_map_dict = load_demo_yaml(yaml_file)
dfp = tables["products"]
dfo = tables["orders"]

if not apply_sku_map:
    sku_map_dict = {}

# -------------------------
# Tabs
# -------------------------
tab1, tab2, tab3 = st.tabs(["How to use (Business Users)", "Audit + Fix", "Insights + Charts"])

# -------------------------
# TAB 1 — Instructions
# -------------------------
with tab1:
    st.subheader("How to use this tool (for business users)")
    st.markdown("""
**Goal:** Catch migration issues before go-live, reduce cutover risk, and create a fix checklist.

### Step-by-step
1) Upload one YAML file that contains **Products** and **Orders**.
2) Go to **Audit + Fix** and click **Run Audit**.
3) Focus first on **Errors** (go-live blockers).
4) Apply fixes in your source file (or mapping rules) and re-run.
5) Download the findings CSV and share it as an implementation checklist.
6) Go to **Insights + Charts** to visualize what’s happening and track progress.

### What counts as an “Error” vs “Warning”?
- **Errors:** must be fixed to go live (duplicate SKU, missing SKU referenced by orders, invalid dates, etc.)
- **Warnings:** risk items (whitespace SKUs, blank UOM, barcode duplicates)
""")

# -------------------------
# TAB 2 — Audit engine + semantic explain + export
# -------------------------
with tab2:
    st.subheader("Audit + Fix")
    if st.button("Run Audit"):
        findings = []

        # Minimum required columns
        findings += require_columns("products", dfp, ["sku", "name"])
        findings += unique_key("products", dfp, "sku")
        findings += audit_products(dfp, tables)

        findings += require_columns("orders", dfo, ["order_id", "order_date", "channel", "customer_id", "sku", "quantity", "warehouse", "status"])
        findings += audit_orders(dfo, tables)

        findings += orders_reference_existing_skus(tables, sku_map=sku_map_dict)

        fdf = findings_to_df(findings)

        # Scorecards
        overall = readiness_score(findings)["overall"]
        by_ent = readiness_by_entity(findings)
        if fdf.empty:
            errs = fdf
            warns = fdf
            sugs = fdf
        else:
            errs = fdf[fdf["severity"] == "ERROR"]
            warns = fdf[fdf["severity"] == "WARN"]
            sugs  = fdf[fdf["severity"] == "SUGGEST"]


        c1, c2, c3, c4 = st.columns(4)
        c1.metric("Readiness Score", f"{overall:.1f}/100")
        c2.metric("Errors (blockers)", len(errs))
        c3.metric("Warnings (risk)", len(warns))
        c4.metric("Suggestions", len(sugs))

        st.write("Module Scores:", {k: f"{v:.1f}/100" for k, v in by_ent.items()})

        # Filter + display
        sev = st.multiselect("Filter severity", ["ERROR", "WARN", "SUGGEST"], default=["ERROR", "WARN", "SUGGEST"])
        view = fdf[fdf["severity"].isin(sev)].copy()

        st.dataframe(view, use_container_width=True)

        # Explain using semantic search
        st.markdown("### Explain an issue (plain English)")
        if not view.empty:
            pick = st.selectbox("Pick a row to explain", view.index.tolist())
            if st.button("Explain selected"):
                issue = view.loc[pick]
                q = f"What does {issue['code']} mean and how do I fix it? Context: {issue['message']}"
                hits = search_kb(q, settings.embedding_model)
                for h in hits:
                    st.markdown(h)
                    st.divider()

        # Export findings CSV
        csv_bytes = view.to_csv(index=False).encode("utf-8")
        st.download_button("Download findings.csv", data=csv_bytes, file_name="findings.csv", mime="text/csv")

        # Export full report (markdown)
        report_text = "# Migration Auditor Report\n\n"
        report_text += f"Readiness Score: {overall:.1f}/100\n\n"
        report_text += "## Summary\n"
        report_text += f"- Errors: {len(errs)}\n- Warnings: {len(warns)}\n- Suggestions: {len(sugs)}\n\n"
        report_text += "## Top Issues\n"
        top = fdf["code"].value_counts().head(10)
        for code, cnt in top.items():
            report_text += f"- {code}: {cnt}\n"
        report_text += "\n## Findings (CSV exported separately)\n"

        st.download_button("Download report.md", data=report_text.encode("utf-8"), file_name="report.md", mime="text/markdown")

# -------------------------
# TAB 3 — Charts + auto insights + chart builder
# -------------------------
with tab3:
    st.subheader("Insights + Charts")

    # Re-run audit (lightweight) for charts if needed
    findings = []
    findings += require_columns("products", dfp, ["sku", "name"])
    findings += unique_key("products", dfp, "sku")
    findings += audit_products(dfp, tables)
    findings += require_columns("orders", dfo, ["order_id", "order_date", "channel", "customer_id", "sku", "quantity", "warehouse", "status"])
    findings += audit_orders(dfo, tables)
    findings += orders_reference_existing_skus(tables, sku_map=sku_map_dict)
    fdf = findings_to_df(findings)

    st.markdown("## Auto analysis (no API needed)")
    st.text(simple_insight_text(fdf, dfp, dfo))

    st.markdown("## Most important graphs (migration-focused)")

    # Graph 1: Issue count by severity (SAFE)
    sev_counts = safe_value_counts(fdf["severity"]) if "severity" in fdf.columns else pd.Series(dtype=int)
    fig1 = safe_bar_from_counts(
        title="Issues by Severity",
        xlabel="Severity",
        ylabel="Count",
        counts=sev_counts
    )
    if fig1 is not None:
        st.caption("Explanation: Errors block go-live. Warnings are risk items. Suggestions improve quality.")
        st.download_button(
            "Download graph (severity).png",
            data=fig_to_png_bytes(fig1),
            file_name="issues_by_severity.png",
            mime="image/png"
        )

    # Graph 2: Top issue codes
    code_counts = safe_value_counts(fdf["code"]) if "code" in fdf.columns else pd.Series(dtype=int)
    code_counts = code_counts.head(10)

    fig2 = safe_bar_from_counts(
        title="Top 10 Issue Codes",
        xlabel="Issue code",
        ylabel="Count",
        counts=code_counts
    )
    if fig2 is not None:
        st.caption("Explanation: Shows where most cleanup effort is required.")
        st.download_button(
            "Download graph (codes).png",
            data=fig_to_png_bytes(fig2),
            file_name="top_issue_codes.png",
            mime="image/png"
        )


    # Graph 3: Orders by channel
    if "channel" in dfo.columns and not dfo.empty:
        ch_counts = safe_value_counts(dfo["channel"])
        fig3 = safe_bar_from_counts(
            title="Orders by Channel",
            xlabel="Channel",
            ylabel="Orders",
            counts=ch_counts
        )
        if fig3 is not None:
            st.caption("Explanation: Useful for validating volume by channel before cutover.")
            st.download_button(
                "Download graph (channel).png",
                data=fig_to_png_bytes(fig3),
                file_name="orders_by_channel.png",
                mime="image/png"
            )
    else:
        st.info("Orders-by-channel chart unavailable (missing column or empty orders).")


    # Graph 4: Orders over time (date parsing)
    if "order_date" in dfo.columns and not dfo.empty:
        dd = pd.to_datetime(dfo["order_date"], errors="coerce")
        dd = dd.dropna()
        if dd.empty:
            st.info("Orders-over-time chart unavailable (all dates invalid).")
        else:
            ts = dd.dt.to_period("M").value_counts().sort_index()
            fig4 = plt.figure()
            ax4 = fig4.add_subplot(111)
            ax4.plot(ts.index.astype(str), ts.values.astype(int))
            ax4.set_title("Orders over Time (Monthly)")
            ax4.set_xlabel("Month")
            ax4.set_ylabel("Orders")
            plt.xticks(rotation=30, ha="right")
            st.pyplot(fig4)
            st.caption("Explanation: Confirms seasonality and data completeness in the migration set.")
            st.download_button(
                "Download graph (timeline).png",
                data=fig_to_png_bytes(fig4),
                file_name="orders_over_time.png",
                mime="image/png"
            )
    else:
        st.info("Orders-over-time chart unavailable (missing order_date or empty orders).")


    st.markdown("## Chart Builder (user-defined)")
    st.write("Pick a dataset and create a chart without coding.")

    dataset = st.selectbox("Dataset", ["orders", "products", "findings"])
    df_map = {"orders": dfo, "products": dfp, "findings": fdf}
    df = df_map[dataset].copy()

    chart_type = st.selectbox("Chart type", ["Bar (counts)", "Histogram", "Scatter", "Line (time)", "Box"])
    cols = list(df.columns)

    if chart_type == "Bar (counts)":
        x = st.selectbox("Column to count", cols)
        topn = st.slider("Top N", 5, 30, 10)
        fig = plt.figure()
        ax = fig.add_subplot(111)
        df[x].astype(str).value_counts().head(topn).plot(kind="bar", ax=ax)
        ax.set_title(f"Top {topn} values of {x}")
        ax.set_xlabel(x)
        ax.set_ylabel("Count")
        st.pyplot(fig)
        st.download_button("Download this chart.png", data=fig_to_png_bytes(fig), file_name="custom_bar.png", mime="image/png")

    elif chart_type == "Histogram":
        x = st.selectbox("Numeric column", cols)
        fig = plt.figure()
        ax = fig.add_subplot(111)
        pd.to_numeric(df[x], errors="coerce").dropna().plot(kind="hist", ax=ax, bins=30)
        ax.set_title(f"Histogram of {x}")
        ax.set_xlabel(x)
        ax.set_ylabel("Frequency")
        st.pyplot(fig)
        st.download_button("Download this chart.png", data=fig_to_png_bytes(fig), file_name="custom_hist.png", mime="image/png")

    elif chart_type == "Scatter":
        x = st.selectbox("X (numeric)", cols)
        y = st.selectbox("Y (numeric)", cols, index=min(1, len(cols)-1))
        fig = plt.figure()
        ax = fig.add_subplot(111)
        xx = pd.to_numeric(df[x], errors="coerce")
        yy = pd.to_numeric(df[y], errors="coerce")
        ax.scatter(xx, yy)
        ax.set_title(f"Scatter: {x} vs {y}")
        ax.set_xlabel(x)
        ax.set_ylabel(y)
        st.pyplot(fig)
        st.download_button("Download this chart.png", data=fig_to_png_bytes(fig), file_name="custom_scatter.png", mime="image/png")

    elif chart_type == "Line (time)":
        x = st.selectbox("Time column", cols)
        y = st.selectbox("Value column (count if blank)", ["(count)"] + cols)
        fig = plt.figure()
        ax = fig.add_subplot(111)
        t = pd.to_datetime(df[x], errors="coerce")
        tmp = df.copy()
        tmp["_t"] = t
        tmp = tmp.dropna(subset=["_t"]).sort_values("_t")
        if y == "(count)":
            s = tmp["_t"].dt.to_period("M").value_counts().sort_index()
            s.plot(kind="line", ax=ax)
            ax.set_ylabel("Count")
        else:
            tmp["_y"] = pd.to_numeric(tmp[y], errors="coerce")
            agg = tmp.dropna(subset=["_y"]).groupby(tmp["_t"].dt.to_period("M"))["_y"].mean()
            agg.plot(kind="line", ax=ax)
            ax.set_ylabel(f"Mean {y}")
        ax.set_title(f"Line chart by month: {x}")
        ax.set_xlabel("Month")
        st.pyplot(fig)
        st.download_button("Download this chart.png", data=fig_to_png_bytes(fig), file_name="custom_line.png", mime="image/png")

    elif chart_type == "Box":
        x = st.selectbox("Numeric column", cols)
        fig = plt.figure()
        ax = fig.add_subplot(111)
        vals = pd.to_numeric(df[x], errors="coerce").dropna()
        ax.boxplot(vals, vert=True)
        ax.set_title(f"Box plot of {x}")
        ax.set_ylabel(x)
        st.pyplot(fig)
        st.download_button("Download this chart.png", data=fig_to_png_bytes(fig), file_name="custom_box.png", mime="image/png")
