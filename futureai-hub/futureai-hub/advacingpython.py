import json 
class student :
    with open("advancing python/db.json",'r') as f :
     student_db = json.load(f)
    
    def __init__(self,name,age):
        self.name = name
        self.age = age
    
  
    def ask_name(self):
            for student in self.student_db:
                if len(student) > 0 and self.name == student[0]:
                    print("User already exists")
                    return

            with open("advancing python/db.json",'w') as f :
                  self.student_db.append([self.name, self.age])
                  json.dump(self.student_db,f)
                  print("Student added:", self.student_db)


name = input("enter you name " ,)
age = int(input("enter your age " , ))
e = student(name,age)
e.ask_name()