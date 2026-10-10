import hashlib
import io
import json
import subprocess
import tarfile
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from zitar_next.backup_guard import deliver,verify

class BackupGuardTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.root=Path(self.tmp.name)
    def archive(self,n):
        p=self.root/('zitar-'+str(n)+'.tar.gz')
        with tarfile.open(p,'w:gz') as z:
            member=tarfile.TarInfo('runtime/account.json');data=b'{"cash":10000}'
            member.size=len(data);z.addfile(member,io.BytesIO(data))
        p.with_suffix('.gz.sha256').write_text(hashlib.sha256(p.read_bytes()).hexdigest()+'  '+p.name)
        return p
    def runner(self,args,**kwargs):return SimpleNamespace(stdout=b'type = crypt\n')
    def test_offsite_failure_preserves_all_backups(self):
        for n in range(4):self.archive(n)
        def failed(args,**kwargs):
            if 'check' in args:raise subprocess.CalledProcessError(1,args)
            return self.runner(args)
        with self.assertRaises(subprocess.CalledProcessError):deliver(self.root,'zitarcrypt:backup','private',2,failed)
        self.assertEqual(len(list(self.root.glob('*.tar.gz'))),4)
        self.assertFalse(list(self.root.glob('*.offsite.json')))
    def test_prunes_only_verified_offsite_backups(self):
        for n in range(4):
            self.archive(n);deliver(self.root,'zitarcrypt:backup','private',2,self.runner)
        self.assertEqual([p.name for p in sorted(self.root.glob('*.tar.gz'))],['zitar-2.tar.gz','zitar-3.tar.gz'])
    def test_unverified_old_backup_is_preserved(self):
        for n in range(4):self.archive(n)
        self.assertEqual(deliver(self.root,'zitarcrypt:backup','private',2,self.runner)['removed'],[])
    def test_corruption_blocks_upload(self):
        p=self.archive(0);p.write_bytes(b'corrupt')
        with self.assertRaises(ValueError):verify(p)
    def test_plain_remote_rejected(self):
        self.archive(0)
        with self.assertRaises(ValueError):deliver(self.root,'plain:backup','private',runner=self.runner)
    def test_remote_configuration_must_be_encrypted(self):
        self.archive(0)
        with self.assertRaises(ValueError):deliver(self.root,'zitarcrypt:backup','private',runner=lambda *a,**k:SimpleNamespace(stdout=b'type = sftp'))
    def test_monitor_detects_missing_and_stale_success(self):
        from zitar_next.backup_monitor import health
        self.assertTrue(health(self.root))
        p=self.root/'BACKUP_LAST_SUCCESS';p.write_text('ok')
        self.assertIn('verified offsite backup older than 26 hours or missing',health(self.root,p.stat().st_mtime+27*3600))
    def test_disk_shortage_blocks_snapshot(self):
        from unittest.mock import patch
        from zitar_next.hosting import backup
        from zitar_next.store import init
        base=self.root/'runtime';base.mkdir();root=init(self.root/'next')
        with patch('zitar_next.hosting.assert_stopped'),patch('zitar_next.hosting.shutil.disk_usage',return_value=SimpleNamespace(free=0)):
            with self.assertRaises(ValueError):backup(base,root,self.root/'out')
        self.assertFalse(list((self.root/'out').glob('*.tar.gz')))

if __name__=='__main__':unittest.main()
