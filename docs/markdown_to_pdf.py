#!/usr/bin/env python3
"""Render one or more Markdown files to polished, print-friendly PDFs."""

from __future__ import annotations

import argparse
import os
from pathlib import Path
import re
import shutil
import subprocess
import tempfile


LATEX_TEMPLATE = r"""
\documentclass[10pt,a4paper]{article}
\usepackage[top=16mm,bottom=18mm,left=15mm,right=15mm]{geometry}
\usepackage{xcolor}
\usepackage{fontspec}
\setmainfont{DejaVu Sans}
\setsansfont{DejaVu Sans}
\setmonofont{DejaVu Sans Mono}[Scale=0.88]

\definecolor{Ink}{HTML}{172033}
\definecolor{Heading}{HTML}{102A43}
\definecolor{Accent}{HTML}{2563EB}
\definecolor{Rule}{HTML}{CBD5E1}
\definecolor{CodeInk}{HTML}{27364A}
\definecolor{LinkBlue}{HTML}{1D4ED8}

\usepackage{hyperref}
\hypersetup{
  colorlinks=true,
  linkcolor=LinkBlue,
  urlcolor=LinkBlue,
  citecolor=LinkBlue,
  pdfborder={0 0 0},
  pdftitle={__PDF_TITLE__}
}
\urlstyle{same}

\usepackage{titlesec}
\setcounter{secnumdepth}{-1}
\titleformat{\section}
  {\color{Heading}\Large\bfseries}{}
  {0pt}{}[\vspace{2pt}\color{Rule}\titlerule]
\titleformat{\subsection}
  {\color{Heading}\large\bfseries}{}{0pt}{}
\titleformat{\subsubsection}
  {\color{Heading}\normalsize\bfseries}{}{0pt}{}
\titleformat{\paragraph}[block]
  {\color{Heading}\normalsize\bfseries}{}{0pt}{}
\titlespacing*{\section}{0pt}{20pt}{7pt}
\titlespacing*{\subsection}{0pt}{14pt}{5pt}
\titlespacing*{\subsubsection}{0pt}{11pt}{4pt}
\titlespacing*{\paragraph}{0pt}{9pt}{3pt}

\usepackage{enumitem}
\setlist{leftmargin=18pt,itemsep=2pt,topsep=4pt,parsep=1pt}
\usepackage{booktabs}
\usepackage{tabularx}
\usepackage{array}
\usepackage{fvextra}
\usepackage{fancyhdr}
\pagestyle{fancy}
\fancyhf{}
\renewcommand{\headrulewidth}{0.4pt}
\renewcommand{\headrule}{\hbox to\headwidth{\color{Rule}\leaders\hrule height
  \headrulewidth\hfill}}
\fancyhead[L]{\footnotesize\color{Heading}__HEADER__}
\fancyhead[R]{\footnotesize\color{Heading}Markdown PDF}
\fancyfoot[C]{\footnotesize\color{Heading}\thepage}
\setlength{\headheight}{13pt}

\setlength{\parindent}{0pt}
\setlength{\parskip}{4pt}
\setlength{\emergencystretch}{3em}
\color{Ink}
\widowpenalty=10000
\clubpenalty=10000
\displaywidowpenalty=10000

\newcommand{\DocumentTitle}[1]{%
  \begingroup
  \color{Heading}\fontsize{23}{28}\selectfont\bfseries #1\par
  \vspace{6pt}
  {\color{Accent}\rule{\linewidth}{1.4pt}}\par
  \vspace{8pt}
  \endgroup
}
\newcommand{\CodeInput}[1]{%
  \par\vspace{3pt}
  \VerbatimInput[
    breaklines=true,
    breakanywhere=true,
    fontsize=\scriptsize,
    frame=single,
    rulecolor=\color{Rule},
    framesep=2.5mm,
    formatcom=\color{CodeInk}
  ]{#1}
  \vspace{2pt}
}
\newcommand{\CodeBlock}[2]{%
  \par\vspace{3pt}
  \if\relax\detokenize{#2}\relax\else
    {\scriptsize\sffamily\bfseries\color{Heading}#2\par\nobreak\vspace{1pt}}
  \fi
  \CodeInput{#1}
}

\usepackage[
  fencedCode,
  pipeTables,
  tightLists,
  blankBeforeHeading,
  blankBeforeBlockquote
]{markdown}

\makeatletter
\markdownSetup{
  rendererPrototypes={
    headingOne={\DocumentTitle{#1}},
    headingTwo={\section{#1}},
    headingThree={\subsection{#1}},
    headingFour={\subsubsection{#1}},
    headingFive={\paragraph{#1}},
    headingSix={\paragraph{#1}},
    link={\href{#3}{#1}},
    image={#1},
    inputVerbatim={\CodeInput{#1}},
    inputFencedCode={\CodeBlock{#1}{#2}},
    blockQuoteBegin={
      \begin{quote}\color{Heading}\itshape
    },
    blockQuoteEnd={
      \end{quote}
    },
    horizontalRule={
      \par\medskip{\color{Rule}\hrule}\medskip
    },
    table={%
      \markdownLaTeXTable={}%
      \markdownLaTeXTableAlignment={}%
      \markdownLaTeXTableEnd={%
        \bottomrule
        \end{tabular}%
        \endgroup}%
      \addto@hook\markdownLaTeXTable{%
        \begingroup
        \small
        \setlength{\tabcolsep}{4pt}%
        \renewcommand{\arraystretch}{1.25}%
        \begin{tabular}}%
      \markdownLaTeXRowCounter=0%
      \markdownLaTeXRowTotal=#2%
      \markdownLaTeXColumnTotal=#3%
      \def\MarkdownColumnWidth{%
        \dimexpr\linewidth/#3-2\tabcolsep\relax}%
      \markdownLaTeXRenderTableRow
    }
  }
}
\def\markdownLaTeXReadAlignments#1{%
  \advance\markdownLaTeXColumnCounter by 1\relax
  \addto@hook\markdownLaTeXTableAlignment{%
    >{\raggedright\arraybackslash}p{\MarkdownColumnWidth}}%
  \ifnum\markdownLaTeXColumnCounter<\markdownLaTeXColumnTotal\relax
  \else
    \expandafter\@gobble
  \fi
  \markdownLaTeXReadAlignments
}
\makeatother

\begin{document}
\markdownInput{source.md}
\end{document}
"""


