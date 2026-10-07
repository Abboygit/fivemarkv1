with open(r'C:\Users\MY PC\Documents\Default Project\Five mark v1\deploy\src\paper\journal.py', 'rb') as f:
    content = f.read()
    lines = content.split(b'\n')
    print('Total lines:', len(lines))
    print('Line 231:', repr(lines[230]))
    print('Line 230:', repr(lines[229]))
    print('Line 232:', repr(lines[231]))
    for i in range(225, 235):
        line = lines[i]
        indent = len(line) - len(line.lstrip())
        print(f'{i+1}: indent={len(line) - len(line.lstrip())} len={len(line)} repr={repr(line[:80])}')