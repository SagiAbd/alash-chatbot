import unittest

from app.api.api_v1.chat import _guest_chat_access_allowed
from app.models.chat import Chat


class ChatAccessTest(unittest.TestCase):
    def test_guest_chat_requires_matching_guest_token(self) -> None:
        chat = Chat(
            title="Public chat",
            user_id=None,
            is_public=True,
            guest_token="guest-token",
        )

        self.assertTrue(_guest_chat_access_allowed(chat, "guest-token"))
        self.assertFalse(_guest_chat_access_allowed(chat, "wrong-token"))
        self.assertFalse(_guest_chat_access_allowed(chat, None))

    def test_user_owned_chat_is_not_treated_as_guest_accessible(self) -> None:
        chat = Chat(
            title="User chat",
            user_id=7,
            is_public=False,
            guest_token="guest-token",
        )

        self.assertFalse(_guest_chat_access_allowed(chat, "guest-token"))


if __name__ == "__main__":
    unittest.main()
