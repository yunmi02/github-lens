"""Keep screenshot review state consistent with saved repository links."""
from .models import ImageRecord, ImageLink, ImageResearch, Repository, Job


def update_review_status(db, image):
    db.flush()
    linked = db.query(Repository).join(ImageLink, ImageLink.repo_id == Repository.id).filter(ImageLink.image_id == image.id).all()
    names = {repo.full_name.lower(): repo.full_name for repo in linked}
    candidates = [{**c, 'confirmed': c['full_name'].lower() in names} for c in image.candidates]
    existing = {c['full_name'].lower() for c in candidates}
    for key, name in names.items():
        if key not in existing:
            candidates.append({'full_name': name, 'confirmed': True, 'evidence': '已确认并关联的项目'})
    image.candidates = candidates
    image.status = 'completed' if linked else 'needs_review'
    research = db.get(ImageResearch, image.id)
    if linked and research and research.status == 'completed':
        research.stage = '研究完成，已关联项目'


def repair_linked_reviews(db):
    """Repair old pending rows without interrupting active screenshot jobs."""
    active = {job.payload.get('image_id') for job in db.query(Job).filter(Job.status.in_(['queued', 'running', 'waiting_browser', 'browser_running']))}
    images = db.query(ImageRecord).filter(
        ImageRecord.status.in_(['needs_review', 'failed']),
        ImageRecord.id.in_(db.query(ImageLink.image_id)),
    ).all()
    repaired = 0
    for image in images:
        if image.id not in active:
            update_review_status(db, image)
            image.error = ''
            repaired += 1
    return repaired
