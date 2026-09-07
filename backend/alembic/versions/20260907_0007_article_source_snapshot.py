"""Freeze article source evidence across later reanalysis."""
from alembic import op
import sqlalchemy as sa
import json

revision = "20260907_0007"
down_revision = "20260827_0006"
branch_labels = None
depends_on = None


def upgrade():
    columns = {c["name"] for c in sa.inspect(op.get_bind()).get_columns("article_versions")}
    if "source_snapshot" not in columns:
        op.add_column("article_versions", sa.Column("source_snapshot", sa.JSON(), nullable=False, server_default="{}"))
    bind = op.get_bind()
    versions = bind.execute(sa.text("SELECT v.id, d.question_id FROM article_versions v JOIN article_drafts d ON v.draft_id=d.id WHERE v.source_snapshot='{}'")).mappings().all()
    for version in versions:
        answers = bind.execute(sa.text("SELECT id, author_name, answer_url, plain_content, content_hash FROM answers WHERE question_id=:q"), {"q": version["question_id"]}).mappings().all()
        clusters = bind.execute(sa.text("SELECT id, name, summary FROM claim_clusters WHERE question_id=:q"), {"q": version["question_id"]}).mappings().all()
        sources = bind.execute(sa.text("SELECT paragraph_id, answer_id, cluster_id FROM article_paragraph_sources WHERE article_version_id=:v"), {"v": version["id"]}).mappings().all()
        paragraphs = {}
        for source in sources:
            paragraph = paragraphs.setdefault(source["paragraph_id"], {"paragraph_id": source["paragraph_id"], "source_answer_ids": [], "cluster_ids": []})
            if source["answer_id"]:
                paragraph["source_answer_ids"].append(source["answer_id"])
            if source["cluster_id"]:
                paragraph["cluster_ids"].append(source["cluster_id"])
        snapshot = {"legacy_snapshot": True, "answers": {a["id"]: {"id": a["id"], "author": a["author_name"], "url": a["answer_url"], "content": a["plain_content"], "hash": a["content_hash"]} for a in answers}, "clusters": [dict(c) for c in clusters], "paragraphs": list(paragraphs.values())}
        bind.execute(sa.text("UPDATE article_versions SET source_snapshot=:snapshot WHERE id=:v"), {"v": version["id"], "snapshot": json.dumps(snapshot, ensure_ascii=False)})


def downgrade():
    op.drop_column("article_versions", "source_snapshot")
