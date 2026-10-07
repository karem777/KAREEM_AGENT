from core.runner import AgentRunner
from prompt_toolkit import prompt


def main():
    runner = AgentRunner("workspace")

    print()
    print("=" * 55)
    print("KAREEM AGENT")
    print("=" * 55)
    print("Local AI Agent | Qwen3 8B")
    print("Type 'exit' to stop.")
    print()

    while True:
        try:
            user_input = prompt("You > ").strip()

            if not user_input:
                continue

            if user_input.lower() in ["exit", "quit", "خروج"]:
                print("Agent stopped.")
                break

            result = runner.run(user_input)

            if isinstance(result, str):
                print("\nAgent >", result)

            print()

        except KeyboardInterrupt:
            print("\nAgent stopped.")
            break

        except Exception as e:
            print("\nERROR:", e)
            print()


if __name__ == "__main__":
    main()