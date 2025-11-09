from fastapi import FastAPI, Query
import httpx
from xml.etree import ElementTree as ET

app = FastAPI(
    title="Dent-R PubMed API",
    description="PubMed search API for Dent-R. Returns real PubMed articles only.",
    version="1.1.0"
)

NCBI_BASE = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils"


def extract_article_info(xml_text: str):
    """
    PubMed efetchのXMLから、タイトル・著者・ジャーナル・年・アブストラクトを抜き出す。
    """
    root = ET.fromstring(xml_text)

    # タイトル
    title = root.findtext(".//ArticleTitle")

    # アブストラクト（抄録）
    abstract_parts = [t.text for t in root.findall(".//AbstractText") if t.text]
    abstract_full = " ".join(abstract_parts)

    # 著者
    authors_list = []
    for author in root.findall(".//Author"):
        last = author.findtext("LastName")
        fore = author.findtext("ForeName")
        if last and fore:
            authors_list.append(f"{fore} {last}")
    authors = ", ".join(authors_list)

    # 雑誌名
    journal = root.findtext(".//Journal/Title")

    # 出版年
    year = root.findtext(".//PubDate/Year")
    if year is None:
        year = root.findtext(".//ArticleDate/Year")

    return {
        "title": title or "",
        "authors": authors or "",
        "journal": journal or "",
        "year": year or "",
        "abstract": abstract_full or ""
    }


async def pmid_to_pmcid(pmid: str):
    """
    PMID から PMCID を取得する。
    取得できない場合は None を返す（＝オープンアクセス全文なし）。
    公式: https://www.ncbi.nlm.nih.gov/pmc/tools/id-converter-api/
    """
    url = "https://www.ncbi.nlm.nih.gov/pmc/utils/idconv/v1.0/"
    params = {
        "ids": pmid,
        "format": "json"
    }
    async with httpx.AsyncClient() as client:
        r = await client.get(url, params=params, timeout=20.0)

    if r.status_code != 200:
        return None

    data = r.json()
    records = data.get("records", [])
    if not records:
        return None

    rec = records[0]
    pmcid = rec.get("pmcid")  # 例: "PMC1234567"
    return pmcid


@app.get("/pubmed_search")
async def pubmed_search(
    term: str = Query(..., description="PubMed search term"),
    retmax: int = Query(10, description="Max number of articles")
):
    """
    term   : PubMedで検索したい語句（例: 'zirconia AND bonding strength'）
    retmax : 何件ほしいか
    """

    # 1. PMID一覧を取得（esearch）
    async with httpx.AsyncClient() as client:
        esearch_res = await client.get(
            f"{NCBI_BASE}/esearch.fcgi",
            params={
                "db": "pubmed",
                "term": term,
                "retmax": retmax,
                "retmode": "xml"
            },
            timeout=20.0
        )

    esearch_root = ET.fromstring(esearch_res.text)
    pmid_list = [n.text for n in esearch_root.findall(".//Id")]

    results = []

    # 2. 各PMIDごとに詳細情報を取得しつつ、オープンアクセスかどうかも判定
    for pmid in pmid_list:
        # PubMedからメタ情報取得（タイトル・アブストラクト等）
        async with httpx.AsyncClient() as client:
            efetch_res = await client.get(
                f"{NCBI_BASE}/efetch.fcgi",
                params={
                    "db": "pubmed",
                    "id": pmid,
                    "retmode": "xml"
                },
                timeout=20.0
            )

        article_info = extract_article_info(efetch_res.text)

        # PMID -> PMCID 変換（オープンアクセス判定用）
        pmcid = await pmid_to_pmcid(pmid)

        if pmcid:
            open_access = True
            # PMCのPDF URL（多くのOA論文がこのパターンでPDF公開されている）
            pdf_url = f"https://www.ncbi.nlm.nih.gov/pmc/articles/{pmcid}/pdf/"
        else:
            open_access = False
            pdf_url = None

        results.append({
            "pmid": pmid,
            "title": article_info["title"],
            "authors": article_info["authors"],
            "journal": article_info["journal"],
            "year": article_info["year"],
            "abstract": article_info["abstract"],
            "open_access": open_access,
            "pmcid": pmcid or None,
            "pdf_url": pdf_url
        })

    return {
        "query": term,
        "count": len(results),
        "results": results
    }
