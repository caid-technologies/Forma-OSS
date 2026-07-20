from __future__ import annotations

import unittest

from blueprint_core import database


class UserCreditTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        database.init_db()

    def test_credit_balance_defaults_to_zero(self) -> None:
        balance = database.get_user_credit_balance("credit_default_user")

        payload = database.user_credit_balance_public_payload(balance)
        self.assertEqual(0, payload["credit_balance"])

    def test_add_user_credits_records_transaction_and_balance(self) -> None:
        owner_user_id = "credit_add_user"

        transaction = database.add_user_credits(
            owner_user_id,
            credit_delta=125,
            source="unit_test",
            metadata={"note": "test"},
        )
        balance = database.get_user_credit_balance(owner_user_id)

        self.assertEqual(125, transaction.credit_delta)
        self.assertGreaterEqual(balance.credit_balance, 125)

    def test_stripe_checkout_session_is_idempotent(self) -> None:
        owner_user_id = "credit_idempotent_user"
        session_id = "cs_test_credit_idempotent"

        first = database.add_user_credits(
            owner_user_id,
            credit_delta=100,
            source="stripe_checkout",
            stripe_checkout_session_id=session_id,
        )
        second = database.add_user_credits(
            owner_user_id,
            credit_delta=100,
            source="stripe_checkout",
            stripe_checkout_session_id=session_id,
        )
        balance = database.get_user_credit_balance(owner_user_id)

        self.assertEqual(first.stripe_checkout_session_id, second.stripe_checkout_session_id)
        self.assertEqual(100, balance.credit_balance)


if __name__ == "__main__":
    unittest.main()
