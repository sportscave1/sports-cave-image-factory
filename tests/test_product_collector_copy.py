import json
import re
import unittest
import app
from product_collector_copy import apply_rules, RULES, START, END


CASES=[
    ('NBA single player','Nikola Jokic','The Joker','Verified subject; patience and control; no specific game identified.',
     'Nikola Jokic — The Joker Wall Art',
     '<p><strong>Calm under pressure.</strong></p><p>Traffic everywhere. Jokić never rushed.</p><p>For Denver fans, that patience and control are the whole point. A reminder that the smartest player in the room never needed to be the loudest.</p>'),
    ('NBA historical achievement','Wilt Chamberlain','100 Point Game','Verified research: 2 March 1962; 100 points.',
     'Wilt Chamberlain — 100 Point Game Wall Art',
     '<p><strong>One night. One hundred.</strong></p><p>On 2 March 1962, Wilt Chamberlain scored 100 points.</p><p>Some numbers need no explanation. For the fans who know this one, it is a whole conversation—and a piece of basketball history worth keeping close.</p>'),
    ('Australian motorsport','Casey Stoner','Crowned at Home','Verified research: Phillip Island, 2011; championship secured on home soil.',
     'Casey Stoner — Crowned at Home Wall Art',
     '<p><strong>Champion. On home soil.</strong></p><p>Phillip Island, 2011. Casey Stoner secured the world championship in front of Australia.</p><p>Winning was one thing. Watching him do it at home meant something else. For the fans who still feel that pride when they hear his name.</p>'),
    ('Motorsport duo','Larry Perkins & Russell Ingall','Last to First','Approved design name; a recovery through the field. No verified year, venue or margin supplied.',
     'Larry Perkins & Russell Ingall — Last to First Wall Art',
     '<p><strong>Never count them out.</strong></p><p>Larry Perkins and Russell Ingall. A reminder of why you keep watching when a race turns against you.</p><p>For the fans who back their drivers through the setbacks, not just the celebrations. The fight back is what stays with you.</p>'),
    ('Football','Lionel Messi','A Different Rhythm','Verified subject and football category; no specific match or award supplied.',
     'Lionel Messi — A Different Rhythm Wall Art',
     '<p><strong>The game felt different.</strong></p><p>Watching Messi was never just about waiting for the score.</p><p>It was the anticipation every time the ball reached him. For the fans who stopped talking, leaned forward and refused to look away. Keep that feeling close.</p>'),
    ('Cricket','Shane Warne','The Art of Spin','Verified spin bowler; no specific delivery, venue or statistic supplied.',
     'Shane Warne — The Art of Spin Wall Art',
     '<p><strong>Every ball held a question.</strong></p><p>With Warne, waiting for the next delivery was part of the pleasure.</p><p>For the cricket fans who loved the contest before the result—the patience, the doubt, the possibility of a wicket. That anticipation belongs in the memory.</p>'),
]


