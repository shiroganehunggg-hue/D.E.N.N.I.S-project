import sys
sys.stdout.reconfigure(encoding="utf-8")
sys.stdin.reconfigure(encoding="utf-8")

from src.core.dennis import Dennis

def main():
    dennis = Dennis()

    print("=== DENNIS v1 ===")
    print("Type 'exit' to quit.\n")

    while True:
        prompt = input("You: ")

        if prompt.lower() == "exit":
            break

        answer = dennis.ask(prompt)

        print(f"DENNIS: {answer}\n")

if __name__ == "__main__":
    main()