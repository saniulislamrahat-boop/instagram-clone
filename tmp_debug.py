from app import app, db
app.config.update(TESTING=True, SQLALCHEMY_DATABASE_URI='sqlite:///:memory:', SECRET_KEY='test-secret')
with app.app_context():
    db.drop_all()
    db.create_all()

client = app.test_client()
r = client.post('/register', data={'username':'tester','email':'tester@example.com','password':'secret123'})
print('register', r.status_code, r.headers.get('Location'))
print(r.get_data(as_text=True))
r2 = client.post('/login', data={'username':'tester','password':'secret123'}, follow_redirects=True)
print('login', r2.status_code, r2.headers.get('Location'))
print(r2.get_data(as_text=True))
