"""Регресія: CarrierAccount.credentials має зберігатися зашифрованим (Fernet),
а не як відкритий JSON, і прозоро розшифровуватись назад через властивість."""
from extensions import db
from models.shipping import CarrierAccount


def test_credentials_stored_encrypted_and_roundtrip(app, default_store):
    with app.app_context():
        account = CarrierAccount(store_id=default_store.id, carrier="dhl", is_enabled=True, is_sandbox=True)
        account.credentials = {"api_key": "secret-key-value", "api_secret": "secret2", "account_number": "123"}
        db.session.add(account)
        db.session.commit()
        account_id = account.id

        raw_blob = account._credentials_encrypted
        assert "secret-key-value" not in raw_blob  # не лежить у відкритому вигляді в БД

        db.session.expire(account)
        reloaded = db.session.get(CarrierAccount, account_id)
        assert reloaded.credentials == {
            "api_key": "secret-key-value",
            "api_secret": "secret2",
            "account_number": "123",
        }

        db.session.delete(reloaded)
        db.session.commit()


def test_is_test_mode_detection(app, default_store):
    with app.app_context():
        account = CarrierAccount(store_id=default_store.id, carrier="ups", is_enabled=True, is_sandbox=True)
        account.credentials = {"client_id": "test", "client_secret": "test", "account_number": "test"}
        db.session.add(account)
        db.session.commit()

        assert account.is_test_mode is True

        account.credentials = {"client_id": "real-value", "client_secret": "test", "account_number": "test"}
        db.session.commit()
        assert account.is_test_mode is False

        db.session.delete(account)
        db.session.commit()
