with open(r'C:\Users\MY PC\Documents\Default Project\Five mark v1\deploy\src\paper\journal.py', 'rb') as f:
    content = f.read()
    lines = content.split(b'\n')
    print('Total lines:', len(lines))
    line = lines[230]
    print('Line 231:', repr(line))
    print('Ends with:', repr(line[-10:]))
    if b'\r' in lines[230]:
        print('CR found in line 231')
    for i, line in enumerate(content.split(b'\n')):
        if b'\r' in line and not line.endswith(b'\r\n'):
            print(f'Line {i+1}: has bare CR')