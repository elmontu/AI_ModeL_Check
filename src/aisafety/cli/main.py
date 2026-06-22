"""CLI entry point for AI Safety Checker."""

from __future__ import annotations

import json
import sys
import time
from pathlib import Path

import typer
from rich.console import Console
from rich.table import Table

app = typer.Typer(
    name="aisafety",
    help="AI Safety Checker — practical, runnable AI model safety checks.",
    no_args_is_help=True,
)
console = Console()


@app.command("list")
def list_checkers() -> None:
    """List all available checkers and their dependency status."""
    from aisafety.core.registry import get_all_checkers

    _ensure_checkers_loaded()
    checkers = get_all_checkers()

    table = Table(title="Available Safety Checkers")
    table.add_column("Category", style="cyan")
    table.add_column("Name", style="white")
    table.add_column("Status", style="bold")
    table.add_column("Missing Deps", style="red")

    for category, cls in sorted(checkers.items()):
        instance = cls()
        available = instance.is_available()
        missing = instance.missing_dependencies()
        status = "[green]ready[/green]" if available else "[red]missing deps[/red]"
        missing_str = ", ".join(missing) if missing else ""
        table.add_row(category, cls.name, status, missing_str)

    console.print(table)


@app.command()
def init(output: str = typer.Option("aisafety.yaml", help="Output config file path")) -> None:
    """Generate a starter configuration file."""
    from aisafety.core.config import DEFAULT_CONFIG_TEMPLATE

    Path(output).write_text(DEFAULT_CONFIG_TEMPLATE)
    console.print(f"[green]Config written to {output}[/green]")


@app.command()
def run(
    category: str = typer.Argument(help="Checker category to run"),
    config: str | None = typer.Option(None, help="Config file path"),
    output: str | None = typer.Option(None, help="Output JSON file path"),
) -> None:
    """Run a specific checker category."""
    from aisafety.core.config import load_config
    from aisafety.core.registry import get_checker

    _ensure_checkers_loaded()

    try:
        checker_cls = get_checker(category)
    except KeyError as e:
        console.print(f"[red]{e}[/red]")
        raise typer.Exit(1)

    instance = checker_cls()
    if not instance.is_available():
        missing = instance.missing_dependencies()
        console.print(f"[red]Missing dependencies for {category}: {', '.join(missing)}[/red]")
        console.print(f"Install with: pip install ai-safety-checker[{category}]")
        raise typer.Exit(1)

    params = {}
    if config:
        cfg = load_config(config)
        checker_cfg = cfg.checkers.get(category)
        if checker_cfg:
            params = checker_cfg.params

    console.print(f"[cyan]Running {instance.name}...[/cyan]")
    start = time.perf_counter()
    try:
        result = instance.check(**params)
    except Exception as e:
        console.print(f"[red]Error running {category}: {e}[/red]")
        raise typer.Exit(1)
    result.duration_seconds = time.perf_counter() - start

    _print_result(result)

    if output:
        Path(output).write_text(result.model_dump_json(indent=2))
        console.print(f"[green]Results written to {output}[/green]")


@app.command()
def audit(
    config: str = typer.Argument(help="Config file path"),
    output: str | None = typer.Option(None, help="Output report file path"),
) -> None:
    """Run all enabled checks from a config file and produce a unified report."""
    from aisafety.core.config import load_config
    from aisafety.core.registry import get_all_checkers
    from aisafety.core.report import ReportBuilder

    _ensure_checkers_loaded()

    cfg = load_config(config)
    all_checkers = get_all_checkers()

    target_desc = cfg.target.get("description", "Unknown target")
    builder = ReportBuilder(target_description=target_desc)

    for category, checker_cfg in cfg.checkers.items():
        if not checker_cfg.enabled:
            console.print(f"  [dim]Skipping {category} (disabled)[/dim]")
            continue

        if category not in all_checkers:
            console.print(f"  [yellow]Unknown checker: {category}[/yellow]")
            continue

        checker_cls = all_checkers[category]
        instance = checker_cls()

        if not instance.is_available():
            missing = instance.missing_dependencies()
            console.print(f"  [yellow]{category}: missing deps ({', '.join(missing)})[/yellow]")
            continue

        console.print(f"  [cyan]Running {instance.name}...[/cyan]")
        start = time.perf_counter()
        try:
            result = instance.check(**checker_cfg.params)
            result.duration_seconds = time.perf_counter() - start
            builder.add_result(result)
            _print_result_brief(result)
        except Exception as e:
            console.print(f"  [red]{category} error: {e}[/red]")

    report = builder.build()
    console.print()
    _print_summary(report)

    out_path = output or cfg.output.get("path", "safety_report.json")
    Path(out_path).write_text(report.model_dump_json(indent=2))
    console.print(f"\n[green]Report saved to {out_path}[/green]")


def _ensure_checkers_loaded() -> None:
    """Import checkers package to trigger @register_checker decorators."""
    import aisafety.checkers  # noqa: F401


def _print_result(result) -> None:
    from aisafety.core.types import CheckStatus

    for f in result.findings:
        icon = {"pass": "[green]PASS[/green]", "fail": "[red]FAIL[/red]",
                "warn": "[yellow]WARN[/yellow]", "error": "[red]ERR [/red]",
                "skipped": "[dim]SKIP[/dim]"}.get(f.status.value, "???")
        console.print(f"  {icon} [{f.severity.value}] {f.title}")
        if f.description:
            console.print(f"       {f.description}")


def _print_result_brief(result) -> None:
    from aisafety.core.types import CheckStatus

    passed = sum(1 for f in result.findings if f.status == CheckStatus.PASS)
    failed = sum(1 for f in result.findings if f.status == CheckStatus.FAIL)
    warns = sum(1 for f in result.findings if f.status == CheckStatus.WARN)
    console.print(f"    {passed} passed, {failed} failed, {warns} warnings ({result.duration_seconds:.1f}s)")


def _print_summary(report) -> None:
    s = report.summary
    table = Table(title="Safety Audit Summary")
    table.add_column("Metric", style="cyan")
    table.add_column("Value", justify="right")
    table.add_row("Total checks", str(s.total_checks))
    table.add_row("Passed", f"[green]{s.passed}[/green]")
    table.add_row("Failed", f"[red]{s.failed}[/red]")
    table.add_row("Warnings", f"[yellow]{s.warnings}[/yellow]")
    table.add_row("Errors", str(s.errors))
    table.add_row("Critical findings", f"[red]{s.critical_findings}[/red]")

    status_color = {"pass": "green", "fail": "red", "warn": "yellow", "error": "red"}.get(
        s.overall_status.value, "white"
    )
    table.add_row("Overall", f"[{status_color}]{s.overall_status.value.upper()}[/{status_color}]")
    console.print(table)


if __name__ == "__main__":
    app()
