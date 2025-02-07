from tests.CLI_test.conftest import run_cmd


def test_exit(cli):
    out, err = run_cmd(cli, "exit")
    assert out == []
    assert err == []
