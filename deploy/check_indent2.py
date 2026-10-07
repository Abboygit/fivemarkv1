with open(r'C:\Users\MY PC\Documents\Default Project\Five mark v1\deploy\src\paper\journal.py', 'rb') as f:
    content = f.read()
    lines = content.split(b'\n')
    print('Total lines:', len(lines))
    # Check lines around 231
    for i in range(225, 240):
        line = lines[i]
        indent = len(line) - len(line.lstrip())
        print(f'{i+1}: indent={indent} len={len(line)} endswith={repr(line[-10:])}')
        # Check for non-ASCII
        for i, b in enumerate(line):
            if b > 127:
                print(f'  Non-ASCII at pos {i}: {b}')
        # Check for tabs in indentation
        leading = line[:len(line) - len(line.lstrip())]
        if b'\t' in leading:
            print(f'  TAB in indentation at line {i+1}')