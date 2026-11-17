"""Offline scene naming, camera persistence and unchanged upload/CSV identities."""
import unittest
import ads_page as ads
import ads_ie_visual_systems as visuals
import ads_image_workflow as images
from ads_image_contracts import INSTANT_EXPERIENCE_CONCEPTS


class SceneNamesTests(unittest.TestCase):
    def resolve(self, token='scene-labels', metadata=None):
        return ads.resolve_standard_instant_experience_visuals(product_name='Collector Edition',
            category='Baseball', country='USA', variation_token=token, product_metadata=metadata or {})

    def test_fresh_cameras_rotate_with_fixed_scene_roles(self):
        seen = [set(), set(), set()]
        for n in range(20):
            rows = self.resolve(str(n))
            self.assertEqual(rows[1]['camera_role'], 'FRONT')
            self.assertEqual({rows[0]['camera_role'], rows[2]['camera_role']}, {'LEFT', 'RIGHT'})
            self.assertIn('collector hallway', rows[0]['room_type'])
            self.assertIn('product wall', rows[1]['room_type'])
            self.assertIn('residential man cave', rows[2]['room_type'])
            self.assertIn('clear but minimal man-cave setup', rows[2]['scene_brief'])
            for i, row in enumerate(rows):
                seen[i].add(row['camera_role'])
                self.assertEqual(row['camera_side'], row['assigned_camera_angle'])
        self.assertEqual(seen, [{'LEFT', 'RIGHT'}, {'FRONT'}, {'LEFT', 'RIGHT'}])

    def test_saved_camera_and_scene_assignments_survive_new_token(self):
        original = self.resolve()
        for legacy in (False, True):
            scenes = [dict(v) for v in original]
            if legacy:
                for i, s in enumerate(scenes):
                    s['assigned_camera_angle'] = visuals.CAMERAS[i]
            metadata = {'instant_experience_scene_selections': scenes,
                        'instant_experience_footer_selections': [dict(v) for v in original]}
            reopened = self.resolve('different-token', metadata)
            for actual, saved in zip(reopened, scenes):
                for key in ('assigned_camera_angle', 'wall_colour', 'wall_finish', 'lighting',
                            'primary_cue', 'room_type', 'headline_text', 'supporting_line', 'glazing_treatment'):
                    self.assertEqual(actual[key], saved[key], key)
                self.assertEqual(actual['camera_side'], saved['assigned_camera_angle'])

    def test_display_names_leave_upload_and_csv_identities_unchanged(self):
        names = ['Collector Hallway', 'Architectural Wall', 'Man Cave']
        slots = images.campaign_image_slots('Instant Experience')
        self.assertEqual([s['display_name'] for s in slots], names)
        for slot, spec in zip(slots, INSTANT_EXPERIENCE_CONCEPTS):
            self.assertEqual(slot['id'], spec['slot_id'])
            self.assertEqual(slot['filename_prefix'], spec['filename_prefix'])
            self.assertNotIn('Angle', slot['label'])
        for result in ({'campaign_type': 'Instant Experience'},
                       {'campaign_type': 'Instant Experience', '_legacy_ie_csv': True}):
            concepts = ads._ie_concepts_for_result(result)
            self.assertEqual([c['display_name'] for c in concepts], names)
            for c, spec in zip(concepts, INSTANT_EXPERIENCE_CONCEPTS):
                old = dict(spec)
                if ads._is_ie_copy_v2(result):
                    old.update(display_name=ads.ie_copy.ROUTES[spec['id']][0],
                               supporting_label=ads.ie_copy.ROUTES[spec['id']][1])
                self.assertEqual(ads._instant_experience_copy_csv_route_label(c),
                                 ads._instant_experience_copy_csv_route_label(old))

    def test_master_and_individual_prompts_use_resolved_cameras(self):
        rows = self.resolve()
        prompt = ads.build_standard_instant_experience_prompt('Collector Edition', 'Baseball', 'USA',
            'Instant Experience', variation_token='scene-labels')
        for old in ('Image 1 (RIGHT angle)', 'Image 3 (LEFT angle)', 'assigned RIGHT / FRONT / LEFT cameras',
                    'GROUP 1 — PREMIUM SCARCITY — RIGHT ANGLE', 'GROUP 3 — PREMIUM SCARCITY — LEFT ANGLE'):
            self.assertNotIn(old, prompt)
        for i, row in enumerate(rows, 1):
            self.assertIn(row['group_heading'], prompt)
            self.assertIn('Camera: ' + row['camera_side'], prompt)
            single = ads.build_standard_instant_experience_image_prompt(i, row,
                product_name='Collector Edition', category='Baseball', country='USA')
            self.assertIn('Selected camera: ' + row['camera_side'], single)
            self.assertNotIn('each uses its assigned right / centre / left camera', single)
        self.assertIn('clear but minimal man-cave setup', prompt)


if __name__ == '__main__':
    unittest.main()
