import json,time
from unittest.mock import patch
from test_label_queue import QueueTests
import detection_library as library

def listing(*a,**kw):return library.listing(*a,**kw,wait=True)

class LibraryTests(QueueTests):
 def setUp(self):
  super().setUp();library.invalidate()
  for p in (self.root/'notifications/outbox').glob('*/event.json'):
   e=json.loads(p.read_text());e['classification']='anomalous' if e['sequence']==1 else 'not_anomalous';e['review_only']=e['sequence']!=1;p.write_text(json.dumps(e))
  self.gallery=patch('labeled_frames.listing',return_value={'items':[]});self.gallery_mock=self.gallery.start()
 def tearDown(self):self.gallery.stop();library.invalidate();super().tearDown()
 def test_batch_persists_positive_and_negative_and_retries_without_duplication(self):
  from email_review import event_reviews,annotation_revision
  items=[dict(id=f'{i:032x}',label='anomalous' if i==1 else 'not_anomalous',request_id=f'{i+20:032x}') for i in (1,2)]
  result=library.label_batch(self.data,dict(items=items));self.assertTrue(all(r['saved'] for r in result['results']))
  manifest=json.loads((self.data/'email-reviews/training-manifest.json').read_text());self.assertEqual(len(manifest['examples']),2)
  for item in items:self.assertEqual(event_reviews(self.data,item['id'])[0]['label'],item['label'])
  completed=json.loads((self.root/'notifications/outbox'/items[0]['id']/'review-completion.json').read_text())
  self.assertEqual(completed['annotation_revision'],annotation_revision(self.data,items[0]['id']))
  before=(self.data/'email-reviews/training-manifest.json').read_bytes();retry=library.label_batch(self.data,dict(items=items))
  self.assertTrue(all(r['saved'] for r in retry['results']));self.assertEqual(before,(self.data/'email-reviews/training-manifest.json').read_bytes())
 def test_batch_commits_good_items_and_preserves_failed_item_for_retry(self):
  items=[dict(id=f'{i:032x}',label='not_anomalous',request_id=f'{i+20:032x}') for i in (1,2)]
  (self.root/'notifications/outbox'/items[1]['id']/'native-object.png').write_bytes(b'corrupt')
  result=library.label_batch(self.data,dict(items=items));self.assertTrue(result['results'][0]['saved']);self.assertFalse(result['results'][1]['saved'])
  self.assertEqual(len(json.loads((self.data/'email-reviews/training-manifest.json').read_text())['examples']),1)
 def test_storage_exhaustion_is_retryable_but_invalid_review_is_not(self):
  import errno
  item=dict(id=f'{1:032x}',label='anomalous',request_id='e'*32)
  for exc,retryable in [(OSError(errno.ENOSPC,'No space left on device'),True),(OSError(errno.EDQUOT,'Disk quota exceeded'),True),(ValueError('Invalid object'),False)]:
   with patch.object(library,'label',side_effect=exc):result=library.label_batch(self.data,dict(items=[item]))['results'][0]
   self.assertFalse(result['saved']);self.assertEqual(result['retryable'],retryable);self.assertEqual(result['request_id'],item['request_id'])
  recovered=library.label_batch(self.data,dict(items=[item]))['results'][0]
  self.assertTrue(recovered['saved'])
 def test_incomplete_directory_does_not_force_full_index_rebuild(self):
  import os
  from email_training import review_batch,current_review_index
  item=dict(id=f'{1:032x}',label='anomalous',request_id='a'*32)
  self.assertTrue(library.label_batch(self.data,dict(items=[item]))['results'][0]['saved'])
  root=self.data/'email-reviews';(root/'examples'/('f'*32)).mkdir()
  os.utime(root/'examples',ns=(time.time_ns()+1000000000,)*2)
  with patch('concurrent.futures.ThreadPoolExecutor',side_effect=AssertionError('Full rebuild should not run')):
   with review_batch(self.data):self.assertEqual(len(current_review_index(self.data)),1)
 def test_rebuild_skips_incomplete_directory_and_preserves_committed_review(self):
  from email_training import review_batch,current_review_index
  item=dict(id=f'{1:032x}',label='anomalous',request_id='a'*32)
  library.label_batch(self.data,dict(items=[item]));root=self.data/'email-reviews';(root/'examples'/('f'*32)).mkdir();(root/'training-manifest.json').unlink()
  with review_batch(self.data):self.assertEqual(len(current_review_index(self.data)),1)
 def test_newer_receipt_still_requires_recovery(self):
  import os
  from email_training import review_batch,current_review_index
  item=dict(id=f'{1:032x}',label='anomalous',request_id='a'*32)
  library.label_batch(self.data,dict(items=[item]));root=self.data/'email-reviews';stamp=time.time_ns()+1000000000
  p=root/'examples'/item['id']/'review.json';record=json.loads(p.read_text());record['label']='not_anomalous';p.write_text(json.dumps(record))
  for folder in ['examples','history']:os.utime(root/folder,ns=(stamp,stamp))
  with review_batch(self.data):self.assertEqual(current_review_index(self.data)[0]['label'],'not_anomalous')
 def test_model_labels_are_not_reviews_or_training(self):
  self.assertEqual(listing(self.data)['counts'],dict(all=3,anomalous=1,not_anomalous=2,needs_review=1,human_reviewed=0,human_reviewed_anomalous=0,starred=0))
  self.assertFalse((self.data/'email-reviews').exists())
 def test_needs_review_contains_only_unreviewed_anomalies(self):
  page=listing(self.data,'needs_review')
  self.assertEqual([r['id'] for r in page['items']],[f'{1:032x}'])
  self.assertEqual(page['counts']['needs_review'],1)
  self.assertEqual(listing(self.data,'not_anomalous')['total'],2)
  library.label(self.data,dict(id=f'{1:032x}',label='anomalous',request_id='f'*32))
  self.assertEqual(listing(self.data,'needs_review')['total'],0)
 def test_independent_filters_allow_auditing_negative_suggestions(self):
  page=listing(self.data,'all',classification='all',review_status='needs_review')
  self.assertEqual(page['total'],3)
  negative=listing(self.data,'all',classification='not_anomalous',review_status='needs_review',limit=1)
  self.assertEqual(negative['total'],2);self.assertIsNotNone(negative['next_cursor'])
  self.assertEqual(negative['items'][0]['label'],'not_anomalous')
  self.assertEqual(negative['filter_counts']['classification'],dict(all=3,anomalous=1,not_anomalous=2))
  next_page=listing(self.data,'all',classification='not_anomalous',review_status='needs_review',before=negative['next_cursor'],limit=1)
  self.assertNotEqual(next_page['items'][0]['id'],negative['items'][0]['id'])
  self.assertEqual(listing(self.data,'needs_review')['total'],1)
 def test_negative_suppression_is_not_review_dismissal(self):
  (self.root/'notifications/outbox'/f'{2:032x}'/'delivery.json').write_text('{"state":"suppressed"}')
  self.assertEqual(listing(self.data,'not_anomalous')['total'],2)
 def test_human_override_keeps_model_label_and_moves_views(self):
  import label_queue
  key=f'{1:032x}';library.label(self.data,dict(id=key,label='not_anomalous',request_id='a'*32))
  record=json.loads((self.data/'email-reviews/examples'/key/'review.json').read_text())
  self.assertTrue(record['human_confirmed'])
  self.gallery_mock.return_value={'items':[dict(kind='review',video_id=key,created=1,annotation=dict(id=key,label='not_anomalous'),image_url='/crop')]}
  library.invalidate();row=listing(self.data,'human_reviewed')['items'][0]
  self.assertEqual(row['model_label'],'anomalous');self.assertEqual(row['label'],'not_anomalous')
  self.assertEqual(listing(self.data,'needs_review')['total'],0)
  library.label(self.data,dict(id=key,label='anomalous',request_id='b'*32))
  self.assertEqual(json.loads((self.data/'email-reviews/examples'/key/'review.json').read_text())['label'],'anomalous')
 def test_deleted_detection_does_not_survive_cached_listing(self):
  import shutil
  listing(self.data)
  key=f'{2:032x}';shutil.rmtree(self.root/'notifications/outbox'/key)
  page=library.listing(self.data,'all',classification='all',review_status='needs_review')
  self.assertEqual(page['total'],2)
  self.assertNotIn(key,{row['id'] for row in page['items']})

 def test_paging_survives_newer_review(self):
  page=listing(self.data,limit=1);second=listing(self.data,before=page['next_cursor'],limit=1)
  self.assertNotEqual(page['items'][0]['id'],second['items'][0]['id'])

 def test_human_anomalous_filter_requires_both_conditions(self):
  key=f'{1:032x}'
  self.assertEqual(listing(self.data,'human_reviewed_anomalous')['total'],0)
  library.label(self.data,dict(id=key,label='anomalous',request_id='a'*32))
  self.gallery_mock.return_value={'items':[dict(kind='review',video_id=key,created=1,annotation=dict(id=key,label='anomalous'),image_url='/crop')]}
  library.invalidate();page=listing(self.data,'human_reviewed_anomalous')
  self.assertEqual(page['total'],1);self.assertEqual(page['items'][0]['id'],key)
  library.label(self.data,dict(id=key,label='not_anomalous',request_id='b'*32))
  self.assertEqual(listing(self.data,'human_reviewed_anomalous')['total'],0)
  self.assertEqual(listing(self.data,'human_reviewed')['total'],1)

 def test_external_review_overrides_stale_index_without_waiting_for_refresh(self):
  import time
  from email_training import store_review
  import hashlib
  key=f'{1:032x}';listing(self.data)
  store_review(self.data,dict(event_id=key,sample_id='f'*32,label='not_anomalous',human_confirmed=True,source='station_web_review',message_id='external',reviewed_epoch=time.time(),native_crop_sha256=hashlib.sha256(self.crop).hexdigest()),self.crop)
  page=listing(self.data,'needs_review');self.assertNotIn(key,[r['id'] for r in page['items']])
  reviewed=listing(self.data,'human_reviewed')['items'];self.assertEqual(len(reviewed),1);self.assertEqual(reviewed[0]['sample_id'],'f'*32)
 def test_clear_includes_old_model_and_filters_warm_cache_preserving_reviews(self):
  import label_queue
  key=f'{1:032x}'
  library.label(self.data,dict(id=key,label='not_anomalous',request_id='c'*32))
  (self.root/'notifications/active-model-release.json').write_text(json.dumps(dict(state='deployed',health_verified=True,version='new-model',deployed_epoch=10,clear_candidate_backlog=True)))
  self.assertEqual(label_queue.detections(self.data)['items'],[])
  self.assertEqual(listing(self.data,'needs_review')['total'],0)
  result=label_queue.clear_backlog(self.data,cutoff=2.5)
  self.assertEqual(result['frames_cleared'],1)
  self.assertTrue(json.loads((self.root/'notifications/outbox'/f'{2:032x}'/'label-queue-dismissed.json').read_text())['dismissed'])
  self.assertEqual([r['id'] for r in listing(self.data,'all')['items'] if not r['human_reviewed']],[f'{3:032x}'])
  self.assertEqual(listing(self.data,'human_reviewed')['total'],1)
  # Simulate a background index publishing stale pre-clear objects again.
  library.invalidate()
  self.assertEqual([r['id'] for r in listing(self.data,'all')['items'] if not r['human_reviewed']],[f'{3:032x}'])
  label_queue.clear_backlog(self.data,cutoff=10)
  self.assertEqual(listing(self.data,'needs_review')['total'],0)
  self.assertEqual(listing(self.data,'human_reviewed')['total'],1)
  self.assertEqual(json.loads((self.data/'email-reviews/examples'/key/'review.json').read_text())['label'],'not_anomalous')
 def test_clear_cutoff_does_not_regress_on_older_repair(self):
  import label_queue
  label_queue.clear_backlog(self.data,cutoff=10)
  label_queue.clear_backlog(self.data,cutoff=2)
  self.assertEqual(json.loads((self.data/'review-queue-cleared.json').read_text())['cutoff_epoch'],10)

