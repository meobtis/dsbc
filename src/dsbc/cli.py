import asyncio
import json
import logging
import re
import unicodedata
from typing import Optional
import click
import yaml
from rich.console import Console
from rich.logging import RichHandler
from rich.panel import Panel
from rich.progress import Progress, SpinnerColumn, TextColumn, BarColumn, TaskProgressColumn, TimeElapsedColumn
from rich.table import Table

from .client import DSBCClient
from .config import (
    DEFAULT_CONCURRENCY,
    MANIFEST_PATH,
    RAW_BOOKS_DIR,
    RAW_CONTENT_DIR,
    TEXTS_DIR,
    TRANSLITERATE_PATH,
)
from .converter import DSBCConverter
from .translit import capitalise, devanagari_to_iast, tool_version
from .indexer import DSBCIndexer
from .scraper import DSBCScraper

console = Console()


def setup_logging(verbose: bool = False):
    level = logging.DEBUG if verbose else logging.INFO
    logging.basicConfig(
        level=level,
        format="%(message)s",
        datefmt="[%X]",
        handlers=[RichHandler(console=console, rich_tracebacks=True, show_path=False)],
    )


@click.group()
@click.option("-v", "--verbose", is_flag=True, help="Enable verbose debug logging.")
def main(verbose: bool):
    """Deterministic DSBC scraper and Markdown converter."""
    setup_logging(verbose)


@main.command()
@click.option(
    "--script",
    type=click.Choice(["all", "romanized", "devanagari"]),
    default="all",
    help="Which script catalog to index.",
)
@click.option("--limit", type=int, default=None, help="Limit number of books to index.")
@click.option(
    "--concurrency",
    type=int,
    default=DEFAULT_CONCURRENCY,
    help="Number of concurrent requests.",
)
@click.option("-f", "--force", is_flag=True, help="Re-fetch even if cached locally.")
def index(script: str, limit: Optional[int], concurrency: int, force: bool):
    """Index DSBC catalog and build data/manifest.json."""
    console.print(
        Panel.fit(
            f"[bold cyan]Indexing DSBC Catalog[/bold cyan]\n"
            f"Script: [yellow]{script}[/yellow] | Concurrency: [yellow]{concurrency}[/yellow]"
            + (f" | Limit: [yellow]{limit}[/yellow]" if limit else ""),
            title="DSBC Indexer",
        )
    )

    async def run():
        async with DSBCClient(concurrency=concurrency) as client:
            indexer = DSBCIndexer(client)
            with Progress(
                SpinnerColumn(),
                TextColumn("[progress.description]{task.description}"),
                BarColumn(),
                TaskProgressColumn(),
                TimeElapsedColumn(),
                console=console,
            ) as progress:
                books = await indexer.build_manifest(
                    script_filter=script, limit=limit, force=force, progress=progress
                )
            console.print(
                f"[bold green]✓[/bold green] Indexed {len(books)} books. Saved to [cyan]{MANIFEST_PATH}[/cyan]"
            )

    asyncio.run(run())


@main.command()
@click.option(
    "--script",
    type=click.Choice(["all", "romanized", "devanagari"]),
    default="all",
    help="Which script to scrape.",
)
@click.option("--book-id", type=int, default=None, help="Scrape a specific book by ID.")
@click.option("--limit", type=int, default=None, help="Limit number of content pages to scrape.")
@click.option(
    "--concurrency",
    type=int,
    default=DEFAULT_CONCURRENCY,
    help="Number of concurrent requests.",
)
@click.option("-f", "--force", is_flag=True, help="Re-fetch even if cached locally.")
def scrape(
    script: str,
    book_id: Optional[int],
    limit: Optional[int],
    concurrency: int,
    force: bool,
):
    """Scrape raw HTML for texts listed in manifest.json."""
    console.print(
        Panel.fit(
            f"[bold green]Scraping DSBC Content[/bold green]\n"
            f"Script: [yellow]{script}[/yellow] | Concurrency: [yellow]{concurrency}[/yellow]"
            + (f" | Book ID: [yellow]{book_id}[/yellow]" if book_id else "")
            + (f" | Limit: [yellow]{limit}[/yellow]" if limit else ""),
            title="DSBC Scraper",
        )
    )

    async def run():
        async with DSBCClient(concurrency=concurrency) as client:
            scraper = DSBCScraper(client)
            with Progress(
                SpinnerColumn(),
                TextColumn("[progress.description]{task.description}"),
                BarColumn(),
                TaskProgressColumn(),
                TimeElapsedColumn(),
                console=console,
            ) as progress:
                stats = await scraper.scrape_all(
                    script_filter=script,
                    book_id_filter=book_id,
                    limit=limit,
                    force=force,
                    progress=progress,
                )
            console.print(
                f"[bold green]✓[/bold green] Scraped {stats['success']}/{stats['total']} content pages."
                + (f" ([red]{stats['failed']} failed[/red])" if stats["failed"] else "")
            )

    asyncio.run(run())


