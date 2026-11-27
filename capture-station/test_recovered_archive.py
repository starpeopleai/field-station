from unittest import TestCase
import test_internet_archive as fixtures
SID=fixtures.SID
from internet_archive import ArchiveAPI, hashes
from experiments import save

class RecoveredArchiveTests(TestCase):
    setUp=fixtures.ArchiveTests.setUp
    tearDown=fixtures.ArchiveTests.tearDown

    def approve(self):
        (self.folder/'recovery-original.mp4').write_bytes(b'preserved excerpt')
        self.note=dict(session_id=SID,operator_approved=True,scope='surviving_evidence',full_session_available=False,approved_epoch=self.decision['reviewed_epoch']+100,video_sha256=hashes(self.folder/'recovery-original.mp4')['sha256'])
        save(self.folder/'recovery-publication.json',self.note)
        return self.note

    def test_existing_plan_adds_all_recovered_evidence(self):
        self.approve()
        for directory,filename in [('recovery-crops','review.png'),('recovery-segments','segment.mkv'),('recovery-context','neighbor.mp4')]:
            folder=self.folder/directory;folder.mkdir();(folder/filename).write_bytes(b'evidence')
        self.assertTrue(self.a.complete_session_plan(self.job,self.m))
        names={f['name'] for f in self.job['files']}
        self.assertTrue({'recovery-original.mp4','recovery-publication.json','recovery-crops/review.png','recovery-segments/segment.mkv','recovery-context/neighbor.mp4'}<=names)
        self.assertEqual(self.job['manual_priority_epoch'],self.note['approved_epoch'])
        self.assertEqual(self.job['recovered_evidence'],self.note)

    def test_public_description_discloses_incomplete_original(self):
        self.approve();self.a.complete_session_plan(self.job,self.m)
        text=ArchiveAPI(self.a.private).item_headers(self.job)['x-archive-meta-description']
        self.assertIn('complete original session is unavailable',text)
        self.assertIn('final available record',text)
        self.assertNotIn('Recovered',ArchiveAPI(self.a.private).item_headers({'id':SID})['x-archive-meta-description'])

    def test_recovery_does_not_bypass_human_anomaly_requirement(self):
        self.approve();self.decision['confirmed_anomalous']=False;save(self.folder/'archive-decision.json',self.decision)
        self.assertFalse(self.a.archive_eligible(SID))

    def test_recovery_directory_symlinks_are_rejected(self):
        self.approve();(self.folder/'recovery-crops').symlink_to(self.root,target_is_directory=True)
        with self.assertRaisesRegex(ValueError,'Unsafe recovery evidence directory'):self.a.complete_session_plan(self.job,self.m)

    def test_recovery_derives_after_final_file_only(self):
        from unittest.mock import patch
        api=ArchiveAPI(self.a.private);job={'id':SID,'identifier':'recovery-test','recovered_evidence':{'operator_approved':True},'files':[{'name':'video.mp4'},{'name':'archive-index.json'}]}
        with patch.object(api,'raw') as raw:
            raw.return_value.__enter__.return_value.content=b'<Result><UploadId>upload-one</UploadId></Result>'
            api.initiate(job,{'name':'video.mp4'})
            self.assertEqual(raw.call_args.args[3]['x-archive-queue-derive'],'0')
            raw.return_value.__enter__.return_value.content=b''
            api.complete(job,{'name':'video.mp4'},'upload-one',[])
            self.assertEqual(raw.call_args.args[3]['x-archive-queue-derive'],'0')
            p=self.folder/'archive-index.json';p.write_bytes(b'');entry=dict(name=p.name,**hashes(p));api.small(job,entry,p)
            self.assertEqual(raw.call_args.args[3]['x-archive-queue-derive'],'1')

    def test_regular_multipart_processing_is_unchanged(self):
        from unittest.mock import patch
        api=ArchiveAPI(self.a.private)
        with patch.object(api,'raw') as raw:
            raw.return_value.__enter__.return_value.content=b'<Result><UploadId>upload-one</UploadId></Result>'
            api.initiate({'id':SID,'identifier':'normal-test'},{'name':'video.mp4'})
            self.assertEqual(raw.call_args.args[3]['x-archive-queue-derive'],'1')
