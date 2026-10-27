"""Isolated regression checks: never initialize or change the live board."""
import concurrent.futures
import contextlib
import json
import os
import pathlib
import sqlite3
import subprocess
import sys
import tempfile
import threading
import time
import types
import unittest
from unittest import mock


SOURCE = pathlib.Path(os.environ.get('COLLAB_SOURCE', pathlib.Path(__file__).resolve().parents[1] / 'collab.py'))
sys.path.insert(0, str(SOURCE.resolve().parent))


class CollaborationRobustness(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix='collab-audit-')
        self.addCleanup(self.tmp.cleanup)
        self.root = pathlib.Path(self.tmp.name)
        self.hub = types.ModuleType('collab_audit')
        self.hub.__file__ = str(SOURCE)
        exec(compile(SOURCE.read_text(), str(SOURCE), 'exec'), self.hub.__dict__)
        for key, value in {
            'BASE_DIR': self.root,
            'STATE_DIR': self.root / 'state',
            'DB_PATH': self.root / 'state/collab.db',
            'JSON_SNAPSHOT_PATH': self.root / 'state/board.json',
            'BOARD_MD_PATH': self.root / 'BOARD.md',
            'SHARED_ARTIFACTS_DIR': self.root / 'shared',
        }.items():
            setattr(self.hub, key, value)
        self.hub.init_db()

    def test_vote_can_be_recorded(self):
        decision = self.hub.op_propose('a', 'Design', 'Use the shared board.')
        result = self.hub.op_vote(decision['decision_id'], 'b', 'approve')
        self.assertTrue(result['ok'])
        self.assertIn('b', result['votes'])

    def test_mentions_ignore_sentence_punctuation(self):
        self.assertEqual(self.hub.extract_mentions('Hi @claude. Ask @codex, then @agent.name!'),
                         ['agent.name', 'claude', 'codex'])

    def test_foreign_owned_review_task_cannot_be_claimed(self):
        task = self.hub.op_task_add('a', 'Task', owner='a')
        self.hub.op_task_update(task['task_id'], 'a', status='review')
        self.assertFalse(self.hub.op_task_claim(task['task_id'], 'b')['ok'])

    def test_foreign_owned_task_cannot_be_updated(self):
        task = self.hub.op_task_add('a', 'Task', owner='a')
        self.assertFalse(self.hub.op_task_update(task['task_id'], 'b', status='done')['ok'])

    def test_done_task_cannot_be_reopened_by_claim(self):
        task = self.hub.op_task_add('a', 'Task', owner='a')
        self.hub.op_task_update(task['task_id'], 'a', status='done')
        self.assertFalse(self.hub.op_task_claim(task['task_id'], 'b')['ok'])

    def test_file_lock_aliases_conflict(self):
        (self.root / 'shared/a.py').write_text('')
        self.assertTrue(self.hub.op_lock('shared/a.py', 'a')['ok'])
        self.assertFalse(self.hub.op_lock(str(self.root / 'shared/a.py'), 'b')['ok'])

    def test_legacy_absolute_lock_is_respected_and_owner_can_release_alias(self):
        expiry = '2099-01-01T00:00:00-05:00'
        with self.hub.get_db() as conn:
            conn.execute('INSERT INTO locks VALUES (?, ?, ?, ?, ?)',
                         (str(self.root / 'shared/a.py'), 'a', 'legacy lock', self.hub.now_iso(), expiry))
        self.assertFalse(self.hub.op_lock('./shared/a.py', 'b')['ok'])
        self.assertFalse(self.hub.op_unlock('shared/a.py', 'b')['ok'])
        self.assertTrue(self.hub.op_unlock('shared/a.py', 'a')['ok'])
        self.assertTrue(self.hub.op_lock('shared/a.py', 'b')['ok'])

    def test_explicit_force_can_transfer_task(self):
        task = self.hub.op_task_add('a', 'Task', owner='a')
        self.assertTrue(self.hub.op_task_update(task['task_id'], 'b', status='done', force=True)['ok'])
        self.assertTrue(self.hub.op_task_claim(task['task_id'], 'b', force=True)['ok'])

    def test_failed_claim_does_not_set_working_status(self):
        self.hub.op_join('b', 'test', 'test', 'test', announce=False)
        task = self.hub.op_task_add('a', 'Task', owner='a')
        self.assertFalse(self.hub.op_task_claim(task['task_id'], 'b')['ok'])
        with self.hub.get_db() as conn:
            status = conn.execute('SELECT status FROM agents WHERE id = ?', ('b',)).fetchone()['status']
        self.assertEqual(status, 'online')

    def test_negative_lock_lease_rejected(self):
        try:
            result = self.hub.op_lock('shared/a.py', 'a', ttl_seconds=-1)
        except (ValueError, TypeError):
            return
        self.assertFalse(result['ok'])

    def test_lock_expiry_compares_instants_across_daylight_saving_offsets(self):
        with self.hub.get_db() as conn:
            conn.execute('INSERT INTO locks VALUES (?, ?, ?, ?, ?)',
                         ('expired', 'a', '', '2026-11-01T01:00:00-04:00', '2026-11-01T01:45:00-04:00'))
            conn.execute('INSERT INTO locks VALUES (?, ?, ?, ?, ?)',
                         ('future', 'a', '', '2026-11-01T01:00:00-04:00', '2026-11-01T01:45:00-05:00'))
            with mock.patch.object(self.hub, 'now_iso', return_value='2026-11-01T06:30:00+00:00'):
                self.hub.cleanup_expired_locks(conn)
            self.assertEqual([row['filepath'] for row in conn.execute('SELECT filepath FROM locks')], ['future'])

    def test_snapshot_error_keeps_durable_commit_and_returns_cache_warning(self):
        self.hub.op_post('a', 'committed baseline')
        self.hub.BOARD_MD_PATH.unlink()
        self.hub.BOARD_MD_PATH.mkdir()
        result = self.hub.op_post('a', 'durable despite snapshot error')
        self.assertTrue(result['ok'])
        self.assertIn('cache_warning', result['state'])
        with self.hub.get_db() as conn:
            durable = [row['content'] for row in conn.execute('SELECT content FROM messages')]
        published = [row['content'] for row in json.loads(self.hub.JSON_SNAPSHOT_PATH.read_text())['messages']]
        self.assertIn('durable despite snapshot error', durable)
        self.assertTrue(set(published).issubset(durable))

    def test_snapshot_files_are_replaced_from_complete_staged_files(self):
        self.hub.op_post('a', 'baseline')
        real_replace = self.hub.os.replace
        replacements = []
        def inspect_replace(src, dst):
            src, dst = pathlib.Path(src), pathlib.Path(dst)
            self.assertEqual(src.parent, dst.parent)
            self.assertNotEqual(src, dst)
            self.assertTrue(src.exists())
            self.assertTrue(dst.exists())
            if dst == self.hub.JSON_SNAPSHOT_PATH:
                self.assertEqual(json.loads(dst.read_text())['messages'][-1]['content'], 'baseline')
                self.assertEqual(json.loads(src.read_text())['messages'][-1]['content'], 'next')
            replacements.append(dst)
            real_replace(src, dst)
        with mock.patch.object(self.hub.os, 'replace', side_effect=inspect_replace):
            self.hub.op_post('a', 'next')
        self.assertEqual(replacements, [self.hub.JSON_SNAPSHOT_PATH, self.hub.BOARD_MD_PATH])

    def test_cross_process_commit_precedes_snapshot_and_writers_stay_ordered(self):
        script = r'''
import pathlib, sys, time, types
source, root, agent = pathlib.Path(sys.argv[1]), pathlib.Path(sys.argv[2]), sys.argv[3]
hub = types.ModuleType('isolated_hub')
hub.__file__ = str(source)
exec(compile(source.read_text(), str(source), 'exec'), hub.__dict__)
for key, value in {'BASE_DIR': root, 'STATE_DIR': root / 'state',
    'DB_PATH': root / 'state/collab.db', 'JSON_SNAPSHOT_PATH': root / 'state/board.json',
    'BOARD_MD_PATH': root / 'BOARD.md', 'SHARED_ARTIFACTS_DIR': root / 'shared'}.items():
    setattr(hub, key, value)
original = hub.publish_snapshots
if agent == 'first':
    def paused(state):
        (root / 'committed').write_text('ready')
        deadline = time.monotonic() + 8
        while not (root / 'release').exists():
            if time.monotonic() > deadline:
                raise RuntimeError('test release timed out')
            time.sleep(.01)
        original(state)
    hub.publish_snapshots = paused
(root / (agent + '-started')).write_text('started')
hub.op_post(agent, agent)
(root / (agent + '-finished')).write_text('finished')
'''
        def start(agent):
            process = subprocess.Popen([sys.executable, '-c', script, str(SOURCE.resolve()), str(self.root), agent],
                                       stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
            self.addCleanup(lambda: process.poll() is None and process.kill())
            return process
        def await_file(name):
            deadline = time.monotonic() + 5
            while not (self.root / name).exists():
                if time.monotonic() > deadline:
                    self.fail(f'Timed out waiting for {name}')
                time.sleep(.01)
        first = start('first')
        await_file('committed')
        # Bypass the hub mutex only for this independent durability probe.
        with contextlib.closing(sqlite3.connect(self.hub.DB_PATH)) as conn:
            self.assertEqual(conn.execute('SELECT content FROM messages').fetchall(), [('first',)])
        second = start('second')
        await_file('second-started')
        time.sleep(.08)
        self.assertFalse((self.root / 'second-finished').exists())
        (self.root / 'release').write_text('release')
        for process in (first, second):
            stdout, stderr = process.communicate(timeout=10)
            self.assertEqual(process.returncode, 0, stdout + stderr)
        with self.hub.get_db() as conn:
            durable = [row['content'] for row in conn.execute('SELECT content FROM messages ORDER BY id')]
        published = [row['content'] for row in json.loads(self.hub.JSON_SNAPSHOT_PATH.read_text())['messages']]
        self.assertEqual(durable, ['first', 'second'])
        self.assertEqual(published, durable)

    def test_concurrent_claims_have_exactly_one_winner(self):
        agents = [f'agent-{i}' for i in range(8)]
        for agent in agents:
            self.hub.op_join(agent, 'test', 'test', 'test', announce=False)
        task = self.hub.op_task_add('creator', 'One owner')
        barrier = threading.Barrier(len(agents))
        def claim(agent):
            barrier.wait()
            return self.hub.op_task_claim(task['task_id'], agent)
        with concurrent.futures.ThreadPoolExecutor(max_workers=len(agents)) as pool:
            results = list(pool.map(claim, agents))
        self.assertEqual(sum(bool(result['ok']) for result in results), 1)


if __name__ == '__main__':
    unittest.main(verbosity=2)
