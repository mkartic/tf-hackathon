import re
import sys

final = {}
for line in open(sys.argv[1]):
    m = re.search(r"req_id=(\w+).*?status=(\d+)", line)
    if m:
        final[m[1]] = int(m[2])  # lines are time-ordered: the last one wins
failed = sum(s >= 500 for s in final.values())
print(f"requests={len(final)} failed={failed} error_rate={failed / len(final):.2%}")
