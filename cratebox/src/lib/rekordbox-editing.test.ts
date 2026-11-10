import { afterEach, expect, it, vi } from 'vitest';
import * as api from './cratebox-api';

afterEach(() => vi.unstubAllGlobals());

it('submits the selected playlist entry and revision once and propagates a conflict', async () => {
  const fetch = vi.fn().mockResolvedValue(new Response(JSON.stringify({ detail: 'Playlist changed; reload it before editing.' }), { status: 409 }));
  vi.stubGlobal('fetch', fetch);
  expect(api).toHaveProperty('editRekordboxPlaylist');
  await expect(api.editRekordboxPlaylist('http://localhost:8000', '100', 'revision', { action: 'move', entry_ids: ['503'], position: 1 })).rejects.toThrow('Playlist changed');
  expect(fetch).toHaveBeenCalledTimes(1);
  const body = JSON.parse(fetch.mock.calls[0]![1].body);
  expect(body).toMatchObject({ expected_revision: 'revision', entry_ids: ['503'], position: 1 });
});
