import ast
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import image_factory
import mockup_product_prompts as prompts


class ProductVariationsTests(unittest.TestCase):
    def test_every_room_and_angle_pair_is_supported_for_each_card(self):
        self.assertEqual(len(prompts.ROOMS),3);self.assertEqual(len(prompts.ANGLES),3)
        for filename,rooms in prompts.ROOMS.items():
            self.assertEqual(len(rooms),5)
            for room in rooms:
                for angle in prompts.ANGLES:
                    with patch.object(prompts.random,'choice',side_effect=[room,angle]) as choose:
                        text=prompts.build(filename)
                    self.assertEqual(choose.call_args_list[0].args[0],rooms)
                    self.assertEqual(choose.call_args_list[1].args[0],prompts.ANGLES)
                    self.assertIn('Selected room: '+room,text)
                    self.assertIn('Selected camera angle: '+angle,text)
                    self.assertIn(prompts.ANGLE_GUIDANCE[angle],text)

    def test_new_generation_draws_independently_but_saved_pack_does_not_redraw(self):
        with patch.object(prompts.random,'choice',side_effect=lambda options:options[0]):
            first=image_factory.build_lifestyle_prompt_items('Collector','Tennis',local_only=True)
        with patch.object(prompts.random,'choice',side_effect=lambda options:options[-1]):
            second=image_factory.build_lifestyle_prompt_items('Collector','Tennis',local_only=True)
        self.assertNotEqual(first,second)
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);reference=root/'reference.webp';reference.write_bytes(b'test reference')
            with patch.object(prompts.random,'choice',side_effect=AssertionError('Saved selection must remain stable')):
                _,_,paths,_=image_factory.generate_lifestyle_prompt_pack('Collector','Tennis','collector',root,reference,prompt_items=first)
            self.assertEqual([p.read_text(encoding='utf-8').strip() for p in paths],[i['prompt'] for i in first])

    def test_saved_editor_override_keeps_current_run_selection_once(self):
        generated=prompts.build('01-man-cave-prompt.txt')
        override='Custom lighting preference\n'+prompts.build('02-office-prompt.txt')
        merged=prompts.preserve_selection(override,generated)
        self.assertIn('Custom lighting preference',merged)
        self.assertEqual(prompts.SCENE.findall(merged),prompts.SCENE.findall(generated))
        self.assertEqual(prompts.preserve_selection(merged,generated),merged)

    def test_only_three_active_cards_and_no_social_section_or_upload_changes(self):
        source=Path('app.py').read_text(encoding='utf-8');tree=ast.parse(source)
        labels=next(ast.literal_eval(n.value) for n in tree.body if isinstance(n,ast.Assign) and any(isinstance(t,ast.Name) and t.id=='PROMPT_LABELS' for t in n.targets))
        self.assertEqual(list(labels.values()),['01 - Man Cave (Product Page)','02 - Office (Product Page)','03 - Living Room (Product Page)'])
        self.assertEqual(list(labels),[s[0] for s in image_factory.LIFESTYLE_PROMPT_SPECS])
        self.assertNotIn('Social Lifestyle Mockups',source)
        self.assertIn('Upload image from ChatGPT',source)
        self.assertIn('lifestyle-upload::{result[\'run_dir\']}::{prompt_name}',source)
        self.assertTrue(image_factory.get_close_up_wall_prompt_foundation())


if __name__=='__main__':unittest.main()
