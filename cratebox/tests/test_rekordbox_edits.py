import asyncio
from pathlib import Path
import sys

import pytest
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from api import rekordbox_playlists as api


def test_playlist_edit_forwards_entry_ids_and_revision_without_retry(monkeypatch):
    calls = []
    async def tool(name, arguments=None):
        calls.append((name, arguments))
        return {'id':'100','name':'Set','revision':'new','editable':True,'entries':[]}
    monkeypatch.setattr(api, 'call_tool', tool)
    assert hasattr(api, 'PlaylistEdit')
    result = asyncio.run(api.edit_rekordbox_playlist('100', api.PlaylistEdit(
        action='move', expected_revision='old', entry_ids=['503'], position=1,
    )))
    assert result['revision'] == 'new'
    assert calls == [('edit_playlist', dict(action='move', playlist_id='100', expected_revision='old',
        name=None, entry_ids=['503'], track_ids=None, position=1, target_entry_id=None, before=True))]


def test_detail_rejects_mixed_playlist_revisions(monkeypatch):
    async def tool(name, arguments=None):
        return {'id':'100','revision':'r','entries':[{'entry_id':'501','track_id':'1','position':1}]}
    async def tracks(_):
        return [{'id':'different-entry','rekordbox_id':'1'}]
    monkeypatch.setattr(api, 'call_tool', tool)
    monkeypatch.setattr(api, 'get_rekordbox_playlist_tracks', tracks)
    assert hasattr(api, 'get_rekordbox_playlist_detail')
    with pytest.raises(api.HTTPException) as caught:
        asyncio.run(api.get_rekordbox_playlist_detail('100'))
    assert caught.value.status_code == 409
