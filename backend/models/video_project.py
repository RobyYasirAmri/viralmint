# SPDX-License-Identifier: AGPL-3.0-only
# Copyright (c) 2025-2026 ViralMint Contributors
"""VideoProject — a Smart Video Studio project.

The project IS its document: `doc_json` holds the scene list with bound voice
takes and visuals, validated by services/studio_doc.py and edited only through
services/studio_ops.py under optimistic concurrency (`revision`).

`assets_json` holds the files the project owns (uploaded clips and stills),
indexed by asset id. It lives OUTSIDE the document on purpose: undo restores
document snapshots, and a snapshot must never be able to forge a reference to
a file the project doesn't have. Keeping it in the row (not a side file) means
an upload is recorded in the same transaction as the revision bump.
"""
from datetime import datetime
from uuid import uuid4

from sqlalchemy import Column, DateTime, Float, Integer, String, Text

from backend.database import Base


class VideoProject(Base):
    __tablename__ = "video_projects"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid4()))
    user_id = Column(String(36), default="local", index=True)  # cloud-sync hook — keep on every model

    title = Column(Text, nullable=False, default="Untitled video")
    status = Column(String(20), nullable=False, default="draft")      # studio_doc.PROJECT_STATUSES
    aspect_ratio = Column(String(10), nullable=False, default="9:16")  # denormalised for the Home list

    doc_json = Column(Text, nullable=False)
    assets_json = Column(Text, nullable=False, default="{}")
    revision = Column(Integer, nullable=False, default=1)

    thumbnail_path = Column(Text, nullable=True)
    last_video_id = Column(String(36), nullable=True)
    duration_seconds = Column(Float, nullable=True)
    # Denormalised for the Home list (so it needn't parse every document);
    # written with every document write.
    scene_count = Column(Integer, nullable=True)
    visual_style = Column(String(40), nullable=True)

    created_at = Column(DateTime, default=datetime.utcnow, index=True)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, index=True)
