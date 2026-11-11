-- Stable student numbers are scoped to a class; login sessions may be class-scoped.
BEGIN IMMEDIATE;
ALTER TABLE enrollments ADD COLUMN student_number INTEGER CHECK (student_number > 0);
WITH numbered AS (
 SELECT user_id,class_id,ROW_NUMBER() OVER(PARTITION BY class_id ORDER BY joined_at,user_id) AS n FROM enrollments
)
UPDATE enrollments SET student_number=(SELECT n FROM numbered n WHERE n.user_id=enrollments.user_id AND n.class_id=enrollments.class_id);
CREATE UNIQUE INDEX ux_enrollment_class_number ON enrollments(class_id,student_number);
CREATE TRIGGER tr_assign_student_number AFTER INSERT ON enrollments
WHEN NEW.student_number IS NULL
BEGIN
 UPDATE enrollments SET student_number=(SELECT COALESCE(MAX(student_number),0)+1 FROM enrollments WHERE class_id=NEW.class_id)
 WHERE user_id=NEW.user_id AND class_id=NEW.class_id;
END;
CREATE TRIGGER tr_student_number_immutable BEFORE UPDATE OF student_number ON enrollments
WHEN OLD.student_number IS NOT NULL AND NEW.student_number IS NOT OLD.student_number
BEGIN SELECT RAISE(ABORT,'student_number is immutable'); END;
ALTER TABLE auth_sessions ADD COLUMN class_id TEXT REFERENCES classes(id);
PRAGMA user_version=3;
COMMIT;
