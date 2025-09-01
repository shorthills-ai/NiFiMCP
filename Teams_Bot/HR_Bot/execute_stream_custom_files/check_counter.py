import sys
import os

# Paths
base_dir = "/home/nifi/nifi2/HR_Bot/data"
queue_path = os.path.join(base_dir, "queue.txt")
counter_path = os.path.join(base_dir, "counter.txt")

def append_content_to_queue(content):
    with open(queue_path, "a") as f:
        f.write(content.strip() + "\n")

def read_counter():
    try:
        with open(counter_path, "r") as f:
            return int(f.read().strip())
    except Exception:
        return 0

def write_counter(val):
    with open(counter_path, "w") as f:
        f.write(str(val))

def main():
    content = sys.stdin.read().strip()
    append_content_to_queue(content)

    counter = read_counter()
    if counter == 1:
        try:
            with open(queue_path, "r") as f:
                all_content = f.read().strip()
        except Exception:
            all_content = ""

        # Empty queue
        with open(queue_path, "w") as f:
            f.write("")

        # Print everything together
        output = "Succesfully_uploaded\n" + all_content
        print(output)
    elif counter > 1:
        write_counter(counter - 1)
        print("wait_flag")
    else:
        print("wait_flag")

if __name__ == "__main__":
    main()
