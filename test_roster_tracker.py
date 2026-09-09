import json
from pathlib import Path
import tempfile
import unittest
from RosterTracker import snapshot_unlocked

class SnapshotTests(unittest.TestCase):
    def test_authoritative_fresh_matching_seed_only(self):
        with tempfile.TemporaryDirectory() as tmp:
            p=Path(tmp)/'state.json'
            self.assertFalse(snapshot_unlocked(p,'seed','Game 01',100))
            baseline=dict(version=1,seed_name='seed',connected=True,unlocked=['Game 01'],updated_at=95)
            for overrides, allowed in (({},True),({'seed_name':'other'},False),
                                       ({'connected':False},False),({'updated_at':60},False),
                                       ({'updated_at':110},False),({'unlocked':[]},False),
                                       ({'unlocked':'Game 01'},False),({'version':2},False)):
                p.write_text(json.dumps(baseline|overrides))
                self.assertEqual(snapshot_unlocked(p,'seed','Game 01',100),allowed)
            p.write_text(json.dumps(baseline))
            self.assertFalse(snapshot_unlocked(p,None,'Game 01',100))
            self.assertFalse(snapshot_unlocked(p,'seed','Game 02',100))
            p.write_text('{partial')
            self.assertFalse(snapshot_unlocked(p,'seed','Game 01',100))

if __name__=='__main__': unittest.main()
