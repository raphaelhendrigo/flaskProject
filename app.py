from flask import Flask, render_template, request, redirect, url_for
from flask_sqlalchemy import SQLAlchemy
from flask import Flask


import os

if os.environ.get('DATABASE_URL'):
    SQLALCHEMY_DATABASE_URI = os.environ.get('DATABASE_URL').replace("://", "ql://", 1)
else:
    SQLALCHEMY_DATABASE_URI = 'sqlite:///your-local-sqlite-database.db'

app = Flask(__name__)

app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///C:/Users/rapha/PycharmProjects/flaskProject/students.db'
db = SQLAlchemy(app)

class Student(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(50), nullable=False)
    grade1 = db.Column(db.Float, nullable=False)
    grade2 = db.Column(db.Float, nullable=False)
    grade3 = db.Column(db.Float, nullable=False)
    grade4 = db.Column(db.Float, nullable=False)

    @property
    def average(self):
        return (self.grade1 + self.grade2 + self.grade3 + self.grade4) / 4
@app.route('/', methods=['GET', 'POST'])
def index():
    if request.method == 'POST':
        name = request.form['name']
        grade1 = float(request.form['grade1'])
        grade2 = float(request.form['grade2'])
        grade3 = float(request.form['grade3'])
        grade4 = float(request.form['grade4'])

        new_student = Student(name=name, grade1=grade1, grade2=grade2, grade3=grade3, grade4=grade4)

        db.session.add(new_student)
        db.session.commit()

        return redirect(url_for('index'))

    students = Student.query.all()
    return render_template('index.html', students=students)

@app.route('/edit/<id>', methods=['GET'])
def edit(id):
    student = Student.query.get(id)
    return render_template('edit.html', student=student)

@app.route('/update/<id>', methods=['POST'])
def update(id):
    student = Student.query.get(id)
    student.name = request.form['name']
    student.grade1 = request.form['grade1']
    student.grade2 = request.form['grade2']
    student.grade3 = request.form['grade3']
    student.grade4 = request.form['grade4']
    db.session.commit()
    return redirect(url_for('index'))

@app.route('/delete/<id>', methods=['POST'])
def delete(id):
    student = Student.query.get(id)
    db.session.delete(student)
    db.session.commit()
    return redirect(url_for('index'))

if __name__ == '__main__':
    db.create_all()
    app.run(debug=True)