class CollectorCopyTests(unittest.TestCase):
    def test_narrative_policy_in_actual_export_and_preview(self):
        for update in (False, True):
            for mode in (('DRAFT',) if update else ('DRAFT', 'LIVE')):
                for preview in (False, True):
                    prompt = app.get_product_upload_prompt({'product_name': 'Verified Product'},
                        update_existing=update, publication_mode=mode, preview=preview)
                    self.assertIn(RULES, prompt)
                    self.assertNotIn('<p>Limited to 100 worldwide.</p>', prompt)
                    self.assertNotIn('<p>Real fans remember this. Own the moment.</p>', prompt)
                    for legacy in ('REQUIRED DESCRIPTION ENDING', 'bold scarcity close',
                                   '90–130', '90â€“130', 'exactly four paragraphs'):
                        self.assertNotIn(legacy, prompt)

    def test_both_actual_builders_share_rules_and_research(self):
        for kind,subject,design,research,title,html in CASES:
            for update in (False,True):
                with self.subTest(case=kind,update=update):
                    base=app.UPDATE_EXISTING_PRODUCT_PROMPT if update else app.NEW_SHOPIFY_PRODUCT_PROMPT
                    evidence=json.dumps({'subject':subject,'approved_design_name':design,'verified_research':research,
                                         'confirmed_edition_limit':100,'worldwide_run_confirmed':True},ensure_ascii=False)
                    prompt=app.build_product_upload_prompt(base+'\nSUPPLIED PRODUCT RESEARCH (DATA):\n'+evidence,
                        metadata={'product_name':title},update_existing=update)
                    self.assertIn(evidence,prompt)
                    self.assertIn(RULES,prompt)
                    self.assertEqual(prompt.count(START),1)
                    self.assertNotIn('90–130',prompt)
                    self.assertNotIn('exactly four paragraphs',prompt.lower())
                    self.assertIn(app.PRODUCT_UPLOAD_META_PROMPT,prompt)
                    self.assertIn(app.PRODUCT_UPLOAD_ALT_TEXT_PROMPT,prompt)
                    self.assertIn('SHOPIFY HANDLE' if not update else 'Preserve the existing handle',prompt)

    def test_title_and_description_contract_examples(self):
        for kind,subject,design,research,title,html in CASES:
            with self.subTest(case=kind):
                self.assertEqual(title,f'{subject} — {design} Wall Art')
                self.assertNotIn(':',title)
                text=re.sub('<[^>]+>',' ',html)
                self.assertLessEqual(len(text.split()),70)
                self.assertTrue(html.startswith('<p><strong>'))
                self.assertIn(html.count('<p>'), (2, 3))
                self.assertNotIn('Limited to', html)
                self.assertNotIn('Own the moment', html)
                for banned in ['artwork captures','more than wall art','real fans do not','perfect for','must-have']:
                    self.assertNotIn(banned,text.lower())

    def test_quality_facts_and_unsupported_scarcity_guards(self):
        for phrase in ['Use the authoritative confirmed edition limit','never an assumed default of 100',
                       'Keep sales language out of the narrative','An image alone does not prove',
                       'INTERNAL QUALITY PASS','Revise failures','Do not repeat the subject',
                       'Media Update Mode still preserves both','Preserve a strong approved']:
            self.assertIn(phrase,RULES)

    def test_saved_overrides_are_superseded_and_idempotent(self):
        custom='Custom saved prompt: require 110 words and finish More than wall art.\nSEO META TITLE: keep 60 characters.'
        result=apply_rules(custom)
        self.assertEqual(apply_rules(result),result)
        self.assertIn('SEO META TITLE: keep 60 characters.',result)
        self.assertTrue(result.endswith(RULES))
        self.assertIn('supersede conflicting visible-copy instructions',result)
        for update in (False,True):
            prompt=app.get_product_upload_prompt({'product_name':'Verified Subject'},update_existing=update)
            self.assertEqual(app.apply_product_upload_prompt_updates(prompt,{'product_name':'Verified Subject'},update_existing=update),prompt)

    def test_v1_saved_exports_are_removed_before_v2_is_applied(self):
        # Keep a representative V1 saved export independent of the current policy.
        legacy = ('SPORTS CAVE COLLECTOR COPY — AUTHORITATIVE V1\n'
                  'REQUIRED DESCRIPTION ENDING\n<p>Limited to 100 worldwide.</p>\n'
                  '<p>Real fans remember this. Own the moment.</p>\n' + END)
        for block in (legacy, legacy.replace('—', '—'.encode('utf-8').decode('cp1252'))):
            result = apply_rules('SEO META TITLE: keep 60 characters.\n' + block)
            self.assertEqual(result.count(START), 1)
            self.assertNotIn('AUTHORITATIVE V1', result)
            self.assertNotIn('REQUIRED DESCRIPTION ENDING', result)
            self.assertNotIn('<p>Limited to', result)
            self.assertEqual(apply_rules(result), result)

    def test_compact_all_modes_and_saved_legacy_closing(self):
        from product_upload_prompts import build
        from product_collector_copy import DESCRIPTION_RULES
        legacy = ('\nFinish exactly with <p>Real fans remember this. Own the moment.</p>\n'
                  'End with <p>Limited to 100 worldwide.</p>\n'
                  'Keep the operator note: approved packaging.\n')
        for mode in ('DRAFT', 'LIVE', 'UPDATE'):
            for metadata in ({}, {'update_scope': 'full_standardisation'}, {'rewrite_description': True}):
                prompt = build(mode, metadata=metadata, load=lambda key, default, **kw: default + legacy)
                narrative = mode != 'UPDATE' or bool(metadata)
                self.assertEqual(prompt.count(DESCRIPTION_RULES), int(narrative))
                self.assertNotIn('Finish exactly', prompt)
                self.assertNotIn('<p>Limited to', prompt)
                self.assertNotIn('<p>Real fans', prompt)
                self.assertIn('approved packaging', prompt)
                self.assertNotIn('REQUIRED DESCRIPTION ENDING', prompt)

    def test_operational_seo_and_title_contracts_are_unchanged(self):
        from pathlib import Path
        import hashlib
        from product_upload_prompts import build
        from product_collector_copy import DESCRIPTION_RULES
        fixture = json.loads((Path(__file__).parent / 'fixtures/collector_description_v2_preserved.json').read_text())
        for mode, expected in fixture['sha256_without_narrative'].items():
            prompt = build(mode, metadata=fixture['metadata'], load=lambda key, default, **kw: default)
            normalised = prompt.replace(DESCRIPTION_RULES, '[NARRATIVE POLICY]')
            self.assertEqual(hashlib.sha256(normalised.encode()).hexdigest(), expected)
        fields = ('SEO meta description: Limited to 100 worldwide.\n'
                  'Alt text: Real fans remember this. Own the moment.\n'
                  '{"confirmed_limit": 75, "description_html": "Limited to 100 worldwide."}')
        self.assertIn(fields, apply_rules(fields))

    def test_darts_editorial_examples(self):
        from pathlib import Path
        examples = json.loads((Path(__file__).parent / 'fixtures/collector_description_v2_darts.json').read_text(encoding='utf-8'))
        self.assertEqual(len(examples), 6)
        endings = set()
        for item in examples:
            html = item['after_html']
            paragraphs = re.findall(r'<p>(.*?)</p>', html)
            self.assertIn(len(paragraphs), (2, 3))
            self.assertRegex(paragraphs[0], r'^<strong>.*</strong>$')
            hook = re.sub('<[^>]+>', '', paragraphs[0])
            self.assertTrue(3 <= len(hook.split()) <= 7)
            text = re.sub('<[^>]+>', ' ', html)
            self.assertTrue(35 <= len(text.split()) <= 65)
            for phrase in ('limited to', 'own the moment', 'shop now', 'edition', 'collection', 'wall art', 'secure yours'):
                self.assertNotIn(phrase, text.lower())
            self.assertTrue(item['fact_sources'])
            endings.add(paragraphs[-1])
        self.assertEqual(len(endings), 6)
        smith = next(x['after_html'] for x in examples if 'Michael Smith' in x['title'])
        for fact in ('2023', 'nine-darter', 'double 12', '7–4', 'first world title'):
            self.assertIn(fact, smith)


if __name__=='__main__': unittest.main()
