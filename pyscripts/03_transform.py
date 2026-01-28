#!/usr/bin/env python
# 06
import argparse
import glob
import os
from pathlib import Path
import subprocess
import sys
import requests
from saxonche import PySaxonProcessor
from concurrent.futures import ThreadPoolExecutor

# from add_missing_initial_page import ensure_placeholder

# Constants
XSLT_URL = "https://csae8092.github.io/page2tei/page2tei-0.xsl"
LOCAL_XSLT = "page2tei-0.xsl"
METS_DIR = Path("./data/mets")
TEI_DIR = Path("./data/editions")
DEFAULT_COL_ID = "258178"


def _prepare_xslt_files() -> str:
    """Ensure page2tei and included stylesheets exist locally and use local includes."""
    if not os.path.exists(LOCAL_XSLT):
        response = requests.get(XSLT_URL, timeout=60)
        response.raise_for_status()
        with open(LOCAL_XSLT, "wb") as f:
            f.write(response.content)

    with open(LOCAL_XSLT, "r", encoding="utf-8") as f:
        xslt_content = f.read()

    xslt_content = xslt_content.replace('href="tokenize.xsl"', 'href="./tokenize.xsl"')
    xslt_content = xslt_content.replace(
        'href="combine-continued.xsl"', 'href="./combine-continued.xsl"'
    )
    xslt_content = xslt_content.replace(
        'href="string-pack.xsl"', 'href="./string-pack.xsl"'
    )

    with open(LOCAL_XSLT, "w", encoding="utf-8") as f:
        f.write(xslt_content)

    def download_xslt(url: str, local_path: str) -> None:
        if os.path.exists(local_path):
            return
        response = requests.get(url, timeout=60)
        response.raise_for_status()
        with open(local_path, "wb") as f:
            f.write(response.content)

    download_xslt("https://csae8092.github.io/page2tei/tokenize.xsl", "tokenize.xsl")
    download_xslt(
        "https://csae8092.github.io/page2tei/combine-continued.xsl",
        "combine-continued.xsl",
    )
    download_xslt("https://csae8092.github.io/page2tei/string-pack.xsl", "string-pack.xsl")
    return LOCAL_XSLT


def _list_mets_files(col_id: str | None, doc_ids: set[str] | None) -> list[str]:
    if col_id:
        candidates = glob.glob(f"{METS_DIR}/{col_id}/*_mets.xml")
    else:
        candidates = glob.glob(str(METS_DIR / "**" / "*_mets.xml"), recursive=True)

    if not doc_ids:
        return sorted(candidates)

    filtered: list[str] = []
    for file_path in candidates:
        tail = os.path.split(file_path)[-1]
        doc_id = tail.split("_")[0]
        if doc_id in doc_ids:
            filtered.append(file_path)
    return sorted(filtered)


def _postprocess_tei_file(tei_path: str) -> None:
    try:
        with open(tei_path, "r", encoding="utf-8") as f:
            output = f.read()
        fixed = output.replace(' type=""', "")
        if fixed != output:
            with open(tei_path, "w", encoding="utf-8") as f:
                f.write(fixed)
    except OSError:
        pass


def _transform_with_saxonche(files: list[str], stylesheet_file: str) -> None:
    os.makedirs(TEI_DIR, exist_ok=True)

    def transform_file(file: str) -> None:
        try:
            tail = os.path.split(file)[-1]
            doc_id = tail.split("_")[0]
            tei_file = f"{doc_id}.xml"
            tei_path = os.path.join(TEI_DIR, tei_file)
            print(f"Transforming METS: {file} to {tei_path}")

            document = proc.parse_xml(xml_file_name=file)
            output = executable.transform_to_string(xdm_node=document)

            with open(tei_path, "w", encoding="utf-8") as f:
                f.write(output)
            _postprocess_tei_file(tei_path)
        except Exception as e:
            print(f"Error processing {file}: {e}")

    with PySaxonProcessor(license=False) as proc:
        xsltproc = proc.new_xslt30_processor()
        xsltproc.set_parameter("combine", proc.make_boolean_value(True))
        xsltproc.set_parameter("ab", proc.make_boolean_value(True))
        executable = xsltproc.compile_stylesheet(stylesheet_file=stylesheet_file)

        with ThreadPoolExecutor(max_workers=1) as executor:
            executor.map(transform_file, files)


