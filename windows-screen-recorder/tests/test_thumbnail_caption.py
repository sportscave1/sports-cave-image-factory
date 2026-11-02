import unittest
import os
import tempfile
from pathlib import Path
from unittest.mock import patch
from desktop_recorder.thumbnail_caption import unique_caption
from desktop_recorder.coordinator import playback_capabilities


class CaptionTests(unittest.TestCase):
    def test_caption_capability_requires_complete_local_runtime(self):
        capability='windows.taskbar.caption.v1'
        with tempfile.TemporaryDirectory() as root, patch.dict(os.environ, {}, clear=True):
            self.assertNotIn(capability, playback_capabilities())
            root=Path(root)
            for name in ('PYTHON','WORKER'):
                path=root/name;path.write_text('fixture')
                os.environ['SC_RECORDER_OCR_'+name]=str(path)
            os.environ['SC_RECORDER_OCR_LIBRARY']=str(root)
            self.assertNotIn(capability, playback_capabilities())
            os.environ['SC_RECORDER_OCR_DATA']=str(root/'evidence')
            self.assertIn(capability, playback_capabilities())
            os.environ['SC_RECORDER_OCR_WORKER']=str(root/'missing')
            self.assertNotIn(capability, playback_capabilities())

    def row(self, text='Extensions - Google Chrome', score=.99):
        return dict(text=text, score=score, box=[[10,20],[250,20],[250,45],[10,45]])

    def test_exact_caption_and_ocr_spacing(self):
        match=unique_caption([self.row('Extensions-GoogleChrome')], 'Extensions - Google Chrome', 600, 400)
        self.assertEqual(match['rect'], [10,20,250,45])

    def test_hover_can_omit_only_browser_suffix(self):
        title='Extensions - Google Chrome'
        for text in ['Extensions - Google...', 'Extensions - Google…', 'Extensions-GoogleChr…']:
            with self.subTest(text=text):
                self.assertEqual(unique_caption([self.row(text)],title,600,400)['title'],title)
        for text in ['Extens…','Extensions - Goo…','Extensions - Google', 'Other - Google…', 'Extensions - GoogleX…']:
            with self.subTest(text=text),self.assertRaises(ValueError):
                unique_caption([self.row(text)],title,600,400)
        with self.assertRaises(ValueError):
            unique_caption([self.row(title),self.row('Extensions - Google…',score=.1)],title,600,400)

    def test_ambiguity_includes_low_confidence_duplicates(self):
        for rows in [[],[self.row(),self.row()], [self.row(),self.row(score=.1)]]:
            with self.subTest(rows=rows), self.assertRaises(ValueError):
                unique_caption(rows,'Extensions - Google Chrome',600,400)

    def test_no_fuzzy_or_confusable_matching(self):
        for text in ['extensions - Google Chrome','Extensions - Google Chr0me','Extensions – Google Chrome']:
            with self.subTest(text=text), self.assertRaises(ValueError):
                unique_caption([self.row(text)],'Extensions - Google Chrome',600,400)

    def test_low_nonfinite_confidence_and_out_of_image(self):
        for score in [.96,float('nan'),float('inf'),1.1]:
            with self.subTest(score=score), self.assertRaises(ValueError):
                unique_caption([self.row(score=score)],'Extensions - Google Chrome',600,400)
        with self.assertRaises(ValueError):
            unique_caption([self.row()],'Extensions - Google Chrome',200,400)