@main.command()
@click.option(
    "--script",
    type=click.Choice(["all", "romanized", "devanagari"]),
    default="all",
    help="Which script to convert.",
)
@click.option("--book-id", type=int, default=None, help="Convert a specific book by ID.")
@click.option(
    "--split-chapters",
    is_flag=True,
    help="Also output individual chapter Markdown files in a book directory.",
)
def convert(script: str, book_id: Optional[int], split_chapters: bool):
    """Convert cached raw HTML texts into formatted Markdown."""
    console.print(
        Panel.fit(
            f"[bold yellow]Converting DSBC Texts to Markdown[/bold yellow]\n"
            f"Script: [yellow]{script}[/yellow] | Split Chapters: [yellow]{split_chapters}[/yellow]"
            + (f" | Book ID: [yellow]{book_id}[/yellow]" if book_id else ""),
            title="DSBC Converter",
        )
    )

    converter = DSBCConverter()
    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        BarColumn(),
        TaskProgressColumn(),
        TimeElapsedColumn(),
        console=console,
    ) as progress:
        stats = converter.convert_all(
            script_filter=script,
            book_id_filter=book_id,
            split_chapters=split_chapters,
            progress=progress,
        )

    console.print(
        f"[bold green]✓[/bold green] Converted {stats['converted_books']}/{stats['total_books']} books to [cyan]{TEXTS_DIR}[/cyan]"
    )
    console.print(f"[bold green]✓[/bold green] Generated catalog index at [cyan]{TEXTS_DIR / 'CATALOG.md'}[/cyan]")


@main.command(name="all")
@click.option(
    "--script",
    type=click.Choice(["all", "romanized", "devanagari"]),
    default="all",
    help="Which script to process.",
)
@click.option("--limit", type=int, default=None, help="Limit number of books to process.")
@click.option(
    "--concurrency",
    type=int,
    default=DEFAULT_CONCURRENCY,
    help="Number of concurrent requests.",
)
@click.option(
    "--split-chapters",
    is_flag=True,
    help="Also output individual chapter Markdown files.",
)
@click.pass_context
def process_all(
    ctx,
    script: str,
    limit: Optional[int],
    concurrency: int,
    split_chapters: bool,
):
    """Run full pipeline: index -> scrape -> convert."""
    console.print(
        Panel.fit(
            f"[bold magenta]Running Full DSBC Pipeline (Index -> Scrape -> Convert)[/bold magenta]\n"
            f"Script: [yellow]{script}[/yellow] | Concurrency: [yellow]{concurrency}[/yellow]"
            + (f" | Limit: [yellow]{limit}[/yellow]" if limit else ""),
            title="DSBC Full Pipeline",
        )
    )
    ctx.invoke(index, script=script, limit=limit, concurrency=concurrency, force=False)
    ctx.invoke(scrape, script=script, book_id=None, limit=None, concurrency=concurrency, force=False)
    ctx.invoke(convert, script=script, book_id=None, split_chapters=split_chapters)
    console.print("[bold green]✓ Pipeline completed successfully![/bold green]")


def _read_md(path):
    """Split a Markdown file into (front matter dict, body)."""
    _, head, body = path.read_text(encoding="utf-8").split("---\n", 2)
    return yaml.safe_load(head), body


def _safe_name(name: str) -> str:
    name = unicodedata.normalize("NFC", name)
    name = re.sub(r'[/\\:*?"<>|]+', "_", name)
    return re.sub(r"\s+", " ", name).strip(". ")[:120] or "untitled"


