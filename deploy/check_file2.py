with open(r'C:\Users\MY PC\Documents\Default Project\Five mark v1\deploy\src\paper\journal.py', 'rb') as f:
    content = f.read()
    lines = content.split(b'\n')
    print('Total lines:', len(lines))
    print('Line 231:', repr(lines[230]))
    print('Line 230:', repr(lines[229]))
    print('Line 232:', repr(lines[231]))
    # Check for CR without LF
    for i, line in enumerate(lines):
        if b'\r' in line and not line.endswith(b'\r\n'):
            print(f'Line {i+1}: bare CR')
    # Check for BOM
    if content.startswith(b'\xef\xbb\xbf'):
        print('BOM found')
    # Check for null bytes
    if b'\x00' in content:
        print('NULL bytes found')
    # Check encoding
    try:
        content.decode('utf-8')
        print('UTF-8 OK')
    except UnicodeDecodeError as e:
        print('UTF-8 decode error:', e)