# Human-grounded machine training

Machine-only is now an automatically managed self-training lane, not a human-label exclusion rule. Every new snapshot starts from the current human-reviewed training dataset, preserving its original labels and source identifiers. Eligible machine labels are added from this lane's own immutable corpus; reviewed identities and pixel hashes override machine labels. Machine examples have a bounded, lower loss-weight budget so repeated automatic negatives cannot overwhelm reviewed positives.

Hybrid continues to require teacher/student agreement before admitting machine examples. Machine-only admits its own confident, augmentation-consistent labels. Both retain separate datasets and independently learned classifiers. Stable and Experimental remain human-reviewed decision profiles.

Manual cascades and the scheduled worker use the same foundation builder. Recording reservations and prospective holdouts remain excluded. Snapshot and release metadata report human and machine counts separately. Existing historical machine-only releases retain their original provenance; new releases explicitly describe the reviewed foundation. The live model is unchanged by shadow training.

Reviewed labels are the reference judgments, not objective proof of an unexplained event. Full training-set comparison measures fit; independent and future reviewed recordings remain necessary to measure generalization.

The initial reset discards old Machine-only generated crops and its collection pool. Historical run manifests remain provenance records, but discarded machine images cannot re-enter fitting. A reset timestamp rejects old frozen machine inputs. Collection pauses until a reviewed-only replacement has trained successfully, then starts afresh using that model. Human-reviewed crops and labels are retained.