@main.command()
@click.option("--book-id", "book_ids", type=int, multiple=True, help="Transliterate only this book (repeatable).")
def transliterate(book_ids):
    """Write IAST versions of the Devanāgarī books listed in data/transliterate.json (Aksharamukha).

    These are Devanāgarī books for which DSBC has no romanised version. The file goes to
    texts/romanized/<category>/ and says in its front matter that it is a transliteration.
    """
    wanted = set(book_ids) or set(json.loads(TRANSLITERATE_PATH.read_text(encoding="utf-8"))["book_ids"])
    dev_dir = TEXTS_DIR / "devanagari"
    files = {}
    for path in dev_dir.rglob("*.md"):
        head = path.read_text(encoding="utf-8")[:3000]
        if re.search(r"^chapter:", head, re.M):  # one file per chapter, not a whole book
            continue
        m = re.search(r"^book_id: (\d+)$", head, re.M)
        if m and int(m.group(1)) in wanted:
            files[int(m.group(1))] = path
    missing = wanted - set(files)
    if missing:
        raise click.ClickException(f"No converted Devanāgarī book for id(s) {sorted(missing)}; run 'dsbc convert' first.")

    version = tool_version()
    rows = []
    for book_id in sorted(files):
        path = files[book_id]
        fm, body = _read_md(path)
        category = devanagari_to_iast(fm.get("category", ""))
        title = capitalise(devanagari_to_iast(fm["title"]))
        target = TEXTS_DIR / "romanized" / category / f"{_safe_name(title)}.md"
        if target.exists() and "transliterated_from" not in _read_md(target)[0]:
            raise click.ClickException(f"{target} exists and is not a transliteration; refusing to overwrite it")

        new = {}
        for key, value in fm.items():
            if key == "title":
                new[key] = title
            elif key == "script":
                new[key] = "romanized"
            elif key == "category":
                new[key] = category
            elif key == "category_path":
                new[key] = "Romanized»" + devanagari_to_iast(value.split("»", 1)[1]) if "»" in value else value
            elif key == "book_id":
                new[key] = f"{value}-iast"
                new["transliterated_from"] = str(path.relative_to(TEXTS_DIR.parent).as_posix())
                new["transliterated_from_book_id"] = value
                new["transliteration"] = {
                    "tool": version,
                    "from": "Devanagari",
                    "to": "IAST",
                    "note": "Machine transliteration of the Devanāgarī edition, which is the authoritative text. "
                    "Dandas are written | and ||.",
                }
            elif key == "technical_details" and isinstance(value, dict):
                details = dict(value)
                details["Text Version"] = "Romanized (IAST), transliterated from the Devanāgarī text"
                new[key] = details
            else:
                new[key] = value
        new_body = devanagari_to_iast(body)
        head = yaml.dump(new, allow_unicode=True, default_flow_style=False, sort_keys=False, width=100).strip()
        # The "# Title" line of the body is the Devanāgarī title: use the IAST one.
        new_body = re.sub(r"^\n# .*\n", f"\n# {title}\n", new_body, count=1)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(f"---\n{head}\n---\n{new_body}", encoding="utf-8")
        rows.append((book_id, title, target.relative_to(TEXTS_DIR)))
        console.print(f"  IAST   {book_id:>4}  {title[:44]:44} {target.stat().st_size // 1024:5} KB")

    lines = [
        "# Transliterated editions\n",
        f"IAST versions of Devanāgarī books that DSBC has no romanised version of, made with {version}. "
        "The Devanāgarī text is the authoritative edition.\n",
        "| Book | Title | IAST version | Devanāgarī book |",
        "|---|---|---|---|",
    ]
    for book_id, title, rel in rows:
        lines.append(f"| {book_id} | {title} | [{rel.stem}]({rel.as_posix().replace(' ', '%20')}) | "
                     f"[dsbcproject.org](https://www.dsbcproject.org/canon-text/book/{book_id}) |")
    (TEXTS_DIR / "TRANSLITERATED.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    console.print(f"[bold green]✓[/bold green] Transliterated {len(rows)} books; see {TEXTS_DIR / 'TRANSLITERATED.md'}")


@main.command()
def info():
    """Display statistics and status of downloaded / converted texts."""
    table = Table(title="DSBC Repository Status")
    table.add_column("Item", style="cyan")
    table.add_column("Count / Status", style="green")

    # Manifest
    if MANIFEST_PATH.exists():
        manifest = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
        total_books = len(manifest)
        rom_books = sum(1 for b in manifest if b.get("script") == "romanized")
        dev_books = sum(1 for b in manifest if b.get("script") == "devanagari")
        total_chapters = sum(len(b.get("chapters", [])) for b in manifest)
        table.add_row("Manifest", f"✓ Exists ({total_books} books: {rom_books} Roman, {dev_books} Dev)")
        table.add_row("Total Chapters in Canon", str(total_chapters))
    else:
        table.add_row("Manifest", "✗ Not found (run 'dsbc index')")

    # Raw cache
    books_cached = len(list(RAW_BOOKS_DIR.glob("*.html"))) if RAW_BOOKS_DIR.exists() else 0
    content_cached = len(list(RAW_CONTENT_DIR.glob("*.html"))) if RAW_CONTENT_DIR.exists() else 0
    table.add_row("Cached Book Pages", str(books_cached))
    table.add_row("Cached Content Pages", str(content_cached))

    # Converted markdown
    md_files = len(list(TEXTS_DIR.glob("**/*.md"))) if TEXTS_DIR.exists() else 0
    table.add_row("Generated Markdown Files", str(md_files))

    console.print(table)


if __name__ == "__main__":
    main()
