"""Offline generation-only sentence-bank contracts; no saved or live writes."""
import copy
import hashlib
import json
from pathlib import Path
import unittest
from PIL import ImageFont
import ads_page as ads
import ads_ie_usa as usa
import ads_ie_visual_systems as words


class SupportingLineTests(unittest.TestCase):
    def test_exact_usa_bank_and_draw_once(self):
        self.assertEqual(usa.SUPPORT_LINES, (
            'Once this edition sells out, there is no second run.',
            'Once it sells out, it’s done.',
            'Once they’re claimed, this edition retires forever.',
            'Once it sells out, it’s gone.',
            'When they’re gone, they’re gone.',
            'One release. Never repeated.',
        ))
        seen = set()
        for seed in range(30):
            rows = [{'resolved_seed':str(seed)} for _ in range(3)]
            usa.resolve_footer(rows, {}, lambda h:True, None)
            selected = [r['supporting_line'] for r in rows]
            self.assertEqual(len(set(selected)),3)
            self.assertTrue(set(selected) <= set(usa.SUPPORT_LINES))
            seen.update(selected)
            retry = [{'resolved_seed':'different'} for _ in range(3)]
            usa.resolve_footer(retry, {}, lambda h:True, None, rows)
            self.assertEqual(rows,[dict(r,resolved_seed=str(seed)) for r in retry])
        self.assertEqual(seen,set(usa.SUPPORT_LINES))

    def test_au_only_two_replacements(self):
        original = words.eligible_support_lines({})
        updated = words.eligible_support_lines({'supporting_line_market':'Australia'})
        self.assertEqual(dict((a,b) for a,b in zip(original,updated) if a!=b),{
            'Made for serious collectors only.':'Once it sells out, it’s done.',
            'A rare piece for those who know its meaning.':'Once this edition sells out, there is no second run.',
        })
        for strong in ('The moment lasts. The opportunity won’t.','Some moments are worth claiming while you can.'):
            self.assertIn(strong,updated)
        self.assertEqual(len(updated),len(set(updated)))
        self.assertIn('Once they’re gone, they’re gone.',words.APPROVED_SUPPORT_LINES)

    def test_other_markets_formats_winners_and_all_visuals_match_release(self):
        cases=json.loads((Path(__file__).parent/'fixtures/ads_supporting_line_baseline.json').read_text())
        for case in cases:
            args=case['args']
            with self.subTest(args=args):
                r=ads.build_ads_result_record(**args)
                fresh_scoped=args['country'] in ('USA','Australia') and args['campaign_type']=='Instant Experience' and not args['creative_refresh_context']
                if not fresh_scoped:
                    self.assertEqual(hashlib.sha256(r['master_prompt'].encode()).hexdigest(),case['prompt_sha256'])
                fp=[{k:v for k,v in row.items() if k not in ('supporting_line','on_image_subline','fomo_line','footer_pair_signature')} for row in r['instant_experience_fingerprints']]
                self.assertEqual(hashlib.sha256(json.dumps(fp,sort_keys=True).encode()).hexdigest(),case['visuals_sha256'])

    def test_saved_legacy_assignments_and_exports_never_reroll(self):
        for country in ('USA','Australia'):
            r=ads.build_ads_result_record('Synthetic Edition','Cricket',country,'Instant Experience',variation_token='saved')
            meta=r['product_metadata']
            for i,row in enumerate(meta['instant_experience_footer_selections']):
                row['supporting_line'] = usa.FALLBACK if country=='USA' else words.eligible_support_lines({})[i]
            before=copy.deepcopy(r)
            self.assertIs(ads.ensure_current_ads_result_prompt(r),r)
            self.assertEqual(r,before)
            rows=ads.resolve_standard_instant_experience_visuals(product_name='Synthetic Edition',category='Cricket',country=country,product_metadata=meta,variation_token='retry')
            self.assertEqual([x['supporting_line'] for x in rows],[x['supporting_line'] for x in meta['instant_experience_footer_selections']])
            from tests.test_ads_page import instant_experience_csv_notes
            notes=instant_experience_csv_notes()
            data=ads.build_instant_experience_copy_csv(r,concept_notes=notes)
            ads.parse_instant_experience_copy_csv(data,r)
            self.assertEqual(r,before)

    def test_approved_sentences_fit_existing_limits_and_font_width(self):
        # Bundled Medium provides a conservative width check; typography remains Regular 24–26 px.
        font=ImageFont.truetype(str(Path(__file__).resolve().parents[1]/'assets/fonts/Montserrat-Medium.ttf'),26)
        for line in usa.SUPPORT_LINES:
            self.assertFalse(ads.validate_instant_experience_on_image_copy(usa.HEADLINE,line,'CLAIM YOUR EDITION'))
            self.assertLessEqual(font.getlength(line),880)


if __name__=='__main__':unittest.main()
