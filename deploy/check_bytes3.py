with open(r'C:\Users\MY PC\Documents\Default Project\Five mark v1\deploy\src\paper\journal.py', 'rb') as f:
    content = f.read()
    lines = content.split(b'\n')
    for i in range(225, 240):
        line = lines[i]
        print(f'{i+1}: len={len(lines[i])} indent={len(lines[i]) - len(lines[i].lstrip())} endswith={repr(lines[i][-10:])}')