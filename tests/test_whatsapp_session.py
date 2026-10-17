from io import BytesIO
from urllib.error import HTTPError
from unittest.mock import MagicMock

from app.adapters.whatsapp_session import run_session


def command(identifier="m1", text="!vou"):
    return {"message_id": identifier, "player_id": "+550000000000", "text": text}


def setup(actions, messages, **overrides):
    arguments = dict(
        initial_ids={"history"}, group_id="test", api_url="http://localhost:8001",
        api_key="", inspect_message=MagicMock(side_effect=messages),
        deliver=MagicMock(return_value="Resposta"),
        read=MagicMock(side_effect=actions), read_key=MagicMock(return_value="secret"),
        output=MagicMock(),
    )
    arguments.update(overrides)
    return arguments


def test_multiple_commands_share_key_and_ignore_processed_ids():
    args = setup(["", "", "/sair"], [command(), command("m2", "!lista")])
    seen = []

    def inspect(ignored):
        seen.append(set(ignored))
        return command("m1" if len(seen) == 1 else "m2")

    args["inspect_message"].side_effect = inspect
    run_session(**args)
    assert seen == [{"history"}, {"history", "m1"}]
    assert args["read_key"].call_count == 1
    assert args["deliver"].call_count == 2
    assert args["deliver"].call_args.args[2]["group_id"] == "test"


def test_network_retry_preserves_message_and_identity():
    args = setup(["", "", "/sair"], [command()])
    args["deliver"].side_effect = [TimeoutError("offline"), "Resposta"]
    run_session(**args)
    assert args["inspect_message"].call_count == 1
    assert args["deliver"].call_args_list[0] == args["deliver"].call_args_list[1]
    args["read_key"].assert_called_once()


def test_unauthorized_key_can_be_corrected_without_reidentifying():
    args = setup(["", "", "/sair"], [command()], api_key="wrong")
    args["deliver"].side_effect = [
        HTTPError("http://localhost/messages", 401, "Unauthorized", {}, BytesIO(b'{}')),
        "Resposta",
    ]
    run_session(**args)
    assert args["deliver"].call_args_list[0].args[1] == "wrong"
    assert args["deliver"].call_args_list[1].args[1] == "secret"
    args["inspect_message"].assert_called_once()


def test_sending_retry_does_not_repeat_api_command():
    sender = MagicMock(side_effect=[ValueError("painel aberto"), "Enter enviado"])
    args = setup(["", "", "", "", "/sair"], [command()], send_response=sender)
    run_session(**args)
    args["deliver"].assert_called_once()
    args["inspect_message"].assert_called_once()
    assert sender.call_count == 2
    assert sender.call_args_list[0] == sender.call_args_list[1]


def test_no_message_keeps_session_open():
    args = setup(["", "", "/sair"], [None, command()])
    run_session(**args)
    assert args["inspect_message"].call_count == 2
    args["deliver"].assert_called_once()


def test_skip_response_does_not_send_or_undo_api_processing():
    sender = MagicMock()
    args = setup(["", "/pular", "/sair"], [command()], send_response=sender)
    run_session(**args)
    args["deliver"].assert_called_once()
    sender.assert_not_called()


def test_skip_failed_command_allows_next_command():
    args = setup(["", "/pular", "", "/sair"], [command(), command("m2")])
    args["deliver"].side_effect = [TimeoutError("offline"), "Resposta"]
    run_session(**args)
    assert args["inspect_message"].call_count == 2
    assert args["deliver"].call_args.args[2]["message_id"] == "m2"


def test_identification_failure_does_not_close_session():
    args = setup(["", "", "/sair"], [ValueError("grupo errado"), command()], browser_errors=(ValueError,))
    run_session(**args)
    args["deliver"].assert_called_once()


def test_watch_processes_messages_without_prompting_for_arrival():
    waiter = MagicMock(side_effect=[True, True, False])
    args = setup([], [command(), command("m2")], wait_for_message=waiter)
    run_session(**args)
    assert args["deliver"].call_count == 2
    args["read"].assert_not_called()


def test_watch_keeps_manual_confirmation_before_sending():
    waiter = MagicMock(side_effect=[True, False])
    sender = MagicMock(return_value="Enter enviado")
    args = setup([""], [command()], wait_for_message=waiter, send_response=sender)
    run_session(**args)
    sender.assert_called_once()
    assert "para enviar" in args["read"].call_args.args[0]


def test_watch_error_requires_operator_before_resuming():
    waiter = MagicMock(side_effect=ValueError("painel aberto"))
    args = setup(["/sair"], [], wait_for_message=waiter, browser_errors=(ValueError,))
    run_session(**args)
    args["deliver"].assert_not_called()
    args["inspect_message"].assert_not_called()


def test_watch_does_not_loop_without_input_after_cancelled_identification():
    args = setup(["/sair"], [None], wait_for_message=MagicMock(return_value=True))
    run_session(**args)
    args["inspect_message"].assert_called_once()
    args["deliver"].assert_not_called()
