from sqlalchemy import String, Integer, BigInteger, Text, Boolean, JSON, ForeignKey, UniqueConstraint, Index
from sqlalchemy.orm import Mapped, mapped_column
from .db import Base, utcnow


class Config(Base):
    __tablename__ = 'config'
    key: Mapped[str] = mapped_column(String(100), primary_key=True)
    value: Mapped[dict] = mapped_column(JSON, default=dict)


class Batch(Base):
    __tablename__ = 'batches'
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    source: Mapped[str] = mapped_column(String(20), default='desktop')
    session_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    created_at: Mapped[str] = mapped_column(String(40), default=utcnow)


class ImageRecord(Base):
    __tablename__ = 'images'
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    batch_id: Mapped[str] = mapped_column(ForeignKey('batches.id'))
    filename: Mapped[str] = mapped_column(String(500))
    sha256: Mapped[str] = mapped_column(String(64), index=True)
    path: Mapped[str] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(30), default='queued', index=True)
    text: Mapped[str] = mapped_column(Text, default='')
    regions: Mapped[list] = mapped_column(JSON, default=list)
    candidates: Mapped[list] = mapped_column(JSON, default=list)
    error: Mapped[str] = mapped_column(Text, default='')
    created_at: Mapped[str] = mapped_column(String(40), default=utcnow)


class ImageResearch(Base):
    __tablename__ = 'image_research'
    image_id: Mapped[str] = mapped_column(ForeignKey('images.id'), primary_key=True)
    job_id: Mapped[str] = mapped_column(String(36))
    status: Mapped[str] = mapped_column(String(20), default='queued')
    stage: Mapped[str] = mapped_column(String(200), default='等待项目研究智能体')
    report: Mapped[dict] = mapped_column(JSON, default=dict)
    error: Mapped[str] = mapped_column(Text, default='')
    updated_at: Mapped[str] = mapped_column(String(40), default=utcnow)


class Repository(Base):
    __tablename__ = 'repositories'
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=False)
    full_name: Mapped[str] = mapped_column(String(300), index=True)
    description: Mapped[str] = mapped_column(Text, default='')
    language: Mapped[str] = mapped_column(String(100), default='')
    stars: Mapped[int] = mapped_column(Integer, default=0)
    forks: Mapped[int] = mapped_column(Integer, default=0)
    archived: Mapped[bool] = mapped_column(Boolean, default=False)
    collected: Mapped[bool] = mapped_column(Boolean, default=False, index=True)
    favorite: Mapped[bool] = mapped_column(Boolean, default=False)
    tags: Mapped[list] = mapped_column(JSON, default=list)
    notes: Mapped[str] = mapped_column(Text, default='')
    study_status: Mapped[str] = mapped_column(String(30), default='待研究')
    metadata_json: Mapped[dict] = mapped_column(JSON, default=dict)
    summary: Mapped[dict] = mapped_column(JSON, default=dict)
    readme: Mapped[str] = mapped_column(Text, default='')
    fetched_at: Mapped[str] = mapped_column(String(40), default=utcnow)
    created_at: Mapped[str] = mapped_column(String(40), default=utcnow)


class ProjectTrash(Base):
    __tablename__ = 'project_trash'
    repo_id: Mapped[int] = mapped_column(ForeignKey('repositories.id'), primary_key=True)
    trashed_at: Mapped[str] = mapped_column(String(40), default=utcnow)


class ProjectOrganization(Base):
    __tablename__ = 'project_organization'
    repo_id: Mapped[int] = mapped_column(ForeignKey('repositories.id'), primary_key=True)
    categories: Mapped[list] = mapped_column(JSON, default=list)
    keywords: Mapped[list] = mapped_column(JSON, default=list)
    method: Mapped[str] = mapped_column(String(20), default='rules')
    updated_at: Mapped[str] = mapped_column(String(40), default=utcnow)


class ImageLink(Base):
    __tablename__ = 'image_links'
    __table_args__ = (UniqueConstraint('image_id', 'repo_id'),)
    id: Mapped[int] = mapped_column(primary_key=True)
    image_id: Mapped[str] = mapped_column(ForeignKey('images.id'))
    repo_id: Mapped[int] = mapped_column(ForeignKey('repositories.id'))


class Job(Base):
    __tablename__ = 'jobs'
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    kind: Mapped[str] = mapped_column(String(40))
    payload: Mapped[dict] = mapped_column(JSON, default=dict)
    status: Mapped[str] = mapped_column(String(20), default='queued', index=True)
    stage: Mapped[str] = mapped_column(String(100), default='等待处理')
    attempts: Mapped[int] = mapped_column(Integer, default=0)
    error: Mapped[str] = mapped_column(Text, default='')
    available_at: Mapped[str] = mapped_column(String(40), default=utcnow)
    created_at: Mapped[str] = mapped_column(String(40), default=utcnow)
    finished_at: Mapped[str | None] = mapped_column(String(40), nullable=True)


class UploadSession(Base):
    __tablename__ = 'upload_sessions'
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    token_hash: Mapped[str] = mapped_column(String(64), unique=True)
    credential_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)
    expires_at: Mapped[str] = mapped_column(String(40))
    revoked: Mapped[bool] = mapped_column(Boolean, default=False)
    file_count: Mapped[int] = mapped_column(Integer, default=0)
    byte_count: Mapped[int] = mapped_column(Integer, default=0)


class Snapshot(Base):
    __tablename__ = 'snapshots'
    __table_args__ = (UniqueConstraint('repo_id', 'date'),)
    id: Mapped[int] = mapped_column(primary_key=True)
    repo_id: Mapped[int] = mapped_column(ForeignKey('repositories.id'), index=True)
    date: Mapped[str] = mapped_column(String(10))
    stars: Mapped[int] = mapped_column(Integer)
    sampled_at: Mapped[str] = mapped_column(String(40), default=utcnow)


PERFORMANCE_INDEXES = (
    Index('ix_jobs_ready', Job.status, Job.available_at, Job.created_at),
    Index('ix_images_batch_created', ImageRecord.batch_id, ImageRecord.created_at),
    Index('ix_image_links_repository', ImageLink.repo_id),
)
