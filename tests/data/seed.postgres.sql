INSERT INTO students (name, city, major, gpa) VALUES
    ('Alice Johnson', 'Seattle', 'Computer Science', 3.8),
    ('Brian Smith', 'Austin', 'Data Science', 3.5),
    ('Clara Lee', 'Boston', 'Mathematics', 3.9),
    ('Daniel Green', 'Denver', 'Computer Science', 3.2),
    ('Emily Davis', 'Chicago', 'Physics', 3.7),
    ('Frank Moore', 'New York', 'Economics', 3.4);

INSERT INTO courses (code, title, instructor, credits) VALUES
    ('CS101', 'Introduction to Programming', 'Laura Chen', 4),
    ('DS201', 'Data Analytics', 'Marcus Hill', 3),
    ('MA210', 'Linear Algebra', 'Sophie Turner', 4),
    ('PH105', 'Modern Physics', 'Isaac Brown', 4),
    ('CS205', 'Database Systems', 'Caroline King', 3);

INSERT INTO enrollments (student_id, course_id, grade) VALUES
    (1, 1, 'A'),
    (1, 5, 'A-'),
    (2, 2, 'B+'),
    (2, 5, 'A'),
    (3, 3, 'A'),
    (4, 1, 'B'),
    (4, 5, 'B+'),
    (5, 4, 'A-'),
    (6, 2, 'B'),
    (6, 3, 'B+');
