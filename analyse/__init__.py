import random

if __name__ == '__main__':
    catch_per_minute = 0.3
    sleep_time = random.uniform(60 / catch_per_minute - 10, 60 / catch_per_minute + 10)
    print(f"随机睡眠...等待{sleep_time}s")