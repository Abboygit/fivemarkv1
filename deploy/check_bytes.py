with open(r'C:\Users\MY PC\Documents\Default Project\Five mark v1\deploy\src\paper\journal.py', 'rb') as f:
    content = f.read()
    lines = content.split(b'\n')
    line = lines[230]
    print('Line 231:', repr(line))
    print('Length:', len(line))
    for i, b in enumerate(line):
        if b > 127 or b in (9, 13, 12, 11):
            print(f'  Pos {i}: {b} ({chr(b) if 32 <= b < 127 else "?"})')