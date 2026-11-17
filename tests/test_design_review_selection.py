from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

import pytest
import streamlit as st
from streamlit.testing.v1 import AppTest

import design_review_page as gallery
import os_accounts
import product_upload_api as api
import product_upload_staff_queue as queue
from product_upload_dropbox import REVIEW


@pytest.fixture
def ui(monkeypatch):
    user = dict(id='fixture', role='admin', is_active=True)
    entries = [dict(id='id:'+str(i), rev='R1', name=title+'.psd',
                    path_display=REVIEW+'/'+title+'.psd', **{'.tag':'file'})
               for i, title in enumerate(('First', 'Second'))]
    details = [dict(design_name=title, sport=sport, review_status='needs_attention')
               for title, sport in (('First', 'NBA'), ('Second', 'Cricket'))]
    folder = Mock(return_value=([(source, data, '', False) for source, data in zip(entries, details)],
                              datetime.now(timezone.utc)))
    monkeypatch.setattr(st._main, '_form_data', None)
    monkeypatch.setattr(gallery, '_folder', folder)
    monkeypatch.setattr(gallery, '_artwork', lambda *args, **kwargs: None)
    monkeypatch.setattr(gallery, '_edit_link', lambda *args: None)
    monkeypatch.setattr(gallery.Intakes, 'read_review_gallery', lambda *args: {})
    monkeypatch.setattr(gallery, '_selection_fixture', (None, user), raising=False)
    monkeypatch.setattr(api, 'Dropbox', lambda: SimpleNamespace(
        metadata_if_present=lambda key: next((source for source in entries if source['id']==key), None)))
    enqueue = Mock(side_effect=lambda *args: 'job-'+args[1]['id'])
    monkeypatch.setattr(queue, 'enqueue', enqueue)
    app = AppTest.from_string("""
import streamlit as st
import design_review_page as gallery
st.html((gallery.Path(gallery.__file__).parent/'components/design_review_gallery.css').read_text())
app, user = gallery._selection_fixture
gallery._gallery(app, user)
""").run()
    assert not app.exception
    return app, entries, details, enqueue, user, folder


def test_selecting_designs_shows_both_actions_and_queues_every_selected_design(ui):
    app, entries, _, enqueue, _, _ = ui
    assert not any(button.key == 'design-review-trash' for button in app.button)
    app.checkbox(key=gallery._selection_key(entries[0])).check().run()
    app.checkbox(key=gallery._selection_key(entries[1])).check().run()
    assert not app.exception
    assert app.button(key='design-review-trash').proto.icon == ':material/delete:'
    assert app.button(key='design-review-enqueue').proto.icon == ':material/playlist_add:'
    assert any(item.value == '2 selected' for item in app.caption)
    enqueue.assert_not_called()
    app.button(key='design-review-enqueue').click().run()
    assert not app.exception and not app.error
    assert [call.args[1]['id'] for call in enqueue.call_args_list] == [source['id'] for source in entries]
    assert not any(box.value for box in app.checkbox)


def test_selection_delete_requires_confirmation_then_removes_exact_files(ui, monkeypatch):
    app, entries, _, enqueue, _, folder = ui
    removed = Mock(return_value=[])
    monkeypatch.setattr('design_review_delete.delete_design', removed)
    monkeypatch.setattr('files_upload_api.invalidate_directory_cache', Mock())
    monkeypatch.setattr('files_upload_api.invalidate_thumbnail_cache', Mock())
    for source in entries:
        app.checkbox(key=gallery._selection_key(source)).check().run()
    app.button(key='design-review-trash').click().run()
    assert not app.exception
    removed.assert_not_called()
    enqueue.assert_not_called()
    app.button(key='design-review-delete-confirm').click().run()
    assert not app.exception
    assert [call.args[1] for call in removed.call_args_list] == entries
    folder.clear.assert_called_once()


def test_bulk_queue_rejects_changed_revision_and_continues_other_selections(ui, monkeypatch):
    _, entries, details, enqueue, user, _ = ui
    monkeypatch.setattr(api, 'Dropbox', lambda: SimpleNamespace(metadata_if_present=lambda key:
        dict(entries[0], rev='changed') if key==entries[0]['id'] else entries[1]))
    queued, warnings = gallery._enqueue_selected(user, list(zip(entries, details)))
    assert len(queued)==1 and queued[0][0]==entries[1]
    assert len(warnings)==1 and 'changed in Dropbox' in warnings[0]
    assert enqueue.call_count==1


def test_bulk_queue_requires_upload_access(ui, monkeypatch):
    _, entries, details, enqueue, user, _ = ui
    monkeypatch.setattr(os_accounts, 'can_attach_missing_psd', lambda user: False)
    with pytest.raises(PermissionError):
        gallery._enqueue_selected(user, list(zip(entries, details)))
    enqueue.assert_not_called()


def test_bulk_queue_missing_sport_requires_selection(ui):
    app, entries, details, enqueue, _, _ = ui
    details[0].pop('sport')
    app.checkbox(key=gallery._selection_key(entries[0])).check().run()
    assert app.button(key='design-review-enqueue').disabled
    app.selectbox(key='design-review-bulk-sport').select('NBA').run()
    assert not app.button(key='design-review-enqueue').disabled
    app.button(key='design-review-enqueue').click().run()
    assert not app.exception and enqueue.call_args.args[3] == 'NBA'


def test_upload_access_without_delete_permission_allows_bulk_queue(ui, monkeypatch):
    app, entries, _, _, _, _ = ui
    monkeypatch.setattr(os_accounts, 'can_delete_files', lambda _: False)
    app.checkbox(key=gallery._selection_key(entries[0])).check().run()
    assert not app.exception and not app.button(key='design-review-enqueue').disabled
    assert not any(button.key == 'design-review-trash' for button in app.button)
