# Approved recovered-evidence publication

When the complete session is irretrievable, an operator may approve the surviving evidence as the final archival record. This is never inferred from missing files. A `recovery-publication.json` must explicitly identify the session, set `operator_approved: true`, `scope: surviving_evidence`, and `full_session_available: false`, and supply the SHA-256 of immutable `recovery-original.mp4`.

The normal human-reviewed anomalous decision, annotated video, reviewed still pairs, checksums, and public download verification remain required. The public description discloses the missing full session. Recovery crops, original segments, and contextual recordings are included only from explicit evidence directories. Publication priority uses the operator approval time.

Prepare `video.mp4`, `video-annotated.mp4`, and indexed still pairs from the preserved excerpt, keeping annotations tied to its actual frames. Keep original-session metadata and exact coverage in the recovery manifest. Mark completion only after the normal publisher verifies every file. Do not fabricate missing footage, remove human labels, or overwrite the full-session manifest to imply a complete recording.