class PendingClearVisibilityTests(LibraryTests):
 def test_pending_clear_updates_cards_counts_and_preserves_stars(self):
  from detection_actions import set_star
  from review_queue_visibility import mark
  key=f'{1:032x}';set_star(self.data,dict(id=key,starred=True))
  listing(self.data,'all')
  mark(self.data,2.5,'pending')
  result=listing(self.data,'all',classification='all',review_status='needs_review')
  self.assertEqual({r['id'] for r in result['items']},{key,f'{3:032x}'})
  self.assertEqual(result['total'],2);self.assertEqual(result['filter_counts']['classification']['all'],2)
  self.assertTrue((self.root/'notifications/outbox'/f'{2:032x}'/'event.json').exists())

class PendingResetTests(QueueTests):
 def test_explicit_reset_discards_old_intent_but_accepts_new_review(self):
  (self.data/'review-pending-reset.json').write_text(json.dumps(dict(epoch=100)))
  items=[dict(id=f'{1:032x}',label='not_anomalous',request_id='a'*32),dict(id=f'{2:032x}',label='not_anomalous',request_id='b'*32,queued_at=101)]
  result=library.label_batch(self.data,dict(items=items))['results']
  self.assertFalse(result[0]['saved']);self.assertTrue(result[0]['discarded']);self.assertTrue(result[1]['saved'])
  rows=json.loads((self.data/'email-reviews/training-manifest.json').read_text())['examples']
  self.assertEqual([r['event_id'] for r in rows],[f'{2:032x}'])

class StarredLibraryTests(LibraryTests):
 def test_saved_star_is_returned_in_listing_and_filter(self):
  from detection_actions import set_star
  key=f'{1:032x}'
  set_star(self.data,dict(id=key,starred=True))
  result=listing(self.data,'starred')
  self.assertEqual(result['total'],1);self.assertEqual(result['counts']['starred'],1)
  self.assertTrue(result['items'][0]['starred']);self.assertEqual(result['items'][0]['id'],key)
  set_star(self.data,dict(id=key,starred=False))
  self.assertEqual(listing(self.data,'starred')['total'],0)
