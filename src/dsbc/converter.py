import json
import logging
from pathlib import Path
from typing import Any, Dict, List, Optional
import yaml
from rich.progress import Progress

from .config import MANIFEST_PATH, RAW_CONTENT_DIR, TEXTS_DIR
from .parser import parse_content_page
from .utils import parse_category_path, sanitize_filename

logger = logging.getLogger("dsbc.converter")


class DSBCConverter:
    """Converts downloaded raw HTML content into beautifully formatted Markdown files."""

    def __init__(self, output_dir: Path = TEXTS_DIR):
        self.output_dir = output_dir

    def load_manifest(self) -> List[Dict[str, Any]]:
        if not MANIFEST_PATH.exists():
            raise FileNotFoundError(
                f"Manifest not found at {MANIFEST_PATH}. Run 'dsbc index' first."
            )
        return json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))

    def convert_book(
        self,
        book: Dict[str, Any],
        split_chapters: bool = False,
    ) -> Optional[Path]:
        """Convert a single book's content files into Markdown."""
        book_id = book.get("book_id")
        title = book.get("title", f"book_{book_id}")
        script = book.get("script", "romanized")
        category_path_raw = book.get("category_path", "")
        chapters_meta = book.get("chapters", [])

        if not chapters_meta:
            logger.info(f"Book {book_id} ('{title}') has no chapters. Skipping.")
            return None

        cat_parts = parse_category_path(category_path_raw)
        book_folder_rel = Path(script) / Path(*cat_parts)
        target_dir = self.output_dir / book_folder_rel
        target_dir.mkdir(parents=True, exist_ok=True)

        book_slug = sanitize_filename(title)
        parsed_chapters = []

        for ch in chapters_meta:
            c_id = ch.get("content_id")
            sn = ch.get("sn", "")
            ch_title = ch.get("title", "")
            raw_path = RAW_CONTENT_DIR / f"{book_id}_{c_id}.html"

            if not raw_path.exists():
                logger.warning(f"Missing raw HTML for book {book_id} content {c_id}")
                continue

            html = raw_path.read_text(encoding="utf-8")
            parsed = parse_content_page(html)

            parsed_chapters.append({
                "sn": sn,
                "title": parsed["title"] or ch_title,
                "content_id": c_id,
                "url": ch.get("url", ""),
                "technical_details": parsed.get("technical_details", {}),
                "text": parsed.get("text", ""),
            })

        if not parsed_chapters:
            return None

        # Build consolidated markdown file
        frontmatter = {
            "title": title,
            "script": script,
            "category": "/".join(cat_parts),
            "category_path": category_path_raw,
            "book_id": book_id,
            "source_url": book.get("book_url", ""),
            "chapters_count": len(parsed_chapters),
        }

        if book.get("bibliography"):
            frontmatter["bibliography"] = book["bibliography"]

        if len(parsed_chapters) == 1 and parsed_chapters[0].get("technical_details"):
            frontmatter["technical_details"] = parsed_chapters[0]["technical_details"]

        yaml_header = yaml.dump(
            frontmatter,
            allow_unicode=True,
            default_flow_style=False,
            sort_keys=False,
        ).strip()

        md_lines = [f"---\n{yaml_header}\n---\n", f"# {title}\n"]

        # If book has multiple chapters, format each with level 2 header
        is_multi_chapter = len(parsed_chapters) > 1

        for idx, ch in enumerate(parsed_chapters, start=1):
            ch_title = ch["title"]
            ch_text = ch["text"]

            if is_multi_chapter:
                header = f"## {ch_title}" if ch_title else f"## Chapter {idx}"
                md_lines.append(f"{header}\n")

            if ch_text:
                md_lines.append(f"{ch_text}\n")

            # If split_chapters requested, write individual chapter file
            if split_chapters and is_multi_chapter:
                ch_dir = target_dir / book_slug
                ch_dir.mkdir(parents=True, exist_ok=True)
                ch_slug = f"{idx:02d}_{sanitize_filename(ch_title or f'chapter_{idx}')}.md"
                ch_frontmatter = {
                    "title": title,
                    "chapter": ch_title,
                    "chapter_number": idx,
                    "script": script,
                    "book_id": book_id,
                    "content_id": ch["content_id"],
                    "source_url": ch["url"],
                }
                if ch.get("technical_details"):
                    ch_frontmatter["technical_details"] = ch["technical_details"]

                ch_yaml = yaml.dump(
                    ch_frontmatter,
                    allow_unicode=True,
                    default_flow_style=False,
                    sort_keys=False,
                ).strip()

                ch_content = f"---\n{ch_yaml}\n---\n\n# {ch_title}\n\n{ch_text}\n"
                (ch_dir / ch_slug).write_text(ch_content, encoding="utf-8")

        # Write consolidated book file
        book_file_path = target_dir / f"{book_slug}.md"
        book_file_path.write_text("\n".join(md_lines), encoding="utf-8")

        return book_file_path

    def convert_all(
        self,
        script_filter: str = "all",
        book_id_filter: Optional[int] = None,
        split_chapters: bool = False,
        progress: Optional[Progress] = None,
    ) -> Dict[str, Any]:
        """Convert all eligible cached books into Markdown and generate CATALOG.md."""
        books = self.load_manifest()

        if script_filter != "all":
            books = [b for b in books if b.get("script") == script_filter]

        if book_id_filter is not None:
            books = [b for b in books if b.get("book_id") == book_id_filter]

        task_id = None
        if progress:
            task_id = progress.add_task(
                f"[yellow]Converting {len(books)} books to Markdown...",
                total=len(books),
            )

        converted_paths = []
        for b in books:
            out_path = self.convert_book(b, split_chapters=split_chapters)
            if out_path:
                converted_paths.append(out_path)
            if progress and task_id is not None:
                progress.advance(task_id)

        self.generate_catalog()

        return {
            "total_books": len(books),
            "converted_books": len(converted_paths),
        }

    def generate_catalog(self):
        """Generate texts/CATALOG.md with links and metadata for all converted texts."""
        if not MANIFEST_PATH.exists():
            return

        manifest = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
        catalog_lines = [
            "# Digital Sanskrit Buddhist Canon - Texts Catalog\n",
            "This catalog lists all texts digitized by the Digital Sanskrit Buddhist Canon (DSBC) project.\n",
            f"**Total Books in Canon:** {len(manifest)}\n",
            "## Table of Contents\n",
            "- [Romanized Texts](#romanized-texts)",
            "- [Devanagari Texts](#devanagari-texts)",
            "\n---\n",
        ]

        for script in ["romanized", "devanagari"]:
            script_books = [b for b in manifest if b.get("script") == script]
            catalog_lines.append(f"## {script.title()} Texts\n")
            catalog_lines.append(f"Total: {len(script_books)} texts\n")
            catalog_lines.append("| ID | Title | Category | Chapters | Link |")
            catalog_lines.append("|---|---|---|---|---|")

            for b in script_books:
                b_id = b.get("book_id", "")
                title = b.get("title", "")
                cat_path_raw = b.get("category_path", "")
                chapters = b.get("chapters", [])
                cat_parts = parse_category_path(cat_path_raw)
                book_slug = sanitize_filename(title)
                rel_path = f"{script}/{'/'.join(cat_parts)}/{book_slug}.md"

                # Check if file exists
                file_exists = (self.output_dir / rel_path).exists()
                link = f"[{title}]({rel_path})" if file_exists else "*(not yet scraped)*"

                clean_cat = "/".join(cat_parts)
                catalog_lines.append(
                    f"| {b_id} | {title} | {clean_cat} | {len(chapters)} | {link} |"
                )

            catalog_lines.append("\n---\n")

        catalog_path = self.output_dir / "CATALOG.md"
        catalog_path.parent.mkdir(parents=True, exist_ok=True)
        catalog_path.write_text("\n".join(catalog_lines), encoding="utf-8")
