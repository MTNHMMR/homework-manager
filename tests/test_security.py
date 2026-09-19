from app.security import hash_password, verify_password


def test_verify_password_accepts_correct_password():
    hashed = hash_password("correct horse battery staple")
    assert verify_password("correct horse battery staple", hashed)


def test_verify_password_rejects_wrong_password():
    hashed = hash_password("correct horse battery staple")
    assert not verify_password("wrong password", hashed)


def test_hash_password_does_not_return_plaintext():
    hashed = hash_password("my-password")
    assert hashed != "my-password"
