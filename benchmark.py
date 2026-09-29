import time

from src.providers.provider_factory import ProviderFactory


TEST_MESSAGES = [
    {
        "role": "user",
        "content": "Reply with exactly one word: Hello"
    }
]


def benchmark():

    providers = ProviderFactory.create_all()

    print("=" * 80)
    print("DENNIS Provider Benchmark")
    print("=" * 80)

    results = []

    for provider in providers:

        name = type(provider).__name__

        print(f"\nTesting {name}...")

        start = time.perf_counter()

        try:

            result = provider.generate(TEST_MESSAGES)

            elapsed = time.perf_counter() - start

            if result.success:

                status = "SUCCESS"
                reply = result.content

            else:

                status = "FAILED"
                reply = result.error

            print(f"Status : {status}")
            print(f"Time   : {elapsed:.2f} s")
            print(f"Reply  : {repr(reply)[:120]}")

            results.append(
                (
                    name,
                    status,
                    elapsed,
                )
            )

        except Exception as exc:

            elapsed = time.perf_counter() - start

            print(f"Status : EXCEPTION")
            print(f"Time   : {elapsed:.2f} s")
            print(exc)

            results.append(
                (
                    name,
                    "EXCEPTION",
                    elapsed,
                )
            )

    print("\n")
    print("=" * 80)
    print("SUMMARY")
    print("=" * 80)

    results.sort(key=lambda x: (x[1] != "SUCCESS", x[2]))

    for name, status, elapsed in results:

        print(
            f"{name:<25}"
            f"{status:<10}"
            f"{elapsed:.2f}s"
        )


if __name__ == "__main__":

    benchmark()