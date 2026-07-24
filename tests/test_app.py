import unittest

from app import app, db, User, Post, Reaction, Message, Follow, FriendRequest, Story


class AuthFlowTests(unittest.TestCase):
    def setUp(self):
        app.config.update(
            TESTING=True,
            SQLALCHEMY_DATABASE_URI="sqlite:///:memory:",
            SECRET_KEY="test-secret",
        )
        self.client = app.test_client()
        with app.app_context():
            db.drop_all()
            db.create_all()

    def test_register_login_profile_logout(self):
        register_response = self.client.post(
            "/register",
            data={
                "username": "tester",
                "email": "tester@example.com",
                "password": "secret123",
            },
            follow_redirects=True,
        )
        self.assertEqual(register_response.status_code, 200)

        login_response = self.client.post(
            "/login",
            data={
                "username": "tester",
                "password": "secret123",
            },
            follow_redirects=True,
        )
        self.assertEqual(login_response.status_code, 200)
        self.assertIn("Welcome tester", login_response.get_data(as_text=True))

        profile_response = self.client.get("/profile")
        self.assertEqual(profile_response.status_code, 200)
        self.assertIn("Welcome tester", profile_response.get_data(as_text=True))

        logout_response = self.client.get("/logout", follow_redirects=True)
        self.assertEqual(logout_response.status_code, 200)
        self.assertIn("Login", logout_response.get_data(as_text=True))

    def test_reactions_and_messages(self):
        with app.app_context():
            first = User(username="first", email="first@example.com", password="x")
            second = User(username="second", email="second@example.com", password="x")
            db.session.add_all([first, second])
            db.session.commit()
            post = Post(user_id=second.id, image_filename="photo.jpg")
            db.session.add(post)
            db.session.commit()
            first_id, second_id, post_id = first.id, second.id, post.id
        with self.client:
            self.client.post("/login", data={"username": "first", "password": "x"})
            # Authenticate directly because test users use a lightweight password value.
            with self.client.session_transaction() as session:
                session["_user_id"] = str(first_id)
                session["_fresh"] = True
            self.client.post(f"/post/{post_id}/reaction", data={"reaction_type": "love"})
            response = self.client.post(f"/api/messages/{second_id}", data={"body": "Hello!"})
            self.assertEqual(response.status_code, 201)
        with app.app_context():
            self.assertEqual(Reaction.query.one().reaction_type, "love")
            self.assertEqual(Message.query.one().body, "Hello!")

    def test_follow_and_friend_request(self):
        with app.app_context():
            first = User(username="first", email="first@example.com", password="x")
            second = User(username="second", email="second@example.com", password="x")
            db.session.add_all([first, second])
            db.session.commit()
            first_id, second_id = first.id, second.id
        with self.client:
            with self.client.session_transaction() as session:
                session["_user_id"] = str(first_id)
                session["_fresh"] = True
            self.client.post(f"/follow/{second_id}")
            self.client.post(f"/friend/{second_id}")
        with app.app_context():
            self.assertEqual(Follow.query.one().followed_id, second_id)
            self.assertEqual(FriendRequest.query.one().status, "pending")


if __name__ == "__main__":
    unittest.main()
