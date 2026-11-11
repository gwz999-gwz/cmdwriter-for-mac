import signal
import sys
import time
import asyncio


class SignalHandler:
    def __init__(self, callback):
        self.last_time = time.time()
        self.callback = callback

    def __call__(self, signum, frame):
        now = time.time()
        if now - self.last_time > 1.0:
            self.last_time = now
            print(f"\n已收到 {signal.Signals(signum).name}，1 秒内再次按下可退出。 / Press again within 1 second to exit.")
        else:
            print(f"\n已收到 {signal.Signals(signum).name}，确认退出。 / Exiting.\n")
            self.last_time = 0
            self.callback()
            
def register_signal(callback):
    signal.signal(signal.SIGINT, SignalHandler(callback))