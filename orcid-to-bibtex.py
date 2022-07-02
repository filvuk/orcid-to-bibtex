from collections import defaultdict

from argparse import Namespace, ArgumentParser
from typing import Any
from asyncio import Semaphore, run, gather
from aiohttp import ClientSession, TCPConnector
from pathlib import Path
import bibtexparser as bp
import yake


async def get_orcid(orcid_path: str, session: ClientSession, dl_limit: Semaphore) -> Any:
    async with dl_limit:
        async with session.get(
                f"https://pub.orcid.org/{orcid_path}",
                headers={'Accept': 'application/orcid+json'}
        ) as response:
            return await response.json()


async def download_all(urls: list, session: ClientSession, dl_limit: Semaphore) -> Any:
    return await gather(*[get_orcid(url, session, dl_limit) for url in urls])


async def get_orcid_works(orcid_id: str) -> Any:
    dl_limit = Semaphore(50)
    async with ClientSession(connector=TCPConnector(ssl=False)) as session:
        works = await get_orcid(f"{orcid_id}/works", session, dl_limit)
        urls = []
        for work in works['group']:
            urls.append(work["work-summary"][0]["path"])
        results = await download_all(urls, session, dl_limit)
        bib = []
        for work in results:
            if work['citation']['citation-type'] == 'bibtex':
                bib.append(work['citation']['citation-value'])

        return bib


def parse_and_format_bib(input_bib: Path, out_bib: Path, indent: int = 4, order_by: str | tuple = 'year') -> None:
    db = bp.loads(input_bib.read_text())
    bib_id_count = defaultdict(int)

    for e in db.entries:
        title = ''.join([l for l in e['title'] if l.isalpha() or l.isspace()])
        keywords = yake.KeywordExtractor().extract_keywords(title)
        id = e['ID']

        unique = False
        c = 0

        while not unique:
            if c < len(keywords):
                id += '_' + keywords[c][0].replace(' ', '_').title()
                if id not in bib_id_count:
                    bib_id_count[id] += 1
                    unique = True
            else:
                bib_id_count[id] += 1
                id += id + '_' + str(bib_id_count)

        e['ID'] = id
        print(e['ID'])

    writer = bp.bwriter.BibTexWriter()
    writer.indent = ' ' * indent  # indent entries with
    writer.order_entries_by = order_by
    out_bib.write_text(writer.write(db))


def parse_cli_args() -> Namespace:
    p = ArgumentParser(description='Generates a BibTeX file for a given ORCID id.')
    p.add_argument('ORCID', type=str, metavar='0000-0000-0000-0000',
                   help="The ORCID ID for the individual whose works should be recorded.")
    p.add_argument('-o', type=Path, metavar='PATH',
                   help="The destination for the output BibTeX file.")
    return p.parse_args()


async def main():
    args = parse_cli_args()
    orcid = args.ORCID  # Test with: '0000-0002-1543-0148'
    bib_path = args.o or Path(f'{orcid}.bib')
    bib = await get_orcid_works(orcid)
    bib_path.write_text('\n'.join(bib))
    parse_and_format_bib(bib_path, bib_path)


run(main())
