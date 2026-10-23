"""Regression checks against actual frozen provider/source counterexamples."""
import unittest
from evaluate import ROOT,read,provider_text,compact,norm,embedded_documents,urlkey,from_md
from evaluate_documents import table_cell_rows,row_check,plain_pdf_rows

class AdapterEvidenceTests(unittest.TestCase):
    def test_continuation_header_people_are_not_lost(self):
        doc=read(ROOT/'results/docling/d01-document.json')
        reference=read(ROOT/'document-reference.json')['rows']
        scored=row_check(reference,table_cell_rows(doc))
        self.assertEqual((scored['names'],scored['titles'],scored['complete_emails']),(61,61,60))
        self.assertTrue(next(x for x in scored['checks'] if x['name']=='周雪梅')['found'])
        self.assertTrue(next(x for x in scored['checks'] if x['name']=='倪钰飞')['found'])
        self.assertTrue(next(x for x in scored['checks'] if x['name']=='严海鸥')['incomplete_email_preserved'])

    def test_jina_link_pairs_and_split_bold_names(self):
        sample=next(x for x in read(ROOT/'reference-checks.json') if x['id']=='p18')
        data=provider_text('jina',sample)
        self.assertTrue(norm('张宏') in norm(data['text']))
        self.assertTrue(norm('金凤') in norm(data['text']))
        keys={urlkey(x['url']) for x in data['links']}
        self.assertTrue(all(urlkey(x['url']) in keys for x in sample['expected']['rows']))

    def test_embed_pdf_discovery_without_anchor_link(self):
        record=read(ROOT/'results/firecrawl/p24.json')
        data=record['response']['structuredContent']
        expected=read(ROOT/'documents.json')[0]['url']
        self.assertIn(expected,embedded_documents(data['rawHtml'],record['request']['url']))

    def test_scan_control_preserves_fields(self):
        doc=read(ROOT/'results/docling/d05-document.json')
        reference=read(ROOT/'document-reference.json')['rows'][:24]
        scored=row_check(reference,table_cell_rows(doc))
        self.assertEqual((scored['names'],scored['titles'],scored['complete_emails']),(24,24,23))

    def test_plain_pdf_page_join_does_not_lose_first_row(self):
        raw=read(ROOT/'results/jina/d01.json')['response']['data']['content']
        text,_=from_md(raw,'')
        reference=read(ROOT/'document-reference.json')['rows']
        scored=row_check(reference,plain_pdf_rows(text))
        self.assertEqual((scored['names'],scored['titles'],scored['complete_emails']),(61,61,60))

    def test_full_markdown_keeps_card_emails(self):
        samples=read(ROOT/'samples.json')
        for sid in ['p06','p07','p25']:
            sample=next(x for x in samples if x['id']==sid)
            data=provider_text('jina_full',sample)
            self.assertIsNotNone(data)
            self.assertIn(compact(sample['expected']['email']),compact(data['text']))

    def test_jina_html_field_keeps_embedded_document_url(self):
        sample=next(x for x in read(ROOT/'samples.json') if x['id']=='p24')
        data=provider_text('jina_html',sample)
        self.assertIn(read(ROOT/'documents.json')[0]['url'],data['embedded_document_urls'])

if __name__=='__main__':unittest.main()
