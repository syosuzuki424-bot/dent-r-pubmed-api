from fastapi import FastAPI, Query
import httpx
from xml.etree import ElementTree as ET

app = FastAPI(
    title="Dent-R PubMed API",
    description="Minimal PubMed search API for debugging.",
    version="0.1.0"
)

NCBI_BASE = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils"


@app.get("/pubmed_search")
async def pubmed_search(
    term: str = Query(..., description="PubMed search term"),
    retmax: int = Query(3, description="Max number of articles")
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

    # esearch の結果を一応見やすくする（Count）
    count_text = esearch_root.findtext(".//Count") or "0"
    total_count = int(count_text)

    pmid_list = [n.text for n in esearch_root.findall(".//Id")]

    results = []

    # 2. 各PMIDごとにタイトルだけ取ってみる（まずはシンプルに）
    for pmid in pmid_list:
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

        root = ET.fromstring(efetch_res.text)
        title = root.findtext(".//ArticleTitle") or ""

        results.append({
            "pmid": pmid,
            "title": title
        })

    return {
        "query": term,
        "total_found_in_pubmed": total_count,
        "returned": len(results),
        "results": results
    }
