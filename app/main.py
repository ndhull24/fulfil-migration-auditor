import typer
from rich.console import Console
from app.config import settings
from app.io.loaders import load_table
from app.rules.common import require_columns, unique_key
from app.rules.products import audit_products
from app.reconcile.cross_checks import orders_reference_existing_skus
from app.semantic.index import build_index
from app.semantic.search import search_kb
from app.rules.orders import audit_orders
from app.rules.orders import audit_orders
from app.reconcile.sku_map import load_sku_map
from app.reports.exporter import export_findings
from app.reports.scoring import readiness_by_entity, readiness_score


app = typer.Typer()
console = Console()

@app.command()
def build_kb_index():
    build_index("app/semantic/knowledge_base.md", settings.embedding_model)
    console.print("[green]KB index built.[/green]")

@app.command()
def ask(query: str):
    hits = search_kb(query, settings.embedding_model)
    for h in hits:
        console.rule("Answer")
        console.print(h)

@app.command()
def audit(products: str = "", orders: str = "", customers: str = "", sku_map: str = ""):
    tables = {}
    sku_map_dict = {}
    if sku_map:
        sku_map_dict = load_sku_map(sku_map)
    if products:
        tables["products"] = load_table(products)
    if orders in tables:
        findings += audit_orders(tables["orders"], tables)
        findings += orders_reference_existing_skus(tables, sku_map=sku_map_dict)
    if customers:
        tables["customers"] = load_table(customers)

    findings = []

    # Minimal “future-proof” baseline columns (customize per customer)
    if "products" in tables:
        df = tables["products"]
        findings += require_columns("products", df, ["sku", "name"])
        findings += unique_key("products", df, "sku")
        findings += audit_products(df, tables)

    # Cross checks
    findings += orders_reference_existing_skus(tables)

    # Print
    err = [x for x in findings if x.severity == "ERROR"]
    warn = [x for x in findings if x.severity == "WARN"]
    sug = [x for x in findings if x.severity == "SUGGEST"]

    console.rule("Migration Audit Summary")
    console.print(f"[red]Errors:[/red] {len(err)}  [yellow]Warnings:[/yellow] {len(warn)}  [blue]Suggestions:[/blue] {len(sug)}")

    for x in findings[:50]:
        console.print(f"{x.severity} {x.entity} {x.code} row={x.row} field={x.field} value={x.value}")
        if x.fix:
            console.print(f"  ↳ fix: {x.fix}")


    s_overall = readiness_score(findings)["overall"]
    s_entity = readiness_by_entity(findings)
    console.print(f"[bold]Readiness score:[/bold] {s_overall:.1f}/100")
    for k, v in s_entity.items():
        console.print(f" - {k}: {v:.1f}/100")

    out_csv = export_findings(findings, out_dir="reports")
    console.print(f"[green]Exported findings to[/green] {out_csv}")


if __name__ == "__main__":
    app()
