import json
from fastmcp import Client
from rekordbx_mcp.server import build_server


async def test_upstream_track_file_path_resolves_active_tracks_without_a_playlist(playable_snapshot):
    async with Client(build_server(playable_snapshot)) as client:
        result = await client.call_tool("get_track_file_path", {"track_id": "1"})
        assert result.structured_content["file_path"] == str(playable_snapshot / "music/Été #1.mp3")
        assert (await client.call_tool("get_track_file_path", {"track_id": "4"}, raise_on_error=False)).is_error


async def test_generic_tracks_preserve_order_duplicates_and_page(playable_snapshot):
    async with Client(build_server(playable_snapshot)) as client:
        result = await client.call_tool('get_collection_tracks', {'track_ids': ['2', '1', '2']})
        tracks = json.loads(result.content[0].text)
        assert [track['id'] for track in tracks] == ['2', '1', '2']
        assert tracks[1]['title'] == 'One More Time'
        assert tracks[1]['file_path'].endswith('Été #1.mp3')
        first = await client.call_tool('get_collection_tracks', {'offset': 0, 'limit': 1})
        second = await client.call_tool('get_collection_tracks', {'offset': 1, 'limit': 1})
        assert json.loads(first.content[0].text)[0]['id'] != json.loads(second.content[0].text)[0]['id']

async def test_generic_locations_are_exact_and_unknown_ids_fail(playable_snapshot):
    location = str(playable_snapshot / 'music/Été #1.mp3')
    async with Client(build_server(playable_snapshot)) as client:
        result = await client.call_tool('get_collection_tracks', {'file_paths': [location, location]})
        assert [t['id'] for t in json.loads(result.content[0].text)] == ['1', '1']
        for args in [
            {'track_ids': ['999']}, {'file_paths': [location + '.other']},
            {'track_ids': ['1'], 'file_paths': [location]},
            {'track_ids': ['1'], 'offset': 1}, {'track_ids': []},
        ]:
            assert (await client.call_tool('get_collection_tracks', args, raise_on_error=False)).is_error, args
