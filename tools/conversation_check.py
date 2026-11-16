"""Live local-only follow-up check using a fictional word and disposable chat history."""
import json
import tempfile
from pathlib import Path

from macooii.engine import Engine
from macooii.privacy import TaskContext
from macooii.storage import Store


def main():
    with tempfile.TemporaryDirectory(prefix="macooii-conversation-check-") as directory:
        store = Store(Path(directory))
        store.set_setting("provider", "local")
        engine = Engine(store, lambda: "")
        answers = []
        for request in ["My fictional test code word is papaya. Acknowledge briefly.",
                        "What test code word did I just give you? Reply with only the word."]:
            message_id = store.add_message("user", request, True)
            task = TaskContext(lambda *args: "decline", current_message_id=message_id)
            answer = engine.run(request, task, lambda stage: None)
            store.add_message("assistant", answer.text, answer.sensitive)
            answers.append(answer.text)
        passed = "papaya" in answers[-1].casefold()
        print(json.dumps({"passed": passed, "answers": answers}, ensure_ascii=True), flush=True)
        return 0 if passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
