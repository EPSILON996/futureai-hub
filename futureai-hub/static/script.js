window.onload = fetchStudents;

document.getElementById('studentForm').onsubmit = async function(e) {
    e.preventDefault();
    const name  = document.getElementById('name').value.trim();
    const email = document.getElementById('email').value.trim().toLowerCase();
    const age   = parseInt(document.getElementById('age').value);

    const resultDiv = document.getElementById('result');
    resultDiv.textContent = '';

    if (!name || !email || !age) {
        resultDiv.textContent = "All fields are required!";
        resultDiv.style.color = 'red';
        return;
    }

    const resp = await fetch('/add_student', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ name, email, age }),
    });
    const data = await resp.json();
    if (data.success) {
        resultDiv.textContent = data.message;
        resultDiv.style.color = 'green';
        fetchStudents();
        document.getElementById('studentForm').reset();
    } else {
        resultDiv.textContent = data.message;
        resultDiv.style.color = 'red';
    }
};

async function fetchStudents() {
    const resp = await fetch('/list_students');
    const students = await resp.json();
    const tbody = document.querySelector('#studentsTable tbody');
    tbody.innerHTML = '';
    for (const student of students) {
        const tr = document.createElement('tr');
        tr.innerHTML = `<td>${student.name}</td>
                        <td>${student.email}</td>
                        <td>${student.age}</td>
                        <td>${student.registration_date}</td>
                        <td><button onclick="deleteStudent('${student.email.replace(/'/g, "\\'")}')">Delete</button></td>`;
        tbody.appendChild(tr);
    }
}

async function deleteStudent(email) {
    if (!confirm("Are you sure you want to delete this student?")) return;
    const resp = await fetch('/delete_student', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ email })
    });
    const data = await resp.json();
    const resultDiv = document.getElementById('result');
    if (data.success) {
        resultDiv.textContent = data.message;
        resultDiv.style.color = 'green';
        fetchStudents();
    } else {
        resultDiv.textContent = data.message;
        resultDiv.style.color = 'red';
    }
}
// Simple confirmation for deletions
function confirmDelete() {
  return confirm("Are you sure you want to delete this student?");
}

