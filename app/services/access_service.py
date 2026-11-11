from app.core.errors import require


def class_ids(s, user):
    if user["role"] == "admin":
        return {r["id"] for r in s.all("SELECT id FROM classes WHERE status='active'")}
    if user["role"] == "teacher":
        return {
            r["class_id"]
            for r in s.all(
                "SELECT a.class_id FROM teacher_assignments a JOIN classes c ON c.id=a.class_id WHERE a.teacher_id=:u AND a.is_active=1 AND c.status='active'",
                u=user["id"],
            )
        }
    if user["role"] == "student":
        return {
            r["class_id"]
            for r in s.all(
                "SELECT e.class_id FROM enrollments e JOIN classes c ON c.id=e.class_id WHERE e.user_id=:u AND e.status='active' AND c.status='active' AND (:sc IS NULL OR e.class_id=:sc)",
                u=user["id"],
                sc=user.get("session_class_id"),
            )
        }
    return set()


def check_class(s, user, cid):
    require(
        s.one("SELECT id FROM classes WHERE id=:c", c=cid), 404, "not_found", "Không tìm thấy lớp."
    )
    require(cid in class_ids(s, user))


def check_scope(s, user, scope):
    require(user["role"] in {"teacher", "admin"})
    target = s.one("SELECT * FROM access_scopes WHERE id=:id", id=scope)
    require(target is not None, 422, "invalid_scope", "Phạm vi không tồn tại.")
    if user["role"] == "admin":
        return
    allowed = class_ids(s, user)
    if target["scope_type"] == "class":
        require(target["class_id"] in allowed)
    else:
        affected = {
            r["id"]
            for r in s.all(
                "SELECT id FROM classes WHERE course_id=:c AND status='active'",
                c=target["course_id"],
            )
        }
        require(bool(affected) and affected.issubset(allowed))


def document_scopes(s, did):
    return [
        r["scope_id"]
        for r in s.all("SELECT scope_id FROM document_access WHERE document_id=:d", d=did)
    ]


def check_document(s, user, did):
    doc = s.one("SELECT * FROM documents WHERE id=:d", d=did)
    require(doc is not None, 404, "not_found", "Không tìm thấy tài liệu.")
    scopes = document_scopes(s, did)
    require(bool(scopes) or user["role"] == "admin")
    for scope in scopes:
        check_scope(s, user, scope)
    return doc


def allowed_sources(s, cid):
    cls = s.one("SELECT course_id FROM classes WHERE id=:c", c=cid)
    scopes = ["class:" + cid, "course:" + cls["course_id"]]
    versions = [
        r["active_version_id"]
        for r in s.all(
            "SELECT DISTINCT d.active_version_id FROM documents d JOIN document_access a ON a.document_id=d.id WHERE d.status='active' AND a.scope_id IN (:s1,:s2)",
            s1=scopes[0],
            s2=scopes[1],
        )
    ]
    return scopes, versions
