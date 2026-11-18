"""Synthetic UI checks: selection must not reload providers or shift the gallery."""
from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import Mock

from streamlit.testing.v1 import AppTest

import design_review_page as gallery
from product_upload_dropbox import REVIEW


def test_selection_keeps_gallery_mounted_and_reuses_displayed_data(monkeypatch):
    designs = []
    for i in range(6):
        source = {'.tag': 'file', 'id': f'id:fixture-{i}', 'rev': 'fixture',
                  'name': f'Design {i}.psd', 'path_display': f'{REVIEW}/Design {i}.psd'}
        designs.append((source, {'design_name': f'Design {i}', 'sport': 'Cricket'}, '', False))
    folder = Mock(return_value=(designs, datetime.now(timezone.utc)))
    rows = Mock(return_value={})
    monkeypatch.setattr(gallery, '_folder', folder)
    monkeypatch.setattr(gallery, 'Intakes', lambda _: SimpleNamespace(read_review_gallery=rows))
    monkeypatch.setattr('os_accounts.can_delete_files', lambda _: True)
    monkeypatch.setattr('os_accounts.can_access_page', lambda *_: True)
    ui = AppTest.from_string('''
from types import SimpleNamespace
import design_review_page as gallery
gallery._gallery(SimpleNamespace(), {'id': 'synthetic-reviewer'})
''').run()
    assert not ui.exception
    assert len(ui.checkbox) == 6
    assert ui.button(key='design-review-enqueue').label == 'Add to queue'
    assert ui.button(key='design-review-enqueue').disabled
    assert ui.button(key='design-review-trash').disabled
    # Count/queue/trash exist before selection, retaining the same delta positions.
    initial_keys = [item.key for item in ui.button]
    for index, value in [(0, True), (5, True), (0, False), (5, False)]:
        ui.checkbox[index].set_value(value).run()
        assert not ui.exception
        assert len(ui.checkbox) == 6
        assert [item.key for item in ui.button] == initial_keys
    assert folder.call_count == rows.call_count == 1
    assert ui.button(key='design-review-enqueue').disabled
    ui.checkbox[2].check().run()
    assert not ui.button(key='design-review-enqueue').disabled
    # Non-selection interactions must refresh data, not reuse the selection snapshot.
    next(button for button in ui.button if button.label == 'Refresh').click().run()
    assert not ui.exception
    assert folder.call_count == rows.call_count == 2
    ui.text_input[0].set_value('Design 2').run()
    assert not ui.exception
    assert len(ui.checkbox) == 1
    assert folder.call_count == rows.call_count == 3


def test_edit_link_has_visible_text_and_preserves_revision(monkeypatch):
    html = Mock()
    monkeypatch.setattr(gallery.st, 'html', html)
    gallery._edit_link({'id': 'id:test', 'rev': 'revision'}, 'A & B')
    markup = html.call_args.args[0]
    assert '>Edit</a>' in markup
    assert 'aria-label="Edit A &amp; B"' in markup
    assert 'rev=revision' in markup
    assert 'data-design-review-prompt=' in markup
