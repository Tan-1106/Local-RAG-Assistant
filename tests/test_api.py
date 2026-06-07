"""Manual API smoke-test entry point.

Run this module directly after starting the backend. The implementation lives in
test_auth_session so pytest collection does not execute network requests.
"""


def main():
    from test_auth_session import main as run_e2e

    run_e2e()


if __name__ == "__main__":
    main()
