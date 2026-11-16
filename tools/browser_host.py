"""Console native-messaging host; stdout is reserved for Chrome protocol frames."""
from macooii.browser_capture import native_main

if __name__ == "__main__":
    raise SystemExit(native_main())
