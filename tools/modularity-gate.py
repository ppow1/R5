import pathlib
p = pathlib.Path(__file__).parent.parent / "cme" / "socket.py"
size = p.stat().st_size if p.exists() else 0
print(f"cme/socket.py {size} bytes")
if size < 15360:
    print("PASS size cme/socket.py %d <15KB" % size)
    print("PASS - lean gate")
else:
    print("FAIL size %d >=15360" % size)
    exit(1)