def _transform_with_java(
    files: list[str],
    stylesheet_file: str,
    classpath: str,
    java_opts: list[str],
) -> None:
    if not classpath:
        raise SystemExit("Missing classpath. Set SAXON_CP/SAXON_JAR or pass --classpath.")

    missing: list[str] = []
    for entry in classpath.split(os.pathsep):
        if entry and not os.path.exists(entry):
            missing.append(entry)
    if missing:
        raise SystemExit(
            "Missing classpath entries: "
            + ", ".join(missing)
            + ". Set SAXON_CP/SAXON_JAR or pass --classpath."
        )

    os.makedirs(TEI_DIR, exist_ok=True)

    for file in files:
        tail = os.path.split(file)[-1]
        doc_id = tail.split("_")[0]
        tei_file = f"{doc_id}.xml"
        tei_path = os.path.join(TEI_DIR, tei_file)
        print(f"Transforming METS: {file} to {tei_path}")

        cmd = (
            ["java"]
            + java_opts
            + [
                "-cp",
                classpath,
                "net.sf.saxon.Transform",
                f"-s:{file}",
                f"-xsl:{stylesheet_file}",
                f"-o:{tei_path}",
                "combine=true",
                "ab=true",
            ]
        )

        try:
            subprocess.run(cmd, check=True, text=True)
            _postprocess_tei_file(tei_path)
        except subprocess.CalledProcessError as e:
            print(f"Error processing {file}: Java Saxon failed with exit code {e.returncode}")


def main() -> int:
    parser = argparse.ArgumentParser(description="Transform METS XML to TEI XML")
    parser.add_argument(
        "--engine",
        choices=["saxonche", "java"],
        default=os.environ.get("OKAR_XSLT_ENGINE", "saxonche"),
        help="XSLT engine to use (default: OKAR_XSLT_ENGINE or saxonche)",
    )
    parser.add_argument(
        "--col-id",
        default=os.environ.get("COL_ID", DEFAULT_COL_ID),
        help="Transkribus collection ID under data/mets (default: COL_ID or 258178)",
    )
    parser.add_argument(
        "--all-collections",
        action="store_true",
        help="Process METS files under all subfolders of data/mets",
    )
    parser.add_argument(
        "--doc-id",
        action="append",
        default=[],
        help="Only transform this doc id (repeatable)",
    )
    parser.add_argument(
        "--classpath",
        "--saxon-jar",
        dest="classpath",
        default=os.environ.get("SAXON_CP", os.environ.get("SAXON_JAR", "")),
        help=(
            "Java classpath for Saxon-HE (for --engine java). "
            "You typically need Saxon-HE plus xmlresolver, separated with ':' on Linux. "
            "Example: .tools/Saxon-HE-12.4.jar:.tools/xmlresolver-5.2.1.jar"
        ),
    )
    parser.add_argument(
        "--java-opts",
        default=os.environ.get("SAXON_JAVA_OPTS", ""),
        help='Additional Java options, e.g. "-Xss32m" (for --engine java)',
    )

    args = parser.parse_args()

    stylesheet_file = _prepare_xslt_files()
    col_id = None if args.all_collections else args.col_id
    doc_ids = set(args.doc_id) if args.doc_id else None
    files = _list_mets_files(col_id=col_id, doc_ids=doc_ids)

    if not files:
        print("No METS files found; nothing to transform.")
        return 0

    if args.engine == "java":
        java_opts = args.java_opts.split() if args.java_opts else []
        _transform_with_java(
            files=files,
            stylesheet_file=stylesheet_file,
            classpath=args.classpath,
            java_opts=java_opts,
        )
        return 0

    _transform_with_saxonche(files=files, stylesheet_file=stylesheet_file)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
