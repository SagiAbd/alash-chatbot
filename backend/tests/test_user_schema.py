import unittest
from datetime import datetime, timezone

from app.models.user import User
from app.schemas.user import UserResponse


class UserSchemaTest(unittest.TestCase):
    def test_user_response_defaults_to_local_auth_provider(self) -> None:
        user = User(
            email="user@example.com",
            username="user",
            hashed_password="hashed",
            is_active=True,
            is_superuser=False,
        )
        user.id = 1
        user.created_at = datetime.now(timezone.utc)
        user.updated_at = user.created_at

        response = UserResponse.model_validate(user)

        self.assertEqual(response.auth_provider, "local")


if __name__ == "__main__":
    unittest.main()