def tex_escape(value: str) -> str:
    replacements = {
        "\\": r"\textbackslash{}",
        "{": r"\{",
        "}": r"\}",
        "$": r"\$",
        "&": r"\&",
        "#": r"\#",
        "_": r"\_",
        "%": r"\%",
        "~": r"\textasciitilde{}",
        "^": r"\textasciicircum{}",
    }
    return "".join(replacements.get(character, character) for character in value)


def document_title(markdown: str, fallback: str) -> str:
    match = re.search(r"^#\s+(.+?)\s*$", markdown, flags=re.MULTILINE)
    if not match:
        return fallback
    title = re.sub(r"[*_`]", "", match.group(1))
    return title.strip()


def preprocess(markdown: str) -> str:
    # Turn remote badge images into normal clickable text. This keeps builds
    # deterministic in offline environments.
    markdown = re.sub(
        r"\[!\[([^\]]*)\]\(https?://[^)]+\)\]\((https?://[^)]+)\)",
        lambda match: f"[{match.group(1)}]({match.group(2)})",
        markdown,
    )
    markdown = re.sub(
        r"!\[([^\]]*)\]\(https?://[^)]+\)",
        lambda match: match.group(1) or "Image",
        markdown,
    )
    # Make links between sibling Markdown files point to their PDF versions.
    markdown = re.sub(
        r"\]\(([^)#]+?)\.(?:md|markdown)\)",
        lambda match: f"]({match.group(1)}.pdf)",
        markdown,
        flags=re.IGNORECASE,
    )
    # Markdown heading IDs are renderer-specific. Keep the hand-written table
    # of contents readable without emitting broken in-document PDF links.
    markdown = re.sub(r"\[([^\]]+)\]\(#[^)]+\)", r"\1", markdown)
    return markdown


def run_xelatex(temp_dir: Path) -> None:
    command = [
        shutil.which("xelatex") or "xelatex",
        "--interaction=nonstopmode",
        "--halt-on-error",
        "--shell-escape",
        "document.tex",
    ]
    environment = os.environ.copy()
    environment["HOME"] = str(temp_dir)
    for _ in range(2):
        result = subprocess.run(
            command,
            cwd=temp_dir,
            check=False,
            capture_output=True,
            text=True,
            env=environment,
        )
        if result.returncode != 0:
            log_path = temp_dir / "document.log"
            log = log_path.read_text(encoding="utf-8", errors="replace") if log_path.exists() else ""
            excerpt = "\n".join(log.splitlines()[-80:])
            raise RuntimeError(f"XeLaTeX conversion failed:\n{excerpt}")


def render_pdf(source: Path, output_dir: Path, force: bool) -> Path:
    target = output_dir / f"{source.stem}.pdf"
    if target.exists() and not force:
        raise FileExistsError(f"{target} already exists; pass --force to replace it")

    original = source.read_text(encoding="utf-8")
    prepared = preprocess(original)
    title = document_title(original, source.stem)
    header = source.stem.replace("_", " ")

    with tempfile.TemporaryDirectory(prefix="markdown-pdf-") as temp_name:
        temp_dir = Path(temp_name)
        (temp_dir / "source.md").write_text(prepared, encoding="utf-8")
        template = LATEX_TEMPLATE.replace("__PDF_TITLE__", tex_escape(title))
        template = template.replace("__HEADER__", tex_escape(header))
        (temp_dir / "document.tex").write_text(template, encoding="utf-8")
        run_xelatex(temp_dir)

        generated = temp_dir / "document.pdf"
        if not generated.exists():
            raise RuntimeError("XeLaTeX finished without creating document.pdf")
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(generated, target)
    return target


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Convert Markdown files to A4 PDFs with Unicode support."
    )
    parser.add_argument("sources", nargs="+", type=Path)
    parser.add_argument("-o", "--output-dir", type=Path, default=Path.cwd())
    parser.add_argument("--force", action="store_true")
    args = parser.parse_args()

    for source in args.sources:
        if not source.is_file():
            parser.error(f"Markdown file not found: {source}")
        output = render_pdf(source.resolve(), args.output_dir.resolve(), args.force)
        print(output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
