"""Class metadata determines roster membership; numbers never become authentication."""

from app.core.errors import require
from app.repositories.store import uid


def ensure_mock_identity(s, user_id, now):
    # Preserve existing identities and explicit revocations; create only missing metadata.
    if s.one(
        "SELECT id FROM external_identities WHERE user_id=:u AND platform='mock_zalo'", u=user_id
    ):
        return
    require(
        not s.one(
            "SELECT id FROM external_identities WHERE platform='mock_zalo' AND external_sender_id=:u",
            u=user_id,
        ),
        409,
        "identity_conflict",
        "Định danh giả lập đã thuộc tài khoản khác.",
    )
    s.insert(
        "external_identities",
        id=uid(),
        user_id=user_id,
        platform="mock_zalo",
        external_sender_id=user_id,
        created_at=now,
    )


def roster(s, class_id, active_only=False):
    condition = " AND e.status='active' AND u.is_active=1" if active_only else ""
    return s.all(
        "SELECT u.id,u.display_name,u.is_active,e.student_number,e.status,e.joined_at,c.username FROM enrollments e JOIN users u ON u.id=e.user_id LEFT JOIN user_credentials c ON c.user_id=u.id WHERE e.class_id=:c AND u.role='student'"
        + condition
        + " ORDER BY e.student_number",
        c=class_id,
    )


def ensure_roster(s, class_id, count, now):
    existing = s.one(
        "SELECT count(*) AS n,COALESCE(MAX(student_number),0) AS last FROM enrollments WHERE class_id=:c",
        c=class_id,
    )
    require(
        count >= existing["n"],
        409,
        "roster_shrink_denied",
        "Sĩ số nhỏ hơn danh sách hiện có; hãy quản lý trạng thái từng học viên.",
    )
    created = []
    for number in range(existing["last"] + 1, existing["last"] + 1 + count - existing["n"]):
        user_id = uid()
        s.insert(
            "users",
            id=user_id,
            display_name=f"Học viên {number}",
            role="student",
            created_at=now,
            updated_at=now,
        )
        s.insert("enrollments", user_id=user_id, class_id=class_id, joined_at=now, updated_at=now)
        s.insert(
            "external_identities",
            id=uid(),
            user_id=user_id,
            platform="mock_zalo",
            external_sender_id=user_id,
            created_at=now,
        )
        created.append(user_id)
    return created


def mock_catalog(s):
    result = []
    for group in s.all(
        "SELECT g.external_group_id,g.class_id,g.display_name,c.name AS class_name FROM group_bindings g JOIN classes c ON c.id=g.class_id WHERE g.platform='mock_zalo' AND g.is_active=1 AND c.status='active' ORDER BY c.name,g.id"
    ):
        group["students"] = [
            {
                "sender_id": r["external_sender_id"],
                "student_number": r["student_number"],
                "label": f"Học viên {r['student_number']}",
            }
            for r in s.all(
                "SELECT MIN(i.external_sender_id) AS external_sender_id,e.student_number FROM enrollments e JOIN users u ON u.id=e.user_id JOIN external_identities i ON i.user_id=u.id AND i.platform='mock_zalo' AND i.is_active=1 AND i.is_bot=0 WHERE e.class_id=:c AND e.status='active' AND u.is_active=1 AND u.role='student' GROUP BY e.user_id,e.student_number ORDER BY e.student_number",
                c=group["class_id"],
            )
        ]
        group["student_count"] = len(group["students"])
        result.append(group)
    return result
